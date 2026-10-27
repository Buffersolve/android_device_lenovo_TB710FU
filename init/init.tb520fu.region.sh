#!/vendor/bin/sh
#
# SPDX-FileCopyrightText: 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Region of the running dtb (region_country), which the bootloader has checked
# against the region of the board: PRC or ROW. init.tb520fu.region.rc sets the
# properties that differ between the PRC and ROW firmware from it.

region=$(tr -d '\000' < /sys/firmware/devicetree/base/region_country)
case "$region" in
    PRC|ROW) ;;
    *) region=unknown ;;
esac
setprop ro.vendor.tb520fu.dtb_region "$region"
