/*
 * SPDX-FileCopyrightText: 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * Postinstall step: gives the vendor_boot dtb just written to the target slot
 * the region of the board.
 *
 * The Lenovo bootloader compares the region_country property of the dtb
 * ("PRC" or "ROW") with the region of the board (devinfo) and powers the
 * device off when they differ. PRC and ROW firmware ship the same dtb apart
 * from that string, so the build carries the PRC one and this step rewrites it
 * to the region of the running dtb, which the bootloader has just accepted.
 * The vbmeta hash of vendor_boot no longer matches then, which the unlocked
 * bootloader allows.
 *
 * Any failure exits non-zero: update_engine then keeps the current slot active
 * instead of switching to a slot that might not boot.
 */

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include <string>
#include <vector>

namespace {

constexpr char kTag[] = "tb520fu_region_postinstall";
constexpr char kRunningFdt[] = "/sys/firmware/fdt";
constexpr char kVendorBoot[] = "/dev/block/by-name/vendor_boot";
// Only in the recovery ramdisk
constexpr char kRecoveryBinary[] = "/system/bin/recovery";

constexpr uint32_t kFdtMagic = 0xd00dfeed;
constexpr uint32_t kFdtHeaderSize = 40;
constexpr uint32_t kFdtBeginNode = 1;
constexpr uint32_t kFdtProp = 3;
constexpr uint32_t kFdtNop = 4;
constexpr char kRegionProp[] = "region_country";
// "PRC\0" or "ROW\0"
constexpr uint32_t kRegionSize = 4;

// boot_img_hdr of vendor_boot (v3/v4), see system/tools/mkbootimg
constexpr char kVendorBootMagic[] = "VNDRBOOT";
constexpr size_t kVendorBootHeaderSize = 2112;
constexpr size_t kOffHeaderVersion = 8;
constexpr size_t kOffPageSize = 12;
constexpr size_t kOffVendorRamdiskSize = 24;
constexpr size_t kOffHeaderSize = 2096;
constexpr size_t kOffDtbSize = 2100;

uint32_t Be32(const uint8_t* p) {
    return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3];
}

uint32_t Le32(const uint8_t* p) {
    return uint32_t(p[3]) << 24 | uint32_t(p[2]) << 16 | uint32_t(p[1]) << 8 | p[0];
}

uint64_t AlignUp(uint64_t value, uint64_t align) {
    return (value + align - 1) / align * align;
}

bool IsKnownRegion(const std::string& region) {
    return region == "PRC" || region == "ROW";
}

bool ReadFile(const char* path, std::vector<uint8_t>* out) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        int saved_errno = errno;
        fprintf(stderr, "%s: open %s: %s\n", kTag, path, strerror(saved_errno));
        errno = saved_errno;
        return false;
    }
    out->clear();
    uint8_t buf[64 * 1024];
    while (true) {
        ssize_t n = TEMP_FAILURE_RETRY(read(fd, buf, sizeof(buf)));
        if (n < 0) {
            fprintf(stderr, "%s: read %s: %s\n", kTag, path, strerror(errno));
            close(fd);
            return false;
        }
        if (n == 0) break;
        out->insert(out->end(), buf, buf + n);
    }
    close(fd);
    return true;
}

// 1 in recovery (update_engine_sideload), 0 in Android, -1 if unknown
int InRecovery() {
    if (access(kRecoveryBinary, F_OK) == 0) return 1;
    return errno == ENOENT ? 0 : -1;
}

bool PreadFully(int fd, void* buf, size_t size, off64_t offset) {
    auto* p = static_cast<uint8_t*>(buf);
    while (size > 0) {
        ssize_t n = TEMP_FAILURE_RETRY(pread64(fd, p, size, offset));
        if (n <= 0) return false;
        p += n;
        size -= n;
        offset += n;
    }
    return true;
}

bool PwriteFully(int fd, const void* buf, size_t size, off64_t offset) {
    auto* p = static_cast<const uint8_t*>(buf);
    while (size > 0) {
        ssize_t n = TEMP_FAILURE_RETRY(pwrite64(fd, p, size, offset));
        if (n <= 0) return false;
        p += n;
        size -= n;
        offset += n;
    }
    return true;
}

