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
| Stock firmware | `TB710FU_CN_OPEN_USER_Q00019.0_A16_ZUXOS_1.5.04.470_ST_260625` (PRC); runs on PRC and ROW tablets, see [PRC and ROW tablets](#prc-and-row-tablets) |
| Board API level | 34 |
| Super partition | 20401094656 bytes (group 19318964224) |

## Downloads

Builds are on SourceForge: [pixelos-tb710fu/TB710FU](https://sourceforge.net/projects/pixelos-tb710fu/files/TB710FU/). Each build has its
own folder with the zip, the matching `recovery.img` and `sha256sums.txt`; see
[Installing](#installing). Installed builds get later builds through the
built-in Updater.

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

Download the zip and `recovery.img` of one build from [SourceForge](https://sourceforge.net/projects/pixelos-tb710fu/files/TB710FU/).

1. Flash the PixelOS recovery from the build to both slots:
   `fastboot flash recovery_a recovery.img` and `fastboot flash recovery_b recovery.img`.
2. Boot to recovery, choose Apply update > Apply from ADB and run
   `adb sideload PixelOS_TB710FU-17.0-<date>.zip`.
3. Coming from stock or another ROM, format data in recovery.

Install only from recovery or the Updater, not by flashing the images with
fastboot: see [PRC and ROW tablets](#prc-and-row-tablets).

## PRC and ROW tablets

The same build works on PRC (China) and ROW (global) tablets. The bootloader
compares the `region_country` of the dtb in `vendor_boot` ("PRC" or "ROW")
with the region of the board (`devinfo`) and powers the tablet off with "The
current system is not compatible with hardware" when they differ. The stock PRC
and ROW dtbs are otherwise identical (as are the kernel, `vendor_boot` ramdisk
and `dtbo`), so the build ships the PRC one and the `system_ext` postinstall
step (`postinstall/tb520fu_region_postinstall.cpp`) sets the dtb of the new
slot to the region of the running one, which the bootloader has accepted. If
it fails, the update is not applied and the current slot stays active.

At boot, `init.tb520fu.region.sh` reads the region of the running dtb and
`init.tb520fu.region.rc` sets what differs between the PRC and ROW firmware:
`ro.product.name_for_attestation` (`TB710FU_PRC` / `TB710FU`) and the Lenovo
market name.

The recovery shows the region in its title. Advanced > Repair region of other
slot sets the dtb of the inactive slot to it, e.g. when a build made before
this support was installed there on a ROW tablet.

Recovery from a slot with the dtb of the other region:

- One slot still boots (e.g. the stock firmware): select it with
  `fastboot --set-active=<slot>`, then either install a build from recovery or
  use Repair region of other slot and switch back to the repaired slot.
- No slot boots: the recovery boots with the dtb of the active slot too, so
  flash the stock `vendor_boot.img` of the tablet's region to it
  (`fastboot flash vendor_boot_<slot> vendor_boot.img`), boot to recovery and
  install a build: it gets the region of the stock dtb.

## OTA updates

Unofficial builds include the PixelOS Updater (`net.pixelos.ota`), pointed by
`overlay/UpdaterResTB710FU` at
[Buffersolve/PixelOS_TB710FU_OTA](https://github.com/Buffersolve/PixelOS_TB710FU_OTA);
the zips are hosted on SourceForge. To publish a build:

```bash
SF_PROJECT=pixelos-tb710fu SF_USER=<user> device/lenovo/TB710FU/tools/ota_release.sh \
    out/target/product/TB710FU/PixelOS_TB710FU-17.0-<date>.zip changelog.md
```

It uploads the zip, the `recovery.img` next to it and a `sha256sums.txt` to
`TB710FU/<date>/` of the SourceForge project (leave out `SF_USER` if they are
already uploaded), writes the feed entry with
`packages/apps/Updater/tools/pixelos_feed.py` and the changelog, and pushes the
OTA repository. Updates must be signed with the same keys as the installed
build.

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

## Signing

Released builds are signed with private release keys (inline signing from
`vendor/lineage-priv/keys`, which is not part of any repository). Without that
directory the build uses the public test keys. Builds with different keys
cannot be installed over each other without formatting data.

## Verified boot

Images are signed with the public AOSP `testkey_rsa4096`, like the stock
firmware. Do not relock the bootloader.

## Credits

- [sungwon1002](https://github.com/sungwon1002) for the TB710FU tree and blobs
- [wnduddld0513](https://github.com/wnduddld0513) for the TB520FU tree and kernel
- The LineageOS project
- The PixelOS project
