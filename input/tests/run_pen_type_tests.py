#!/usr/bin/env python3
"""Exercise the production pen policy with deterministic Android/HAL doubles."""
from pathlib import Path
import shutil
import subprocess
import tempfile

production = Path(__file__).resolve().parents[1] / "src/com/tb520fu/input/PenStylusMode.java"
sources = {
    "android/content/Context.java": """
package android.content;
public class Context {
    public final ContentResolver resolver = new ContentResolver();
    public ContentResolver getContentResolver() { return resolver; }
}
""",
    "android/content/ContentResolver.java": """
package android.content;
public class ContentResolver {
    public java.util.function.Consumer<Object> observer;
    public void registerContentObserver(Object uri, boolean descendants,
            java.util.function.Consumer<Object> callback) { observer = callback; }
    public void changed() { observer.accept(null); }
}
""",
    "android/os/Handler.java": """
package android.os;
public class Handler {}
""",
    "android/os/SystemClock.java": """
package android.os;
public class SystemClock {
    public static long now;
    public static long uptimeMillis() { return now; }
}
""",
    "android/provider/Settings.java": """
package android.provider;
public class Settings {
    public static class Global {
        public static Integer override;
        public static Object getUriFor(String key) { return key; }
        public static int getInt(android.content.ContentResolver resolver, String key, int fallback) {
            return override == null ? fallback : override;
        }
    }
}
""",
    "android/util/Log.java": """
package android.util;
public class Log {
    public static final java.util.List<String> info = new java.util.ArrayList<>();
    public static final java.util.List<String> warnings = new java.util.ArrayList<>();
    public static final java.util.List<String> debug = new java.util.ArrayList<>();
    public static int i(String tag, String message) { info.add(message); return 0; }
    public static int w(String tag, String message) { warnings.add(message); return 0; }
    public static int d(String tag, String message) { debug.add(message); return 0; }
}
""",
    "android/view/InputDevice.java": """
package android.view;
public class InputDevice {
    private final String name;
    public InputDevice(String name) { this.name = name; }
    public String getName() { return name; }
}
""",
    "android/view/KeyEvent.java": """
package android.view;
public class KeyEvent {
    public static final int ACTION_DOWN = 0, ACTION_UP = 1;
    private final int scan, action;
    private final InputDevice device;
    public KeyEvent(int scan, int action, InputDevice device) {
        this.scan = scan; this.action = action; this.device = device;
    }
    public int getScanCode() { return scan; }
    public int getAction() { return action; }
    public InputDevice getDevice() { return device; }
}
""",
    "com/tb520fu/input/Doubles.java": """
package com.tb520fu.input;
class PenController {
    static final int TYPE_PARKER = 2, TYPE_PICASSO = 1;
}
class LenovoHal {
    static final java.util.List<Integer> writes = new java.util.ArrayList<>();
    static String reply = "true";
    static String setPenType(int type) { writes.add(type); return reply; }
}
class Safe {
    static void post(android.os.Handler handler, String reason, Runnable callback) { callback.run(); }
    static java.util.function.Consumer<Object> observer(android.os.Handler handler, String reason,
            java.util.function.Consumer<Object> callback) { return callback; }
}
""",
    "com/tb520fu/input/PenTypeTest.java": """
package com.tb520fu.input;
import android.content.Context;
import android.os.Handler;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;
import android.view.InputDevice;
import android.view.KeyEvent;
public class PenTypeTest {
    static int assertions;
    static void check(boolean condition, String why) {
        if (!condition) throw new AssertionError(why);
        assertions++;
    }
    public static void main(String[] args) {
        Context context = new Context();
        int[] refreshHints = {0};
        PenStylusMode policy = new PenStylusMode(context, new Handler(), () -> refreshHints[0]++);
        policy.start();
        check(LenovoHal.writes.isEmpty(), "boot must leave the panel unchanged");
        policy.onPenConnected(PenController.TYPE_PARKER);
        check(LenovoHal.writes.equals(java.util.List.of(5)), "Parker Bluetooth 2 must configure TP 5");
        check(Log.info.getLast().contains("proc write accepted"), "successful proc reply is reported");

        Settings.Global.override = 0;
        context.resolver.changed();
        check(LenovoHal.writes.getLast() == 0, "explicit override 0 remains valid");
        Settings.Global.override = 99;
        context.resolver.changed();
        check(LenovoHal.writes.getLast() == 5, "invalid override falls back to connected model");
        Settings.Global.override = null;
        context.resolver.changed();
        check(LenovoHal.writes.getLast() == 5, "deleting override restores model type");
        policy.onPenDisconnected();
        int previous = LenovoHal.writes.size();
        context.resolver.changed();
        check(LenovoHal.writes.size() == previous, "setting changes while disconnected must not write");

        policy.onPenConnected(PenController.TYPE_PICASSO);
        check(LenovoHal.writes.getLast() == 2, "Picasso Bluetooth 1 must configure TP 2");
        previous = LenovoHal.writes.size();
        policy.onPenConnected(4);
        check(LenovoHal.writes.size() == previous, "unestablished model mapping must not be invented");
        Settings.Global.override = 5;
        context.resolver.changed();
        check(LenovoHal.writes.getLast() == 5, "explicit override works for an unconfigured model");
        Settings.Global.override = -2;
        previous = LenovoHal.writes.size();
        context.resolver.changed();
        check(LenovoHal.writes.size() == previous, "invalid override on unknown model must not write");

        Settings.Global.override = null;
        for (String reply : new String[] {"false", null}) {
            LenovoHal.reply = reply;
            int successes = Log.info.size();
            policy.onPenConnected(PenController.TYPE_PARKER);
            check(Log.info.size() == successes, "failed or absent HAL reply must not log success");
            check(Log.warnings.getLast().contains("proc write failed"), "failed reply is visible");
        }

        InputDevice panel = new InputDevice("NVTCapacitiveTouchScreen");
        previous = LenovoHal.writes.size();
        int debug = Log.debug.size();
        SystemClock.now = 0;
        check(policy.handle(new KeyEvent(249, KeyEvent.ACTION_DOWN, panel)), "consume stylus-state down");
        check(refreshHints[0] == 1, "scan 249 activates the display policy before any pen motion");
        check(policy.handle(new KeyEvent(249, KeyEvent.ACTION_UP, panel)), "consume stylus-state up");
        check(refreshHints[0] == 1, "key release does not extend the display vote");
        for (int i = 0; i < 80; i++) {
            SystemClock.now = i * 10;
            policy.handle(new KeyEvent(249, KeyEvent.ACTION_DOWN, panel));
        }
        check(Log.debug.size() == debug + 1, "frame flood should log at most once per second");
        check(refreshHints[0] == 81, "all proximity downs reach the throttled display controller");
        check(LenovoHal.writes.size() == previous, "scan 249 must not trigger speculative HAL writes");
        check(!policy.handle(new KeyEvent(249, KeyEvent.ACTION_DOWN, new InputDevice("keyboard"))),
                "do not consume another device's scan code");
        check(!policy.handle(new KeyEvent(248, KeyEvent.ACTION_DOWN, panel)), "do not consume unrelated keys");
        check(!policy.handle(new KeyEvent(249, KeyEvent.ACTION_DOWN, null)), "handle missing device safely");
        check(refreshHints[0] == 81, "unrelated keys/devices do not activate the display vote");
        System.out.println("PASS: " + assertions + " pen-policy assertions");
    }
}
""",
}

with tempfile.TemporaryDirectory(prefix="tb710fu-pen-type-") as directory:
    root = Path(directory)
    for name, source in sources.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    shutil.copyfile(production, root / "com/tb520fu/input/PenStylusMode.java")
    classes = root / "classes"
    subprocess.run(["javac", "-d", str(classes), *map(str, root.rglob("*.java"))], check=True)
    subprocess.run(["java", "-cp", str(classes), "com.tb520fu.input.PenTypeTest"], check=True)