// Finds the region_country property of the root node of the fdt at |base| in
// |data|. Sets |*total| to the size of the fdt and |*value_off| to the offset
// of the property value in |data|. Returns false if the fdt is malformed or has
// no such property.
bool FindRegion(const std::vector<uint8_t>& data, size_t base, size_t* total, size_t* value_off) {
    if (data.size() < base || data.size() - base < kFdtHeaderSize) return false;
    const uint8_t* fdt = data.data() + base;
    if (Be32(fdt) != kFdtMagic) return false;
    uint32_t size = Be32(fdt + 4);
    uint32_t off_struct = Be32(fdt + 8);
    uint32_t off_strings = Be32(fdt + 12);
    uint32_t size_strings = Be32(fdt + 32);
    uint32_t size_struct = Be32(fdt + 36);
    if (size < kFdtHeaderSize || size > data.size() - base) return false;
    if (off_struct > size || size_struct > size - off_struct) return false;
    if (off_strings > size || size_strings > size - off_strings) return false;
    *total = size;

    const uint8_t* strings = fdt + off_strings;
    size_t pos = off_struct;
    size_t end = off_struct + size_struct;
    auto token_at = [&](size_t p, uint32_t* token) {
        if (p > end || end - p < 4) return false;
        *token = Be32(fdt + p);
        return true;
    };

    uint32_t token;
    // Root node: FDT_BEGIN_NODE with an empty name, padded to 4 bytes
    while (token_at(pos, &token) && token == kFdtNop) pos += 4;
    if (!token_at(pos, &token) || token != kFdtBeginNode) return false;
    pos += 4;
    while (pos < end && fdt[pos] != 0) pos++;
    pos = AlignUp(pos + 1, 4);

    // Its properties come before its subnodes
    while (token_at(pos, &token)) {
        if (token == kFdtNop) {
            pos += 4;
            continue;
        }
        if (token != kFdtProp) break;
        if (end - pos < 12) return false;
        uint32_t len = Be32(fdt + pos + 4);
        uint32_t nameoff = Be32(fdt + pos + 8);
        size_t value = pos + 12;
        if (len > end - value || nameoff >= size_strings) return false;
        const char* name = reinterpret_cast<const char*>(strings + nameoff);
        size_t name_max = size_strings - nameoff;
        if (strnlen(name, name_max) == name_max) return false;
        if (strcmp(name, kRegionProp) == 0) {
            if (len != kRegionSize || fdt[value + kRegionSize - 1] != 0) return false;
            *value_off = base + value;
            return true;
        }
        pos = AlignUp(value + len, 4);
    }
    return false;
}

std::string RegionAt(const std::vector<uint8_t>& data, size_t value_off) {
    return std::string(reinterpret_cast<const char*>(data.data() + value_off), kRegionSize - 1);
}

// Offsets of the region values of all the fdts concatenated in |dtb|
bool FindRegions(const std::vector<uint8_t>& dtb, std::vector<size_t>* offsets) {
    offsets->clear();
    size_t base = 0;
    while (dtb.size() - base >= kFdtHeaderSize && Be32(dtb.data() + base) == kFdtMagic) {
        size_t total, value_off;
        if (!FindRegion(dtb, base, &total, &value_off)) {
            fprintf(stderr, "%s: no %s in the dtb at 0x%zx\n", kTag, kRegionProp, base);
            return false;
        }
        offsets->push_back(value_off);
        base += total;
    }
    if (offsets->empty()) {
        fprintf(stderr, "%s: no dtb in vendor_boot\n", kTag);
        return false;
    }
    return true;
}

bool ReadDtb(int fd, off64_t dtb_offset, size_t dtb_size, std::vector<uint8_t>* dtb) {
    dtb->resize(dtb_size);
    if (!PreadFully(fd, dtb->data(), dtb_size, dtb_offset)) {
        fprintf(stderr, "%s: read dtb: %s\n", kTag, strerror(errno));
        return false;
    }
    return true;
}

}  // namespace

