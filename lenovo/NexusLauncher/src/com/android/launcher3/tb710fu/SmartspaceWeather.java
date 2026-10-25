/*
 * SPDX-FileCopyrightText: 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package com.android.launcher3.tb710fu;

import android.app.smartspace.SmartspaceAction;
import android.app.smartspace.SmartspaceTarget;
import android.app.smartspace.uitemplatedata.TapAction;
import android.content.ComponentName;
import android.content.Intent;
import android.util.Log;
import android.view.View;

import com.android.systemui.plugins.BcSmartspaceDataPlugin.IntentStarter;

/**
 * Opens Pixel Weather from the At a Glance weather card.
 *
 * The card's tap action goes to the Google app smartspace trampoline, which
 * only forwards it when the caller is a Google-signed Pixel Launcher. This
 * launcher is patched and re-signed with the platform key, so the trampoline
 * logs "QSB permission is not trusted" and finishes without opening anything.
 * patch_launcher.py routes the BcSmartspace card clicks through here; weather
 * cards that point at the trampoline start Pixel Weather instead, everything
 * else is started as before.
 */
public final class SmartspaceWeather {

    private static final String TAG = "SmartspaceWeather";
    private static final ComponentName TRAMPOLINE = new ComponentName(
            "com.google.android.googlequicksearchbox",
            "com.google.android.apps.search.assistant.verticals.ambient.smartspace"
                    + ".trampolineactivity.ExportedSmartspaceTrampolineActivity");
    private static final String WEATHER_PACKAGE = "com.google.android.apps.weather";

    private SmartspaceWeather() {
    }

    public static void startFromAction(IntentStarter starter, SmartspaceAction action,
            View view, boolean showOnLockscreen, SmartspaceTarget target) {
        if (!openWeather(starter, target, action.getIntent(), view, showOnLockscreen)) {
            starter.startFromAction(action, view, showOnLockscreen);
        }
    }

    public static void startFromAction(IntentStarter starter, TapAction action,
            View view, boolean showOnLockscreen, SmartspaceTarget target) {
        if (!openWeather(starter, target, action.getIntent(), view, showOnLockscreen)) {
            starter.startFromAction(action, view, showOnLockscreen);
        }
    }

    private static boolean openWeather(IntentStarter starter, SmartspaceTarget target,
            Intent intent, View view, boolean showOnLockscreen) {
        if (target == null || target.getFeatureType() != SmartspaceTarget.FEATURE_WEATHER
                || intent == null || !TRAMPOLINE.equals(intent.getComponent())) {
            return false;
        }
        Intent weather = view.getContext().getPackageManager()
                .getLaunchIntentForPackage(WEATHER_PACKAGE);
        if (weather == null) {
            return false;
        }
        weather.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            starter.startIntent(view, weather, showOnLockscreen);
            return true;
        } catch (RuntimeException e) {
            Log.w(TAG, "Cannot open " + WEATHER_PACKAGE, e);
            return false;
        }
    }
}
