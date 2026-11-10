#!/usr/bin/env python3
"""Run the production transient stylus controller with a deterministic clock/handler."""
from pathlib import Path
import shutil
import subprocess
import tempfile

production = Path(__file__).resolve().parents[1] / 'src/com/tb520fu/input/PenRefreshRate.java'
sources = {
    'android/os/SystemClock.java': '''
package android.os;
public class SystemClock {
    public static long now;
    public static long uptimeMillis() { return now; }
}
''',
    'android/os/Handler.java': '''
package android.os;
import java.util.*;
public class Handler {
    record Task(Runnable callback, long time, long sequence) {}
    public final List<Task> tasks = new ArrayList<>();
    long sequence;
    public boolean post(Runnable r) { return postAtTime(r, SystemClock.now); }
    public boolean postDelayed(Runnable r, long delay) {
        return postAtTime(r, SystemClock.now + delay);
    }
    public boolean postAtTime(Runnable r, long time) {
        tasks.add(new Task(r, time, sequence++)); return true;
    }
    public void removeCallbacks(Runnable r) { tasks.removeIf(t -> t.callback == r); }
    public void drain() {
        for (;;) {
            Task next = tasks.stream().filter(t -> t.time <= SystemClock.now)
                .min(Comparator.comparingLong(Task::time).thenComparingLong(Task::sequence))
                .orElse(null);
            if (next == null) return;
            tasks.remove(next); next.callback.run();
        }
    }
}
''',
    'android/content/Context.java': '''
package android.content;
public class Context {
    public <T> T getSystemService(Class<T> type) { return null; }
    public void registerReceiver(Object receiver, IntentFilter filter, String permission,
            android.os.Handler handler) {}
}
''',
    'android/content/Intent.java': '''
package android.content;
public class Intent {
    public static final String ACTION_SCREEN_ON = "on", ACTION_SCREEN_OFF = "off";
    public String getAction() { return ACTION_SCREEN_ON; }
}
''',
    'android/content/IntentFilter.java': '''
package android.content;
public class IntentFilter { public void addAction(String action) {} }
''',
    'android/hardware/display/DisplayManagerInternal.java': '''
package android.hardware.display;
public class DisplayManagerInternal {}
''',
    'android/os/PowerManager.java': '''
package android.os;
public class PowerManager { public boolean isInteractive() { return true; } }
''',
    'android/view/Display.java': '''
package android.view;
public class Display { public static final int DEFAULT_DISPLAY = 0; }
''',
    'android/util/Log.java': '''
package android.util;
public class Log {
    public static int i(String tag, String message) { return 0; }
    public static int w(String tag, String message, Throwable error) { return 0; }
}
''',
    'com/tb520fu/input/Safe.java': '''
package com.tb520fu.input;
class Safe {
    static Object receiver(String name,
            java.util.function.BiConsumer<android.content.Context,android.content.Intent> r) {
        return r;
    }
}
''',
    'com/tb520fu/input/PenRefreshTest.java': '''
package com.tb520fu.input;
import android.os.Handler;
import android.os.SystemClock;
import java.util.*;
public class PenRefreshTest {
    static int assertions;
    static void check(boolean condition, String reason) {
        if (!condition) throw new AssertionError(reason);
        assertions++;
    }
    static class Backend implements PenRefreshRate.Backend {
        final List<Float> limits = new ArrayList<>();
        boolean failApply, failClear;
        public void setLimit(float hz) {
            if ((hz == 0 && failClear) || (hz != 0 && failApply)) {
                throw new IllegalStateException("simulated backend failure");
            }
            limits.add(hz);
        }
    }
    static void at(Handler handler, long time) { SystemClock.now = time; handler.drain(); }
    public static void main(String[] ignored) {
        SystemClock.now = 0;
        Handler h = new Handler(); Backend b = new Backend();
        PenRefreshRate policy = new PenRefreshRate(h, b);
        check(b.limits.isEmpty(), "boot does not cap the display");
        policy.onStylusActivity();
        check(b.limits.isEmpty(), "input policy thread never calls display service inline");
        h.drain();
        check(b.limits.equals(List.of(120f)), "first proximity event arms 120 Hz");
        for (int i = 0; i < 80; i++) policy.onStylusActivity();
        check(h.tasks.size() == 1, "same-time key flood cannot flood the handler");
        at(h, 1999);
        check(b.limits.equals(List.of(120f)), "vote survives until idle timeout");
        policy.onStylusActivity(); h.drain();
        check(b.limits.equals(List.of(120f)), "ongoing motion renews without redundant vote writes");
        at(h, 2000);
        check(b.limits.equals(List.of(120f)), "old timeout is cancelled after motion");
        at(h, 3999);
        check(b.limits.equals(List.of(120f, 0f)), "idle removes only the transient vote");

        at(h, 4100); policy.onStylusActivity(); h.drain();
        policy.setInteractive(true);
        at(h, 6100);
        check(b.limits.equals(List.of(120f, 0f, 120f, 0f)),
                "duplicate screen-on does not orphan an active vote");
        at(h, 6200); policy.onStylusActivity(); h.drain();
        policy.setInteractive(false);
        check(b.limits.getLast() == 0f, "screen off releases immediately");
        int writes = b.limits.size();
        at(h, 6300); policy.onStylusActivity(); h.drain();
        check(b.limits.size() == writes, "screen-off input cannot cap display");

        at(h, 6400); policy.onStylusActivity();
        SystemClock.now = 6401; policy.setInteractive(true); h.drain();
        check(b.limits.size() == writes, "queued activity predating screen-on is ignored");
        policy.onStylusActivity(); h.drain();
        check(b.limits.getLast() == 120f, "first new activity after wake is immediate");
        at(h, 6500); policy.setInteractive(false);
        check(b.limits.getLast() == 0f, "second screen-off clears again");

        at(h, 6600); policy.setInteractive(true); policy.onStylusActivity();
        SystemClock.now = 9000; h.drain();
        check(b.limits.getLast() == 0f, "stale input after a blocked worker cannot arm the vote");

        b.failApply = true;
        policy.onStylusActivity(); h.drain();
        check(b.limits.getLast() == 0f, "backend apply failure does not claim an active vote");
        b.failApply = false;
        at(h, 9100); policy.onStylusActivity(); h.drain();
        check(b.limits.getLast() == 120f, "a later hint recovers after backend failure");
        b.failClear = true; at(h, 11100);
        check(b.limits.getLast() == 120f, "clear failure retains ownership for retry");
        check(h.tasks.size() == 1, "clear failure schedules one bounded retry");
        b.failClear = false; at(h, 11600);
        check(b.limits.getLast() == 0f, "retry releases the vote");
        check(h.tasks.isEmpty(), "successful release leaves no work queued");
        at(h, 12000); policy.onStylusActivity(); h.drain();
        b.failClear = true; policy.setInteractive(false);
        check(h.tasks.size() == 1, "screen-off clear failure has a pending retry");
        b.failClear = false;
        SystemClock.now = 12001; policy.setInteractive(true);
        check(b.limits.getLast() == 0f, "wake completes a failed screen-off release");
        check(h.tasks.isEmpty(), "wake cannot orphan the failed clear or its timer");
        System.out.println("PASS: " + assertions + " pen-refresh assertions");
    }
}
''',
}

with tempfile.TemporaryDirectory(prefix='tb710fu-pen-refresh-') as directory:
    root = Path(directory)
    for name, content in sources.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    shutil.copyfile(production, root / 'com/tb520fu/input/PenRefreshRate.java')
    classes = root / 'classes'
    subprocess.run(['javac', '-d', str(classes), *map(str, root.rglob('*.java'))], check=True)
    subprocess.run(['java', '-cp', str(classes), 'com.tb520fu.input.PenRefreshTest'], check=True)
