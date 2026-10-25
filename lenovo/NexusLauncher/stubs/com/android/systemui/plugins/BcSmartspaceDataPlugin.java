/*
 * SPDX-FileCopyrightText: 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package com.android.systemui.plugins;

import android.app.PendingIntent;
import android.app.smartspace.SmartspaceAction;
import android.app.smartspace.uitemplatedata.TapAction;
import android.content.Intent;
import android.view.View;

/** Compile-time stub of the Pixel Launcher class; not packaged. */
public interface BcSmartspaceDataPlugin {
    interface IntentStarter {
        default void startFromAction(SmartspaceAction action, View v, boolean showOnLockscreen) {
        }

        default void startFromAction(TapAction action, View v, boolean showOnLockscreen) {
        }

        void startIntent(View v, Intent i, boolean showOnLockscreen);

        void startPendingIntent(View v, PendingIntent pi, boolean showOnLockscreen);
    }
}
