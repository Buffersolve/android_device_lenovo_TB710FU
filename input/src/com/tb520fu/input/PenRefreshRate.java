/*
 * SPDX-FileCopyrightText: 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package com.tb520fu.input;

import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.hardware.display.DisplayManagerInternal;
import android.os.Handler;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.Log;
import android.view.Display;

import java.lang.reflect.Method;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Keeps the built-in display within the pen's working range during proximity/drawing.
 *
 * Stock routes touchscreen scan 249 and stylus motion to a SurfaceFlinger pen timer,
 * which selects 120 Hz instead of 144/165 Hz. Use a transient display-policy vote
 * here: no user settings are changed, and a quiet or sleeping display loses the vote.
 */
final class PenRefreshRate {
    private static final String TAG = "TB520FUPenRefresh";
    static final float MAX_REFRESH_RATE = 120f;
    // A local debounce choice; the stock timer's configured interval is unknown.
    static final long IDLE_TIMEOUT_MS = 2000;
    static final long HINT_INTERVAL_MS = 100;
    private static final long RELEASE_RETRY_MS = 500;

    interface Backend {
        /** Zero clears this controller's vote. */
        void setLimit(float maxRefreshRate);
    }

    private final Context mContext;
    private final Handler mHandler;
    private final AtomicLong mLastPosted = new AtomicLong(-HINT_INTERVAL_MS);
    private volatile Backend mBackend;
    // Worker handler only.
    private boolean mInteractive = true;
    private boolean mLimited;
    private long mInteractiveSince;
    private final Runnable mRelease = this::release;

    PenRefreshRate(Context context, Handler handler) {
        mContext = context;
        mHandler = handler;
    }

    /** Test constructor: the production state machine runs with a recording vote backend. */
    PenRefreshRate(Handler handler, Backend backend) {
        this(null, handler);
        mBackend = backend;
    }

    void start() {
        try {
            // LocalServices is in services.jar. Resolve it once so the device jar
            // can still compile on ROMs without the optional framework patch.
            Class<?> services = Class.forName("com.android.server.LocalServices");
            Object display = services.getMethod("getService", Class.class)
                    .invoke(null, DisplayManagerInternal.class);
            if (display == null) throw new IllegalStateException("Display service unavailable");
            Method setLimit = DisplayManagerInternal.class.getMethod(
                    "setStylusRefreshRateLimit", int.class, float.class);
            mBackend = limit -> {
                try {
                    setLimit.invoke(display, Display.DEFAULT_DISPLAY, limit);
                } catch (ReflectiveOperationException e) {
                    throw new IllegalStateException("Stylus display vote failed", e);
                }
            };
        } catch (ReflectiveOperationException | RuntimeException e) {
            Log.w(TAG, "Transient stylus display limit unavailable; framework patch required", e);
            return;
        }

        PowerManager power = mContext.getSystemService(PowerManager.class);
        setInteractive(power != null && power.isInteractive());
        IntentFilter filter = new IntentFilter();
        filter.addAction(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_SCREEN_OFF);
        mContext.registerReceiver(Safe.receiver("pen display state", (context, intent) ->
                setInteractive(Intent.ACTION_SCREEN_ON.equals(intent.getAction()))),
                filter, null, mHandler);
    }

    /** Cheap, bounded posting from either input policy or the stylus monitor thread. */
    void onStylusActivity() {
        if (mBackend == null) return;
        long now = SystemClock.uptimeMillis();
        long previous = mLastPosted.get();
        if (now - previous < HINT_INTERVAL_MS || !mLastPosted.compareAndSet(previous, now)) return;
        mHandler.post(() -> apply(now));
    }

    private void apply(long eventTime) {
        if (!mInteractive || eventTime < mInteractiveSince
                || SystemClock.uptimeMillis() - eventTime >= IDLE_TIMEOUT_MS) return;
        if (!mLimited) {
            try {
                mBackend.setLimit(MAX_REFRESH_RATE);
                mLimited = true;
                Log.i(TAG, "Stylus display ceiling enabled: 120 Hz");
            } catch (RuntimeException e) {
                Log.w(TAG, "Could not enable stylus display ceiling", e);
                return;
            }
        }
        mHandler.removeCallbacks(mRelease);
        mHandler.postAtTime(mRelease, eventTime + IDLE_TIMEOUT_MS);
    }

    /** Handler thread only. Also invalidates input posted before the current screen state. */
    void setInteractive(boolean interactive) {
        if (mInteractive == interactive) return;
        mInteractive = interactive;
        mInteractiveSince = SystemClock.uptimeMillis();
        mLastPosted.set(-HINT_INTERVAL_MS);
        mHandler.removeCallbacks(mRelease);
        // A failed screen-off clear must not lose its retry when the screen wakes.
        if (!interactive || mLimited) release();
    }

    private void release() {
        if (!mLimited) return;
        try {
            mBackend.setLimit(0);
            mLimited = false;
            Log.i(TAG, "Stylus display ceiling released");
        } catch (RuntimeException e) {
            Log.w(TAG, "Could not release stylus display ceiling; retrying", e);
            mHandler.postDelayed(mRelease, RELEASE_RETRY_MS);
        }
    }
}
