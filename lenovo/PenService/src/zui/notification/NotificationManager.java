/*
 * SPDX-FileCopyrightText: 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package zui.notification;

import android.app.Notification;
import android.content.Context;
import android.text.TextUtils;
import android.util.Log;

/**
 * Replaces the ZUI notification client bundled in the APK. Stock talks to the
 * ZUI-only "zuinotification" service and keeps a null binder when it is
 * missing, so the first call (cancelNotification() from
 * PenEventReceiver on SCREEN_OFF) crashed PenService with a
 * NullPointerException. Post the notifications through the platform
 * NotificationManager instead, with the same public methods the APK calls.
 */
public class NotificationManager {

    private static final String TAG = "NotificationManager";

    private static NotificationManager sInstance;

    private final android.app.NotificationManager mNotificationManager;

    private NotificationManager(Context context) {
        mNotificationManager = context.getApplicationContext()
                .getSystemService(android.app.NotificationManager.class);
    }

    public static NotificationManager getInstance(Context context) {
        synchronized (NotificationManager.class) {
            if (sInstance == null) {
                sInstance = new NotificationManager(context);
            }
            return sInstance;
        }
    }

    public void showNotification(int id, Notification notification) {
        showNotification(id, notification, 0);
    }

    public void showNotification(int id, Notification notification, int userId) {
        post(id, notification);
    }

    public void showPermanentNotification(int id, Notification notification) {
        showPermanentNotification(id, notification, 0);
    }

    public void showPermanentNotification(int id, Notification notification, int userId) {
        if (notification != null) {
            notification.flags |= Notification.FLAG_ONGOING_EVENT | Notification.FLAG_NO_CLEAR;
        }
        post(id, notification);
    }

    public void updatePermanentNotification(int id, Notification notification) {
        updatePermanentNotification(id, notification, 0);
    }

    public void updatePermanentNotification(int id, Notification notification, int userId) {
        showPermanentNotification(id, notification, userId);
    }

    public void cancelNotification(String pkg, int id) {
        try {
            mNotificationManager.cancel(id);
        } catch (RuntimeException e) {
            Log.w(TAG, "cancelNotification(" + id + ") failed", e);
        }
    }

    public void cancelAllNotifications(String pkg) {
        try {
            mNotificationManager.cancelAll();
        } catch (RuntimeException e) {
            Log.w(TAG, "cancelAllNotifications failed", e);
        }
    }

    public void setDescriptionText(Notification notification, String text, boolean warning) {
        if (notification == null || TextUtils.isEmpty(text) || notification.extras == null) {
            return;
        }
        notification.extras.putString("DescriptionText", text);
        notification.extras.putBoolean("WarningDescription", warning);
    }

    private void post(int id, Notification notification) {
        if (notification == null) {
            return;
        }
        try {
            mNotificationManager.notify(id, notification);
        } catch (RuntimeException e) {
            // e.g. a notification without a channel; ZUI used to accept those
            Log.w(TAG, "notify(" + id + ") failed", e);
        }
    }
}
