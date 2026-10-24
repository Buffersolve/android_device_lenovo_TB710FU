/*
 * SPDX-License-Identifier: Apache-2.0
 */

package org.lunaris.dolby.data

import android.util.Log
import org.lunaris.dolby.audio.DolbyAudioEffect

/**
 * Process-wide owner of the DAP effect on audio session 0.
 *
 * AudioFlinger gives control of an effect to a single handle and does not hand it over to a
 * later handle of equal priority, so every [DolbyRepository] in the process has to share one
 * handle. The handle is reference counted and released when the last repository closes.
 */
internal object DolbyEffectHolder {

    private const val TAG = "DolbyEffectHolder"
    private const val EFFECT_PRIORITY = 100

    private val lock = Any()
    private var effect: DolbyAudioEffect? = null
    private var refCount = 0
    private var restorePending = false

    /** Takes a reference, creating the shared effect if this is the first one. */
    fun acquire() {
        synchronized(lock) {
            if (effect == null) {
                effect = createEffect()
                Log.i(TAG, "Created shared Dolby effect")
            }
            refCount++
        }
    }

    /** Drops a reference and releases the shared effect once nobody uses it. */
    fun release() {
        synchronized(lock) {
            if (refCount == 0) return
            refCount--
            if (refCount == 0) {
                effect?.let { runCatching { it.release() } }
                effect = null
                restorePending = false
                Log.i(TAG, "Released shared Dolby effect")
            }
        }
    }

    /**
     * The shared effect. Read it on every use: [recreate] replaces it. If an earlier recreate
     * failed to create a handle, this tries again.
     */
    fun current(): DolbyAudioEffect = synchronized(lock) {
        effect ?: run {
            if (refCount == 0) throw IllegalStateException("Dolby effect is not held")
            createEffect().also {
                effect = it
                restorePending = true
                Log.i(TAG, "Created shared Dolby effect after earlier failure")
            }
        }
    }

    /**
     * Replaces [stale] with a new handle when it lost control or went dead. If another caller
     * already replaced it, that newer handle is returned instead, so concurrent callers do not
     * recreate twice. A new handle has to get its saved state back, see [restoreIfPending].
     */
    fun recreate(stale: DolbyAudioEffect): DolbyAudioEffect = synchronized(lock) {
        val held = effect
        if (held == null || held !== stale) return current()
        Log.i(TAG, "Recreating shared Dolby effect")
        runCatching { held.release() }
        effect = null
        val fresh = createEffect()
        effect = fresh
        restorePending = true
        fresh
    }

    /**
     * Runs [restore] if a recreated handle still has to get its saved state back. The pending
     * flag is cleared only when [restore] reports success. Returns true when nothing is pending
     * or the restore succeeded.
     */
    fun restoreIfPending(restore: () -> Boolean): Boolean = synchronized(lock) {
        if (!restorePending) return true
        val restored = restore()
        if (restored) restorePending = false
        restored
    }

    private fun createEffect() = DolbyAudioEffect(EFFECT_PRIORITY, audioSession = 0)
}
