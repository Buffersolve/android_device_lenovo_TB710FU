/*
 * Copyright (C) 2024-2025 Lunaris AOSP
 * SPDX-License-Identifier: Apache-2.0
 */

package org.lunaris.dolby.tile

import android.content.res.Resources
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import org.lunaris.dolby.R
import org.lunaris.dolby.data.DolbyRepository

class DolbyTileService : TileService() {

    private var repositoryOrNull: DolbyRepository? = null
    private val repository: DolbyRepository
        get() = repositoryOrNull ?: DolbyRepository(applicationContext).also { repositoryOrNull = it }

    override fun onDestroy() {
        // Release the reference on the shared effect when the tile is unbound.
        repositoryOrNull?.close()
        repositoryOrNull = null
        super.onDestroy()
    }

    override fun onStartListening() {
        super.onStartListening()
        updateTile()
    }

    override fun onClick() {
        super.onClick()
        val enabled = repository.getDolbyEnabled()
        repository.setDolbyEnabled(!enabled)
        updateTile()
    }

    private fun updateTile() {
        qsTile?.apply {
            val enabled = repository.getDolbyEnabled()
            state = if (enabled) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
            subtitle = getProfileName()
            updateTile()
        }
    }

    private fun getProfileName(): String {
        val profile = repository.getCurrentProfile()
        val profiles = resources.getStringArray(R.array.dolby_profile_entries)
        val profileValues = resources.getStringArray(R.array.dolby_profile_values)
        
        return try {
            val index = profileValues.indexOf(profile.toString())
            if (index != -1) profiles[index] else getString(R.string.dolby_unknown)
        } catch (e: Exception) {
            getString(R.string.dolby_unknown)
        }
    }
}
