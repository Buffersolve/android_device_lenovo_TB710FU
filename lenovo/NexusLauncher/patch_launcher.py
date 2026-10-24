#!/usr/bin/env python3
"""Patch Pixel Launcher so the swipe-home taskbar aligns with the hotseat.

TaskbarLauncherStateController.onIconAlignmentRatioChanged (with
TaskbarViewController.createIconAlignmentController inlined by R8) computes the
taskbar Y offset as taskbarDp.getTaskbarOffsetY(). The taskbar DeviceProfile has
the workspace icon size replaced by the taskbar icon size (57dp), so with the
66dp hotseat icons of the responsive grid the dock lands 19px low and snaps up
when the real hotseat takes over. Call it on the launcher DeviceProfile, which
yields barBottomSpace + hotseatIcon/2 - taskbarHeight/2: exactly the hotseat
icon centre for any icon size.

The patch changes the register of one invoke-virtual (v13 -> v11) and is located
by its exact instruction context, not by a fixed offset.

usage: patch_launcher.py <in.apk> <out-unsigned.apk>
"""
import hashlib
import struct
import sys
import zipfile
import zlib

# iget-object v13, v10, TaskbarActivityContext.mDeviceProfile is followed (a few
# instructions later) by: invoke-virtual {v13}, DeviceProfile.getTaskbarOffsetY()
# move-result v5 ; iget-object v4, v8, ...mTaskbarIconTranslationYForHome
# We match "6e10 <idx> 0d00 0a05" (invoke {v13} + move-result v5) and verify the
# method index resolves to DeviceProfile.getTaskbarOffsetY.


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def method_index(dex, cls, name):
    string_ids_size, string_ids_off = u32(dex, 0x38), u32(dex, 0x3C)
    type_ids_off = u32(dex, 0x44)
    method_ids_size, method_ids_off = u32(dex, 0x58), u32(dex, 0x5C)

    def string(i):
        off = u32(dex, string_ids_off + 4 * i)
        # skip uleb128 length
        while dex[off] & 0x80:
            off += 1
        off += 1
        end = dex.index(b"\0", off)
        return dex[off:end].decode("utf-8", "replace")

    def type_name(i):
        return string(u32(dex, type_ids_off + 4 * i))

    found = []
    for m in range(method_ids_size):
        o = method_ids_off + 8 * m
        class_idx, _proto, name_idx = struct.unpack_from("<HHI", dex, o)
        if string(name_idx) == name and type_name(class_idx) == cls:
            found.append(m)
    return found


def patch_dex(dex):
    dex = bytearray(dex)
    idxs = method_index(dex, "Lcom/android/launcher3/DeviceProfile;", "getTaskbarOffsetY")
    if len(idxs) != 1:
        raise SystemExit(f"getTaskbarOffsetY method id not unique: {idxs}")
    idx = idxs[0]
    # invoke-virtual {v13}, meth@idx ; move-result v5
    needle = bytes([0x6E, 0x10]) + struct.pack("<H", idx) + bytes([0x0D, 0x00, 0x0A, 0x05])
    hits = []
    start = 0
    while True:
        i = dex.find(needle, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one call site, found {len(hits)}: {[hex(h) for h in hits]}")
    site = hits[0]
    dex[site + 4] = 0x0B  # v13 -> v11 (launcher DeviceProfile)
    # fix SHA-1 signature and Adler-32 checksum in the header
    dex[12:32] = hashlib.sha1(dex[32:]).digest()
    struct.pack_into("<I", dex, 8, zlib.adler32(bytes(dex[12:])) & 0xFFFFFFFF)
    print(f"patched call site at 0x{site:x} (method id 0x{idx:x})")
    return bytes(dex)


def main():
    src, out = sys.argv[1], sys.argv[2]
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            if info.filename.startswith("META-INF/") and info.filename.split("/")[-1].upper().endswith(
                    (".SF", ".RSA", ".EC", ".DSA", "MANIFEST.MF")):
                continue
            data = zin.read(info.filename)
            if info.filename == "classes.dex":
                data = patch_dex(data)
            zout.writestr(info, data, compress_type=info.compress_type)


if __name__ == "__main__":
    main()
