#
# Copyright (C) 2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from those products. Most specific first.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base.mk)

# Inherit from TB710FU device
$(call inherit-product, device/lenovo/TB710FU/device.mk)

# Inherit some common PixelOS stuff.
$(call inherit-product, vendor/custom/config/common_full_tablet_wifionly.mk)

PRODUCT_NAME := custom_TB710FU
PRODUCT_DEVICE := TB710FU
PRODUCT_MANUFACTURER := Lenovo
PRODUCT_BRAND := Lenovo
PRODUCT_MODEL := TB710FU
PRODUCT_CHARACTERISTICS := nosdcard,tablet

PRODUCT_GMS_CLIENTID_BASE := android-lenovo

# Report a Pixel release-keys build like Evolution X did on this tablet,
# instead of custom_TB710FU/.../eng.<user>:user/test-keys. PropImitationHooks
# still spoof the certified Pixel props for Play services per process.
PRODUCT_BUILD_PROP_OVERRIDES += \
    BuildDesc="bluejay_beta-user CANARY ZP11.260918.007 16484274 release-keys" \
    BuildFingerprint=google/bluejay_beta/bluejay:CANARY/ZP11.260918.007/16484274:user/release-keys \
    DeviceName=TB710FU \
    DeviceProduct=TB710FU \
    SystemDevice=TB710FU \
    SystemName=TB710FU