int Run(const char* running_fdt, const char* vendor_boot) {
    std::vector<uint8_t> fdt;
    size_t total, value_off;
    if (!ReadFile(running_fdt, &fdt)) {
        // The step runs under the SELinux policy of the running system or
        // recovery, and the builds before it do not let it read the dtb.
        // Those systems only boot on boards that take the PRC dtb this build
        // ships, so updating them needs nothing. Their recovery can run on a
        // ROW board though: it has to be replaced first.
        if (errno != EACCES) return 1;
        int recovery = InRecovery();
        if (recovery == 0) {
            printf("%s: the running build predates this step, so the board takes "
                   "the PRC dtb\n", kTag);
            return 0;
        }
        if (recovery == 1) {
            fprintf(stderr, "%s: flash the recovery.img of this build first\n", kTag);
        }
        return 1;
    }
    if (!FindRegion(fdt, 0, &total, &value_off)) {
        fprintf(stderr, "%s: no %s in the running dtb\n", kTag, kRegionProp);
        return 1;
    }
    std::string region = RegionAt(fdt, value_off);
    if (!IsKnownRegion(region)) {
        fprintf(stderr, "%s: unknown running region '%s'\n", kTag, region.c_str());
        return 1;
    }

    int fd = open(vendor_boot, O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        fprintf(stderr, "%s: open %s: %s\n", kTag, vendor_boot, strerror(errno));
        return 1;
    }
    int ret = 1;
    do {
        off64_t image_size = lseek64(fd, 0, SEEK_END);
        uint8_t hdr[kVendorBootHeaderSize];
        if (image_size < off64_t(sizeof(hdr)) || !PreadFully(fd, hdr, sizeof(hdr), 0)) {
            fprintf(stderr, "%s: read %s header failed\n", kTag, vendor_boot);
            break;
        }
        uint32_t version = Le32(hdr + kOffHeaderVersion);
        uint32_t page_size = Le32(hdr + kOffPageSize);
        if (memcmp(hdr, kVendorBootMagic, strlen(kVendorBootMagic)) != 0 || version < 3 ||
            page_size == 0 || (page_size & (page_size - 1)) != 0) {
            fprintf(stderr, "%s: %s is not a vendor_boot image\n", kTag, vendor_boot);
            break;
        }
        uint64_t dtb_offset = AlignUp(Le32(hdr + kOffHeaderSize), page_size) +
                              AlignUp(Le32(hdr + kOffVendorRamdiskSize), page_size);
        uint32_t dtb_size = Le32(hdr + kOffDtbSize);
        if (dtb_size == 0 || dtb_offset + dtb_size > uint64_t(image_size)) {
            fprintf(stderr, "%s: bad dtb section in %s\n", kTag, vendor_boot);
            break;
        }

        std::vector<uint8_t> dtb;
        std::vector<size_t> offsets;
        if (!ReadDtb(fd, dtb_offset, dtb_size, &dtb) || !FindRegions(dtb, &offsets)) break;

        bool known = true;
        size_t mismatches = 0;
        for (size_t off : offsets) {
            std::string value = RegionAt(dtb, off);
            known = known && IsKnownRegion(value);
            if (value != region) mismatches++;
        }
        if (!known) {
            fprintf(stderr, "%s: unknown region in the new dtb\n", kTag);
            break;
        }
        if (mismatches == 0) {
            printf("%s: %zu dtbs already %s\n", kTag, offsets.size(), region.c_str());
            ret = 0;
            break;
        }

        bool written = true;
        for (size_t off : offsets) {
            if (RegionAt(dtb, off) == region) continue;
            if (!PwriteFully(fd, region.data(), region.size(), dtb_offset + off)) {
                fprintf(stderr, "%s: write %s: %s\n", kTag, vendor_boot, strerror(errno));
                written = false;
                break;
            }
        }
        if (!written) break;
        if (fsync(fd) != 0) {
            fprintf(stderr, "%s: fsync %s: %s\n", kTag, vendor_boot, strerror(errno));
            break;
        }

        // Read it back
        std::vector<size_t> check;
        if (!ReadDtb(fd, dtb_offset, dtb_size, &dtb) || !FindRegions(dtb, &check) ||
            check != offsets) {
            break;
        }
        bool ok = true;
        for (size_t off : check) ok = ok && RegionAt(dtb, off) == region;
        if (!ok) {
            fprintf(stderr, "%s: %s does not read back as %s\n", kTag, vendor_boot,
                    region.c_str());
            break;
        }
        printf("%s: set %zu of %zu dtbs to %s\n", kTag, mismatches, offsets.size(),
               region.c_str());
        ret = 0;
    } while (false);
    close(fd);
    return ret;
}

// update_engine runs it as: <program> <target slot> <status fd> [1]
int main(int argc, char** argv) {
    setvbuf(stdout, nullptr, _IOLBF, 0);
    if (argc < 2 || (strcmp(argv[1], "0") != 0 && strcmp(argv[1], "1") != 0)) {
        fprintf(stderr, "%s: bad target slot\n", kTag);
        return 1;
    }
    std::string vendor_boot = std::string(kVendorBoot) + (argv[1][0] == '0' ? "_a" : "_b");
    return Run(kRunningFdt, vendor_boot.c_str());
}
