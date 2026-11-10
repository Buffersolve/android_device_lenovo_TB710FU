/*
 * SPDX-FileCopyrightText: 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package com.tb520fu.input;

import android.content.ContentResolver;
import android.content.Context;
import android.os.Handler;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;
import android.view.InputDevice;
import android.view.KeyEvent;

/**
 * Configures the touch firmware's pen type and consumes its stylus-state key.
 *
 * Stock ROW BluetoothPenConnectPolicy.setConnectedPen() maps Bluetooth Parker
 * type 2 to touchscreen ioctl(3, "5"), and Picasso type 1 to ioctl(3, "2").
 * PenController calls this directly before setPenMode(true)/setPenBle(false).
 * The driver caches pen_type and restores it on resume, so no boot or wake
 * write is needed. Settings.Global tb520fu_pen_type (0-5) remains an explicit
 * diagnostic override; deleting the setting restores the model-specific value.
 *
 * nt36532_ts emits scan code 249 for an enter-stylus-state frame and drops the
 * frame. Stock handles this in native input dispatch, requesting the 120 Hz
 * pen display policy through SurfaceFlinger. Arm our transient display ceiling
 * and consume the key here; pen_type is not its firmware acknowledgement.
 */
final class PenStylusMode {
    private static final String TAG = "TB520FUStylusMode";

    static final String SETTING = "tb520fu_pen_type";
    private static final int TYPE_UNCONFIGURED = -1;
    private static final int TP_PARKER = 5;
    private static final int TP_PICASSO = 2;
    private static final int MAX_TYPE = 5;

    private static final int SCAN_ENTER_STYLUS = 249;
    private static final String TOUCH_DEVICE = "NVTCapacitiveTouchScreen";
    private static final long REQUEST_LOG_INTERVAL_MS = 1000;

    private final Context mContext;
    private final Handler mHandler;
    private final Runnable mStylusActivity;

    // Input policy thread only.
    private long mLastRequest = -REQUEST_LOG_INTERVAL_MS;
    // Handler thread only. -1 preserves the firmware default for other models.
    private int mModelType = TYPE_UNCONFIGURED;
    private boolean mConnected;

    PenStylusMode(Context context, Handler handler, Runnable stylusActivity) {
        mContext = context;
        mHandler = handler;
        mStylusActivity = stylusActivity;
    }

    /** Called on the input policy thread; never performs a HAL call. */
    boolean handle(KeyEvent event) {
        if (event.getScanCode() != SCAN_ENTER_STYLUS) return false;
        InputDevice device = event.getDevice();
        if (device == null || !TOUCH_DEVICE.equals(device.getName())) return false;
        if (event.getAction() == KeyEvent.ACTION_DOWN) {
            // This precedes usable stylus motion: the controller requests its
            // compatible display timing with this key while the panel is at 144 Hz.
            mStylusActivity.run();
            long now = SystemClock.uptimeMillis();
            if (now - mLastRequest >= REQUEST_LOG_INTERVAL_MS) {
                mLastRequest = now;
                Safe.post(mHandler, "stylus mode request", () ->
                        Log.d(TAG, "touch firmware requested stylus display timing; scan code 249"));
            }
        }
        return true;
    }

    void start() {
        ContentResolver cr = mContext.getContentResolver();
        cr.registerContentObserver(Settings.Global.getUriFor(SETTING), false,
                Safe.observer(mHandler, "pen type setting", uri -> apply("setting")));
    }

    /** Called on the shared handler before PenController enables pen mode. */
    void onPenConnected(int bluetoothType) {
        mConnected = true;
        switch (bluetoothType) {
            case PenController.TYPE_PARKER:
                mModelType = TP_PARKER;
                break;
            case PenController.TYPE_PICASSO:
                mModelType = TP_PICASSO;
                break;
            default:
                mModelType = TYPE_UNCONFIGURED;
                break;
        }
        apply("pen connected");
    }

    void onPenDisconnected() {
        mConnected = false;
        mModelType = TYPE_UNCONFIGURED;
    }

    private void apply(String why) {
        if (!mConnected) return;
        int type = Settings.Global.getInt(mContext.getContentResolver(), SETTING, mModelType);
        if (type < 0 || type > MAX_TYPE) {
            if (type != TYPE_UNCONFIGURED) {
                Log.w(TAG, "ignoring " + SETTING + "=" + type + ", using model type " + mModelType);
            }
            type = mModelType;
        }
        if (type == TYPE_UNCONFIGURED) return;

        String result = LenovoHal.setPenType(type);
        if ("true".equals(result)) {
            // The HAL confirms the proc write, not firmware acceptance or drawing.
            Log.i(TAG, "pen type " + type + " proc write accepted (" + why + ")");
        } else {
            Log.w(TAG, "pen type " + type + " proc write failed (" + why + "), reply=" + result);
        }
    }
}
