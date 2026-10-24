/*
 * SPDX-FileCopyrightText: 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package com.android.launcher3.tb710fu;

import android.content.Context;
import android.content.ContextWrapper;
import android.graphics.Rect;
import android.util.Log;
import android.view.View;

import com.android.launcher3.widget.LauncherAppWidgetHostView;

import java.lang.reflect.Field;

/**
 * Hides the taskbar copy of the hotseat search bar while a FloatingWidgetView
 * animates the search bar widget (returning home from Google search by swipe
 * or back, or opening it). The floating copy flies into place over the taskbar
 * search bar, which the taskbar already shows there, so the bar was drawn
 * twice. App icons get the same treatment in the launcher itself (the matching
 * taskbar icon is hidden during the icon animation).
 *
 * FloatingWidgetView calls setUpdatesDeferred(true) when it starts and
 * setUpdatesDeferred(false) when it finishes; patch_launcher.py routes both
 * calls through here. The taskbar search bar is hidden with an empty clip,
 * since its alpha and visibility are driven by the taskbar animations.
 */
public final class TaskbarQsbHider {

    private static final String TAG = "TaskbarQsbHider";
    private static final String SEARCH_BAR_CLASS = "com.android.launcher3.qsb.OseWidgetView";
    private static final Rect EMPTY = new Rect();

    private TaskbarQsbHider() {
    }

    public static void setUpdatesDeferred(LauncherAppWidgetHostView view, boolean deferred) {
        view.setUpdatesDeferred(deferred);
        if (!SEARCH_BAR_CLASS.equals(view.getClass().getName())) {
            return;
        }
        try {
            View qsb = findTaskbarQsb(view.getContext());
            if (qsb != null) {
                qsb.post(new SetClip(qsb, deferred ? EMPTY : null));
            }
        } catch (ReflectiveOperationException | RuntimeException e) {
            Log.w(TAG, "Cannot reach the taskbar search bar", e);
        }
    }

    /** Applies the clip on the taskbar UI thread. */
    private static final class SetClip implements Runnable {
        private final View mView;
        private final Rect mClip;

        SetClip(View view, Rect clip) {
            mView = view;
            mClip = clip;
        }

        @Override
        public void run() {
            mView.setClipBounds(mClip);
        }
    }

    private static View findTaskbarQsb(Context context) throws ReflectiveOperationException {
        Object launcher = context;
        while (launcher instanceof ContextWrapper && field(launcher, "mTaskbarInteractor") == null) {
            launcher = ((ContextWrapper) launcher).getBaseContext();
        }
        Object o = get(launcher, "mTaskbarInteractor");
        o = get(o, "taskbarUIController");
        o = get(o, "mControllers");
        o = get(o, "taskbarViewController");
        o = get(o, "mTaskbarView");
        o = get(o, "mQsb");
        return o instanceof View ? (View) o : null;
    }

    private static Field field(Object obj, String name) {
        for (Class<?> c = obj.getClass(); c != null; c = c.getSuperclass()) {
            try {
                Field f = c.getDeclaredField(name);
                f.setAccessible(true);
                return f;
            } catch (NoSuchFieldException ignored) {
                // keep looking in the superclass
            }
        }
        return null;
    }

    private static Object get(Object obj, String name) throws ReflectiveOperationException {
        if (obj == null) {
            return null;
        }
        Field f = field(obj, name);
        if (f == null) {
            throw new NoSuchFieldException(obj.getClass().getName() + "." + name);
        }
        return f.get(obj);
    }
}
