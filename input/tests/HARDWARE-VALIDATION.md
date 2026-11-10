# TB710FU live pen refresh validation

Tested on 2026-11-10, personal-release build `1794335079`, with a real Lenovo
Tab Pen Pro. The tablet retained its user data and the separate stock ROW
Novatek revision 0x16 firmware experiment. That firmware replacement alone had
previously failed to restore drawing at 144 Hz. This PR includes no firmware
replacement; the original vendor revision 0x1a was not retested in this run.

The saved settings were `min_refresh_rate=0.0`, `peak_refresh_rate=144.0`.
The affected display was observed at 144 Hz before pen entry. Input logs,
controller logcat and repeated `dumpsys display` snapshots showed:

| Relative sample time | Stylus vote | Physical display rate |
| --- | --- | --- |
| 0.0 s | absent | 144.00002 Hz |
| 7.8 s | active, ceiling 120 | 120.00001 Hz |
| 40.2 s | absent after lift-away | 144.00002 Hz |
| 51.3 s | active on another entry | 120.00001 Hz |
| 56.2 s | absent after lift-away | 144.00002 Hz |

The controller logged activation on the known touchscreen scan 249. The capture
contained 7 transient key-249 downs and 7,090 real pen frames across 10 contact
downs. Pen frames spanned 46.407 seconds including gaps between strokes. The user
reported that drawing worked immediately and continuously on entry from 144 Hz.
The prior sustained key-249 failure pattern did not occur during these strokes.
A separate baseline at the previous saved 120 Hz cap recorded 7,034 pen frames
across 29.541 seconds and also received a continuous-drawing report.

A timed fallback was armed for testing and cancelled after the successful run.
Final saved settings remain the original adaptive minimum 0 and maximum 144;
the transient pen vote now supplies the 120 Hz limit during pen use. No app data
or tablet userdata was cleared, and no touchscreen HAL commands were added by
this display handler.

This establishes short-session entry, renewal, and release on the installed
build. It does not establish long-idle/suspend reliability, the original firmware
variant, screen-off cleanup on hardware, or behavior on other display hardware.
Host tests cover the controller's screen transitions; Android policy tests cover
lower user ceilings and vote precedence.
