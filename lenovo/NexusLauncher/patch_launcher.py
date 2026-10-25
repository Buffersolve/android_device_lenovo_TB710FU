#!/usr/bin/env python3
"""Patch Pixel Launcher (tablet) for TB710FU.

classes.dex and classes2.dex are disassembled with baksmali, edited, and
reassembled with smali; the TaskbarQsbHider and SmartspaceWeather helpers are
added as an extra dex. Every edit must match
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

4. Taskbar left in the launcher state after a quick switch from home (swipe
   along the nav handle on the home screen). TaskbarLauncherStateController
   .onStateChangeApplied() captures isInLauncher, and for
   QUICK_SWITCH_FROM_HOME re-enters itself (updateStateForFlag(FLAG_VISIBLE,
   false); applyState(0)), which correctly sets FLAG_IN_APP. The outer call
   then adds an animator listener with the stale isInLauncher = true, whose
   onAnimationStart sets FLAG_IN_APP back to false: the app is in front but
   the taskbar stays in its home state and never stashes. Make the listener
   read isInLauncher(mState) when it runs.

5. At a Glance weather card did not open anything. Its tap action goes to the
   Google app smartspace trampoline, which only forwards it when the caller is
   a Google-signed Pixel Launcher ("QSB permission is not trusted"), and this
   one is re-signed. The BcSmartspace card click listeners (classes2.dex) call
   IntentStarter.startFromAction(SmartspaceAction|TapAction, View, boolean);
   pass the card's SmartspaceTarget along to SmartspaceWeather, which starts
   Pixel Weather for weather cards pointing at the trampoline.

usage: patch_launcher.py --baksmali CMD --smali CMD --helper-dex-zip ZIP <in.apk> <out.apk>
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile

HOST_VIEW = "Lcom/android/launcher3/widget/LauncherAppWidgetHostView;"
HIDER = "Lcom/android/launcher3/tb710fu/TaskbarQsbHider;"
WEATHER = "Lcom/android/launcher3/tb710fu/SmartspaceWeather;"
STARTER = "Lcom/android/systemui/plugins/BcSmartspaceDataPlugin$IntentStarter;"
TARGET = "Landroid/app/smartspace/SmartspaceTarget;"


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


def check_dex_header(path):
    with open(path, "rb") as f:
        head = f.read(0x28)
    version = int(head[4:7])
    header_size = int.from_bytes(head[0x24:0x28], "little")
    expected = 0x78 if version >= 41 else 0x70
    if header_size != expected:
        sys.exit(f"{path}: dex {version:03d} with a {header_size} byte header")


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

    # 4. taskbar left in the launcher state after a quick switch from home: the
    #    onStateChangeApplied() animator listener must use the state at the time it runs
    tlsc = "Lcom/android/launcher3/taskbar/TaskbarLauncherStateController;"
    listeners = []
    tdir = os.path.join(root, "com/android/launcher3/taskbar")
    for name in sorted(os.listdir(tdir)):
        if not name.startswith("TaskbarLauncherStateController$") or not name.endswith(".smali"):
            continue
        src = open(os.path.join(tdir, name)).read()
        if ("->val$isInLauncher:Z" in src and "->updateOverviewDragState(" in src
                and "->updateStateForFlag(JZ)Z" in src):
            listeners.append(name[:-len(".smali")])
    if len(listeners) != 1:
        raise SystemExit(f"isInLauncher animator listener not unique: {listeners}")
    cls = listeners[0]
    lcls = "L" + "com/android/launcher3/taskbar/" + cls + ";"
    edit(root, "com/android/launcher3/taskbar/" + cls, "onAnimationStart",
         r"iget-boolean ([vp]\d+), p0, " + re.escape(lcls) + r"->val\$isInLauncher:Z",
         r"iget-object \1, p0, " + lcls + "->this$0:" + tlsc + "\n\n"
         r"    iget \1, \1, " + tlsc + "->mState:I\n\n"
         r"    invoke-static {\1}, " + tlsc + "->isInLauncher(I)Z\n\n"
         r"    move-result \1", 2)

    # 3. stuck transient taskbar: clean up like ACTION_UP/CANCEL before dropping the proxy
    consumer = "Lcom/android/quickstep/inputconsumers/TaskbarUnstashInputConsumer;"
    edit(root, "com/android/quickstep/inputconsumers/TaskbarUnstashInputConsumer",
         "onConsumerAboutToBeSwitched",
         r"(invoke-super \{p0\}, Lcom/android/quickstep/inputconsumers/DelegateInputConsumer;"
         r"->onConsumerAboutToBeSwitched\(\)V\n)",
         r"\1\n    invoke-direct {p0}, " + consumer + r"->cleanupAfterMotionEvent()V\n", 1)


def patch_smali2(root):
    # 5. weather card: hand the SmartspaceTarget to SmartspaceWeather
    for action in ("Landroid/app/smartspace/SmartspaceAction;",
                   "Landroid/app/smartspace/uitemplatedata/TapAction;"):
        call = (r"invoke-interface \{([vp]\d+), ([vp]\d+), ([vp]\d+), ([vp]\d+)\}, "
                + re.escape(STARTER) + r"->startFromAction\(" + re.escape(action)
                + r"Landroid/view/View;Z\)V")
        hits = []
        for dirpath, _, files in os.walk(root):
            for name in files:
                path = os.path.join(dirpath, name)
                src = open(path).read()
                if re.search(call, src) and ".implements Landroid/view/View$OnClickListener;" in src:
                    hits.append(path)
        if len(hits) != 1:
            raise SystemExit(f"startFromAction({action}) click listener not unique: {hits}")
        path = hits[0]
        src = open(path).read()
        m = re.search(r"(\.method public final onClick\(Landroid/view/View;\)V\n)(.*?)(\n\.end method)",
                      src, re.S)
        if not m:
            raise SystemExit(f"{path}: onClick not found")
        body = m.group(2)
        loads = re.findall(r"iget-object ([vp]\d+), p0, L[^;]+;->\w+:" + re.escape(TARGET), body)
        calls = list(re.finditer(call, body))
        if len(loads) != 1 or len(calls) != 1:
            raise SystemExit(f"{path}: expected one target load and one call, "
                             f"found {len(loads)} and {len(calls)}")
        reg = loads[0]
        load_end = re.search(r"iget-object " + reg + r", p0, L[^;]+;->\w+:" + re.escape(TARGET),
                             body).end()
        between = body[load_end:calls[0].start()]
        # the target register must still hold the target at the call
        if re.search(r"^\s+(?!invoke|if-|check-cast|\.)\S+ " + reg + r"\b", between, re.M) \
                or re.search(r"^\s+move-result(-object)? " + reg + r"\b", between, re.M):
            raise SystemExit(f"{path}: {reg} is overwritten before startFromAction")
        body = body[:calls[0].start()] + re.sub(
            call, r"invoke-static {\1, \2, \3, \4, " + reg + "}, " + WEATHER
            + "->startFromAction(" + STARTER + action + "Landroid/view/View;Z" + TARGET + ")V",
            body[calls[0].start():], count=1)
        open(path, "w").write(src[:m.start(2)] + body + src[m.end(2):])
        print(f"{os.path.relpath(path, root)}.onClick: SmartspaceWeather ({action})")


# dex file -> edits; the other dex files are copied unchanged
DEX_EDITS = {"classes.dex": patch_smali, "classes2.dex": patch_smali2}


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
            dex_count = sum(1 for n in z.namelist() if re.fullmatch(r"classes\d*\.dex", n))
            new_dex = {}
            for name, patch in DEX_EDITS.items():
                old = os.path.join(tmp, name)
                open(old, "wb").write(z.read(name))
                smali_dir = os.path.join(tmp, name + ".smali")
                run(args.baksmali, "d", old, "-o", smali_dir)
                patch(smali_dir)
                new = os.path.join(tmp, name + ".new")
                # --api 34 writes dex 039. With 35 smali stamps dex 041 but keeps the
                # 0x70 byte header instead of the 0x78 container header, which ART
                # rejects ("Header size is 112 but 120 was expected").
                run(args.smali, "a", smali_dir, "-o", new, "--api", "34")
                check_dex_header(new)
                new_dex[name] = new
        with zipfile.ZipFile(args.helper_dex_zip) as hz:
            helper = hz.read("classes.dex")
        helper_name = f"classes{dex_count + 1}.dex"

        with zipfile.ZipFile(args.src) as zin, zipfile.ZipFile(args.out, "w") as zout:
            for info in zin.infolist():
                base = info.filename.split("/")[-1].upper()
                if info.filename.startswith("META-INF/") and base.endswith(
                        (".SF", ".RSA", ".EC", ".DSA", "MANIFEST.MF")):
                    continue  # old signature; android_app_import re-signs
                data = open(new_dex[info.filename], "rb").read() if info.filename in new_dex \
                    else zin.read(info.filename)
                zout.writestr(info, data, compress_type=info.compress_type)
            zout.writestr(zipfile.ZipInfo(helper_name, date_time=(2008, 1, 1, 0, 0, 0)), helper,
                          compress_type=zipfile.ZIP_DEFLATED)
        print(f"added {helper_name} (TaskbarQsbHider, SmartspaceWeather)")


if __name__ == "__main__":
    main()
