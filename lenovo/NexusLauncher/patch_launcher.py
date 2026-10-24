#!/usr/bin/env python3
"""Patch Pixel Launcher (tablet) for TB710FU. Each patch is located by its exact
instruction bytes (not a fixed offset) and the build fails if it is not found.

1. Swipe-home dock alignment. TaskbarLauncherStateController
   .onIconAlignmentRatioChanged (with TaskbarViewController
   .createIconAlignmentController inlined by R8) computes the taskbar Y offset
   as taskbarDp.getTaskbarOffsetY(). The taskbar DeviceProfile carries the 57dp
   taskbar icon size, so with the 66dp hotseat icons of the responsive grid the
   dock lands 19px low and snaps up when the real hotseat takes over. Call it on
   the launcher DeviceProfile instead (v13 -> v11), which yields
   barBottomSpace + hotseatIcon/2 - taskbarHeight/2: the hotseat icon centre for
   any icon size.

2. Search bar return animation. Swiping home from an app launched from the
   hotseat search bar (OseWidgetView, an app widget) runs
   LauncherSwipeHandlerV2.createWidgetHomeAnimationFactory, which flies a copy
   of the widget (FloatingWidgetView) into place while the taskbar already shows
   its own search bar there, so the bar is drawn twice for ~0.35 s. Treat the
   search bar like a translucent target (floatingWidgetAlpha 0): the closing
   window shrinks and fades into the bar. Other widgets keep the flying copy.
     before: floatingWidgetAlpha = isTargetTranslucent ? 0f : 1f
     after:  floatingWidgetAlpha = (isTargetTranslucent || hostView instanceof
                                    OseWidgetView) ? 0f : 1f
   The 8 code units are rewritten in place, so nothing else moves.

usage: patch_launcher.py <in.apk> <out-unsigned.apk>
"""
import hashlib
import struct
import sys
import zipfile
import zlib


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


class Dex:
    def __init__(self, data):
        self.d = data
        self.string_ids_off = u32(data, 0x3C)
        self.type_ids_size, self.type_ids_off = u32(data, 0x40), u32(data, 0x44)
        self.method_ids_size, self.method_ids_off = u32(data, 0x58), u32(data, 0x5C)

    def string(self, i):
        off = u32(self.d, self.string_ids_off + 4 * i)
        while self.d[off] & 0x80:  # skip uleb128 length
            off += 1
        off += 1
        return bytes(self.d[off:self.d.index(b"\0", off)]).decode("utf-8", "replace")

    def type_name(self, i):
        return self.string(u32(self.d, self.type_ids_off + 4 * i))

    def type_index(self, name):
        found = [i for i in range(self.type_ids_size) if self.type_name(i) == name]
        if len(found) != 1:
            raise SystemExit(f"type {name} not unique: {found}")
        return found[0]

    def method_index(self, cls, name):
        found = []
        for m in range(self.method_ids_size):
            class_idx, _proto, name_idx = struct.unpack_from("<HHI", self.d, self.method_ids_off + 8 * m)
            if self.string(name_idx) == name and self.type_name(class_idx) == cls:
                found.append(m)
        if len(found) != 1:
            raise SystemExit(f"method {cls}->{name} not unique: {found}")
        return found[0]


def find_once(dex, needle, what):
    hits, start = [], 0
    while (i := dex.find(needle, start)) >= 0:
        hits.append(i)
        start = i + 1
    if len(hits) != 1:
        raise SystemExit(f"{what}: expected exactly one match, found {len(hits)}")
    return hits[0]


def patch_dex(data):
    dex = bytearray(data)
    info = Dex(dex)

    # 1. invoke-virtual {v13}, DeviceProfile.getTaskbarOffsetY() ; move-result v5
    idx = info.method_index("Lcom/android/launcher3/DeviceProfile;", "getTaskbarOffsetY")
    needle = bytes([0x6E, 0x10]) + struct.pack("<H", idx) + bytes([0x0D, 0x00, 0x0A, 0x05])
    site = find_once(dex, needle, "dock alignment call site")
    dex[site + 4] = 0x0B  # v13 (taskbar DeviceProfile) -> v11 (launcher DeviceProfile)
    print(f"dock alignment: patched at 0x{site:x}")

    # 2. createWidgetHomeAnimationFactory prologue (v12 hostView, v13 isTargetTranslucent,
    #    v10 floatingWidgetAlpha):
    #    if-eqz v13, +5 ; const/4 v0, 0 ; move v10, v0 ; goto +4 ;
    #    const/high16 v0, 1.0f ; goto -4
    old = bytes.fromhex("380d0500 1200 010a 2804 1500803f 28fc".replace(" ", ""))
    site = find_once(dex, old, "widget return alpha prologue")
    ose = info.type_index("Lcom/android/launcher3/qsb/OseWidgetView;")
    new = (bytes([0x20, 0xCA]) + struct.pack("<H", ose)  # instance-of v10, v12, OseWidgetView
           + bytes([0xB6, 0xDA])                        # or-int/2addr v10, v13
           + bytes([0xDF, 0x0A, 0x0A, 0x01])            # xor-int/lit8 v10, v10, #1
           + bytes([0x82, 0xAA])                        # int-to-float v10, v10
           + bytes([0x00, 0x00, 0x00, 0x00]))           # nop ; nop
    assert len(new) == len(old)
    dex[site:site + len(old)] = new
    print(f"search bar return: patched at 0x{site:x}")

    # fix SHA-1 signature and Adler-32 checksum in the header
    dex[12:32] = hashlib.sha1(dex[32:]).digest()
    struct.pack_into("<I", dex, 8, zlib.adler32(bytes(dex[12:])) & 0xFFFFFFFF)
    return bytes(dex)


def main():
    src, out = sys.argv[1], sys.argv[2]
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            name = info.filename.split("/")[-1].upper()
            if info.filename.startswith("META-INF/") and name.endswith(
                    (".SF", ".RSA", ".EC", ".DSA", "MANIFEST.MF")):
                continue  # old signature
            data = zin.read(info.filename)
            if info.filename == "classes.dex":
                data = patch_dex(data)
            zout.writestr(info, data, compress_type=info.compress_type)


if __name__ == "__main__":
    main()
