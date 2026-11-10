# Lenovo pen display timing

On TB710FU, the Tab Pen Pro can produce only a brief hover or sporadic contacts
when the built-in display runs at 144 Hz. The touchscreen then repeatedly emits
scan code 249 instead of sustained pen input. Bluetooth can remain connected.
Changing the display to 120 Hz restores drawing without resetting user data.

The stock ROW input dispatcher routes scan 249 and ordinary stylus motion to
SurfaceFlinger hints 120 and 119. Stock SurfaceFlinger uses these to reset a pen
timer and replace a 144/165 Hz selection with a 120 Hz pen mode. These hints are
not touchscreen-HAL acknowledgements. The stock timer's configured duration has
not been established.

`PenRefreshRate` implements the required behavior through display-mode votes:

- The existing NVT scan-249 handler activates the limit before usable pen motion.
- The default-display stylus monitor renews it for stylus and eraser motion,
  including long strokes and hover moves. Finger and mouse events do not renew it.
- A two-second quiet period or screen-off clears the vote. Two seconds is this
  implementation's debounce choice, not a claimed stock constant.
- The vote caps physical refresh at 120 Hz on display 0. It does not change
  `min_refresh_rate`, `peak_refresh_rate`, or any other user setting. Removing
  the vote restores the existing policy, including eligibility for 144 Hz.
- Lower user limits and higher-priority layout, low-power, thermal and
  fingerprint constraints remain effective. Other displays receive no vote.

The framework support is in
`patches/frameworks_base-0010-transient-stylus-refresh-limit.patch`, applied by
`patches/apply.sh`. The device jar resolves the local display service once at
startup. If the framework patch is absent, it logs that the feature is unavailable;
it does not fall back to overwriting user preferences.

## Validation

From the device repository:

```sh
python3 input/tests/run_pen_type_tests.py
python3 input/tests/run_pen_refresh_tests.py
```

From the Android source root:

```sh
bash device/lenovo/TB710FU/patches/apply.sh
m tb520fu-input DisplayServiceTests -j10
atest DisplayServiceTests:com.android.server.display.mode.DisplayModeDirectorTest
```

The controller tests compile the production classes with deterministic Android
and HAL doubles. They check early scan-249 activation, device filtering, expiry,
renewal, screen transitions, bounded posting, stale input and backend failures.
The framework tests check vote precedence, lower user caps, per-display scope,
vote removal and invalid requests.

After installing a build containing both parts, validate on hardware:

1. Save the user's refresh-rate settings. Remove a previous manual 120 Hz
   workaround only on the updated build, and allow 144 Hz through normal settings.
2. Bring the pen near the display. Check `adb logcat -s TB520FUPenRefresh` and
   `adb shell dumpsys display` for the transient `PRIORITY_STYLUS` vote and a
   physical rate no higher than 120 Hz. Verify sustained drawing for over two seconds.
3. Lift the pen and wait two seconds. The vote should disappear; normal activity
   can select 144 Hz again. An idle screen may naturally choose a lower rate.
4. Check that a user-selected 60 Hz ceiling stays at 60 Hz, and that screen-off
   removes the vote. Verify an external display is unaffected.

The 50 host assertions pass, and `m tb520fu-input DisplayServiceTests -j10`
completed successfully. The four new display-mode tests and 11 existing voting regression tests passed
on the tablet. The full display-mode class could not complete because unrelated
observer tests require cross-user permission unavailable to the test APK on the
release ROM.

A short live test on release build 1794335079 verified real pen entry from
144 Hz, scan-249 activation of the ceiling, sustained drawing at 120 Hz, and
return to 144 Hz after lift-away. The user confirmed immediate, continuous
drawing. See `tests/HARDWARE-VALIDATION.md` for evidence and scope. The device
retained the separate ROW-touch16 firmware experiment; this PR changes no firmware.
Long-idle and suspend recurrence still need normal-use validation.
