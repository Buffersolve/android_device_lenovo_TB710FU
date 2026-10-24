#!/usr/bin/env python3
"""Patch Pixel Launcher (tablet) for TB710FU.

classes.dex is disassembled with baksmali, edited, and reassembled with smali;
the TaskbarQsbHider helper is added as an extra dex. Every edit must match
exactly the expected number of times, otherwise the build fails (e.g. after a
Pixel Launcher update), instead of silently shipping an unpatched launcher.

1. Swipe-home dock alignment. TaskbarLauncherStateController
   .onIconAlignmentRatioChanged (with TaskbarViewController
   .createIconAlignmentController inlined by R8) computes the taskbar Y offset
   as taskbarDp.getTaskbarOffsetY(). The taskbar DeviceProfile carries the 57dp
   taskbar icon size, so with the 66dp hotseat icons of the responsive grid the
   dock lands 19px low and snaps up when the real hotseat takes over. Call it on
   the launcher DeviceProfile (v11) instead of the taskbar one (v13), which
   yields barBottomSpace + hotseatIcon/2 - taskbarHeight/2: the hotseat icon
   centre for any icon size.

2. Search bar return/launch animation. FloatingWidgetView flies a copy of the
   hotseat search bar widget into place while the taskbar shows its own search
   bar there, so the bar was drawn twice (home swipe, back gesture). Its
   setUpdatesDeferred(true/false) calls mark the start and end of the
   animation; route them through TaskbarQsbHider, which hides the taskbar
   search bar meanwhile, like the launcher already does for app icons.

3. Transient taskbar stuck open in apps. TaskbarUnstashInputConsumer sets
   FLAG_AUTOHIDE_SUSPEND_TOUCHING on ACTION_DOWN and clears it on ACTION_UP /
   ACTION_CANCEL through mTaskbarApiProxy. When the input consumer is switched
   mid-gesture (e.g. TYPE_RESET_GESTURE), onConsumerAboutToBeSwitched() nulls
   the proxy without clearing the flag, so the later ACTION_UP cannot clear it
   and the taskbar never times out. Run the ACTION_UP/CANCEL cleanup first.

usage: patch_launcher.py --baksmali CMD --smali CMD --helper-dex-zip ZIP <in.apk> <out.apk>
"""
import argparse
import os
import re
import shlex
import subprocess
import tempfile
import zipfile

HOST_VIEW = "Lcom/android/launcher3/widget/LauncherAppWidgetHostView;"
HIDER = "Lcom/android/launcher3/tb710fu/TaskbarQsbHider;"


def edit(root, cls, method, pattern, repl, count):
    p = os.path.join(root, *cls.split("/")) + ".smali"
    src = open(p).read()
    # " name(" so that "init" does not match the "<init>" constructors
    m = re.search(r"(\.method [^\n]* %s\(.*?\n)(.*?)(\n\.end method)" % re.escape(method), src, re.S)
    if not m:
        raise SystemExit(f"{cls}.{method}: method not found")
    body, n = re.subn(pattern, repl, m.group(2))
    if n != count:
        raise SystemExit(f"{cls}.{method}: expected {count} match(es), found {n}")
    open(p, "w").write(src[:m.start(2)] + body + src[m.end(2):])
    print(f"{cls}.{method}: {n} edit(s)")


def patch_smali(root):
    # 1. dock alignment
    edit(root, "com/android/launcher3/taskbar/TaskbarLauncherStateController",
         "onIconAlignmentRatioChanged",
         r"invoke-virtual \{v13\}, Lcom/android/launcher3/DeviceProfile;->getTaskbarOffsetY\(\)I"
         r"(\s+move-result v5)",
         r"invoke-virtual {v11}, Lcom/android/launcher3/DeviceProfile;->getTaskbarOffsetY()I\1", 1)

    # 2. hide the taskbar search bar during the floating widget animation
    call = (r"invoke-virtual \{([vp]\d+), ([vp]\d+)\}, "
            + re.escape(HOST_VIEW) + r"->setUpdatesDeferred\(Z\)V")
    hider = (r"invoke-static {\1, \2}, " + HIDER
             + "->setUpdatesDeferred(" + HOST_VIEW + "Z)V")
    for method in ("init", "finish"):
        edit(root, "com/android/quickstep/views/FloatingWidgetView", method, call, hider, 1)

    # 3. stuck transient taskbar: clean up like ACTION_UP/CANCEL before dropping the proxy
    consumer = "Lcom/android/quickstep/inputconsumers/TaskbarUnstashInputConsumer;"
    edit(root, "com/android/quickstep/inputconsumers/TaskbarUnstashInputConsumer",
         "onConsumerAboutToBeSwitched",
         r"(invoke-super \{p0\}, Lcom/android/quickstep/inputconsumers/DelegateInputConsumer;"
         r"->onConsumerAboutToBeSwitched\(\)V\n)",
         r"\1\n    invoke-direct {p0}, " + consumer + r"->cleanupAfterMotionEvent()V\n", 1)


def run(cmd, *args):
    subprocess.run(shlex.split(cmd) + list(args), check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baksmali", required=True)
    ap.add_argument("--smali", required=True)
    ap.add_argument("--helper-dex-zip", required=True)
    ap.add_argument("src")
    ap.add_argument("out")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(args.src) as z:
            open(os.path.join(tmp, "classes.dex"), "wb").write(z.read("classes.dex"))
            dex_count = sum(1 for n in z.namelist() if re.fullmatch(r"classes\d*\.dex", n))
        smali_dir = os.path.join(tmp, "smali")
        run(args.baksmali, "d", os.path.join(tmp, "classes.dex"), "-o", smali_dir)
        patch_smali(smali_dir)
        new_dex = os.path.join(tmp, "classes.new.dex")
        run(args.smali, "a", smali_dir, "-o", new_dex, "--api", "35")
        with zipfile.ZipFile(args.helper_dex_zip) as hz:
            helper = hz.read("classes.dex")
        helper_name = f"classes{dex_count + 1}.dex"

        with zipfile.ZipFile(args.src) as zin, zipfile.ZipFile(args.out, "w") as zout:
            for info in zin.infolist():
                base = info.filename.split("/")[-1].upper()
                if info.filename.startswith("META-INF/") and base.endswith(
                        (".SF", ".RSA", ".EC", ".DSA", "MANIFEST.MF")):
                    continue  # old signature; android_app_import re-signs
                data = open(new_dex, "rb").read() if info.filename == "classes.dex" \
                    else zin.read(info.filename)
                zout.writestr(info, data, compress_type=info.compress_type)
            zout.writestr(zipfile.ZipInfo(helper_name, date_time=(2008, 1, 1, 0, 0, 0)), helper,
                          compress_type=zipfile.ZIP_DEFLATED)
        print(f"added {helper_name} (TaskbarQsbHider)")


if __name__ == "__main__":
    main()
