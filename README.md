# Lenovo Xiaoxin Pad Pro GT (TB710FU): PixelOS device tree

Unofficial device tree for building PixelOS 17 (Android 17, branch `seventeen`)
for the Lenovo Xiaoxin Pad Pro GT / Yoga Tab 11.1 AI (TB710FU, Snapdragon 8 Gen 3).

Maintainer: [Buffersolve](https://github.com/Buffersolve)

> **Status: boots and is used daily.** Builds are unofficial. Keep a way to
> restore the stock firmware (EDL) before flashing.

| | |
|---|---|
| SoC | Qualcomm SM8650 (pineapple) |
| Kernel | GKI `android14-6.1` (KMI 11), built from source |
| Display | NT36532 dual-DSI DSC, 3200×2000, `ORIENTATION_270` (reported as 2000×3200), density 400, 30/60/90/120/144 Hz |
| Touch | Novatek NVT-ts (SPI), pen support |
| Audio amp | Awinic aw882xx |
| Stock firmware | `TB710FU_CN_OPEN_USER_Q00019.0_A16_ZUXOS_1.5.04.470_ST_260625` (PRC) |
| Board API level | 34 |
| Super partition | 20401094656 bytes (group 19318964224) |

## Based on

This tree is a fork of the TB710FU tree by
[sungwon1002](https://github.com/sungwon1002/android_device_lenovo_TB710FU),
a port of the TB520FU (Lenovo Yoga Tab Plus) tree by
[wnduddld0513](https://github.com/wnduddld0513/android_device_lenovo_TB520FU),
which is itself based on the LineageOS OnePlus Pad 2 (`caihong`) and
`oneplus/sm8650-common` trees. Copyright headers of the original files are kept.

Changes on top of the sungwon1002 tree (see the git log for details):

- PixelOS product makefile `custom_TB710FU.mk`; recovery fstab without
  `/vendor/firmware_mnt`, so sideloading the zip from recovery works.
- Pixel Launcher patched at build time (`lenovo/NexusLauncher`): dock position
  after swipe home, transient taskbar that could stay open, home state after a
  quick switch, search bar return animation without a second taskbar copy.
- Lenovo input bridge (`tb520fu-input`: pen, keyboard, folio, double tap to wake)
  is actually loaded on PixelOS.
- zram swap is loaded again; Parts hides Memory extension, which needs kernel
  zram writeback.
- LunarisDolby from the lenovo-sm8650 tree (Dolby on/off works).
- No half-screen flicker at 144 Hz (`vendor.display.disable_idle_fps_switch`).
- PenService no longer crashes without the ZUI notification service.
- Stock Lenovo build fingerprint, sepolicy and log spam fixes.
- Smart Accessories (ZUI UDevice) is kept out of the quick settings Active apps list.
- Maintainer row in Settings > About tablet (`ro.custom.maintainer`).

## Repositories

| Path | Repository | Branch |
|---|---|---|
| `device/lenovo/TB710FU` | `Buffersolve/android_device_lenovo_TB710FU` | `seventeen` |
| `vendor/lenovo/TB710FU` | `Buffersolve/android_vendor_lenovo_TB710FU` | `seventeen` |
| `kernel/lenovo/TB710FU` | `Buffersolve/android_kernel_lenovo_sm8650` (the lenovo-sm8650 TB520FU kernel, unchanged) | `seventeen` |

The vendor repository holds the proprietary blobs plus the stock dtb, dtbo and
vendor kernel modules in `kernel/`. Git LFS is not used: `PenService.apk` is
larger than the GitHub file limit, so it is stored in parts that the build
joins back together (the `PenService-stock` genrule in the vendor `Android.bp`).

## Getting the source

```bash
mkdir pixelos && cd pixelos
repo init -u https://github.com/PixelOS-AOSP/android_manifest -b seventeen --git-lfs
mkdir -p .repo/local_manifests
curl -L https://raw.githubusercontent.com/Buffersolve/android_device_lenovo_TB710FU/seventeen/tools/local_manifest.xml \
  -o .repo/local_manifests/TB710FU.xml
repo sync -c -j$(nproc) --force-sync --no-clone-bundle --no-tags
```

## Building

```bash
device/lenovo/TB710FU/tools/build.sh
```

The script applies the source patches from `patches/` (`patches/apply.sh`, see
below), runs `breakfast TB710FU user` and `m pixelos`, logging to `build.log`.
By hand:

```bash
bash device/lenovo/TB710FU/patches/apply.sh
source build/envsetup.sh
breakfast TB710FU user
m pixelos
```

The result is `out/target/product/TB710FU/PixelOS_TB710FU-17.0-<date>.zip`.
32 GB of RAM is recommended; with 16 GB use a large swap and `-j8` or less.

## Source patches

`patches/` holds patches for PixelOS repositories (frameworks, Settings, Dolby,
camera and others) that the device needs. `patches/apply.sh` applies them with
`git apply` without committing, skips the ones already applied and records what
it applied, so it is safe to run before every build. `repo sync` resets the
patched repositories, so run it again after syncing.

## Installing

1. Flash the PixelOS recovery from the build to both slots:
   `fastboot flash recovery_a recovery.img` and `fastboot flash recovery_b recovery.img`.
2. Boot to recovery, choose Apply update > Apply from ADB and run
   `adb sideload PixelOS_TB710FU-17.0-<date>.zip`.
3. Coming from stock or another ROM, format data in recovery.

## Extracting blobs

```bash
./extract-files.py <dump>
```

`<dump>` is an extracted stock firmware containing `vendor/`, `odm/`,
`system_ext/`, `product/` and `pvmfw.img`. A full extraction clears the vendor
repository, so restore the stock kernel files afterwards with
`git -C ../../../vendor/lenovo/TB710FU checkout -- kernel`. `setup-makefiles.py`
regenerates the vendor `Android.bp` with a plain `PenService-stock` filegroup;
split the APK again and keep the genrule before committing.

## Verified boot

Images are signed with the public AOSP `testkey_rsa4096`, like the stock
firmware. Do not relock the bootloader.

## Credits

- [sungwon1002](https://github.com/sungwon1002) for the TB710FU tree and blobs
- [wnduddld0513](https://github.com/wnduddld0513) for the TB520FU tree and kernel
- The LineageOS project
- The PixelOS project
