package com.mikaguei.downloader.data

import android.content.Context
import android.content.SharedPreferences
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "mikaguei_prefs")

class SettingsStore(private val context: Context) {

    data class UiPrefs(
        val simpleMode: Boolean = false,
        val dynamicColor: Boolean = true,
    )

    enum class Destination { LocalOnly, IaUpload, IaUploadDelete }

    data class DownloadPrefs(
        val destination: Destination = Destination.LocalOnly,
        val format: Int = FORMAT_BEST,
    )

    val uiPrefs: Flow<UiPrefs> = context.dataStore.data.map {
        UiPrefs(
            simpleMode = it[KEY_SIMPLE_MODE] ?: false,
            dynamicColor = it[KEY_DYNAMIC_COLOR] ?: true,
        )
    }

    val downloadPrefs: Flow<DownloadPrefs> = context.dataStore.data.map {
        DownloadPrefs(
            destination = (it[KEY_DESTINATION] ?: 0).toDestination(),
            format = it[KEY_FORMAT] ?: FORMAT_BEST,
        )
    }

    suspend fun setSimpleMode(enabled: Boolean) {
        context.dataStore.edit { it[KEY_SIMPLE_MODE] = enabled }
    }

    suspend fun setDynamicColor(enabled: Boolean) {
        context.dataStore.edit { it[KEY_DYNAMIC_COLOR] = enabled }
    }

    suspend fun setDestination(d: Destination) {
        context.dataStore.edit { it[KEY_DESTINATION] = d.ordinal }
    }

    suspend fun setFormat(f: Int) {
        context.dataStore.edit { it[KEY_FORMAT] = f }
    }

    private fun securePrefs(): SharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            context,
            "mikaguei_secure",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    fun iaAccessKey(): String = securePrefs().getString("ia_access", "") ?: ""
    fun iaSecretKey(): String = securePrefs().getString("ia_secret", "") ?: ""
    fun iaCollection(): String = securePrefs().getString("ia_collection", "opensource_movies") ?: "opensource_movies"
    fun iaCreator(): String = securePrefs().getString("ia_creator", "") ?: ""

    fun setIaCredentials(access: String, secret: String, collection: String, creator: String) {
        securePrefs().edit().apply {
            putString("ia_access", access)
            putString("ia_secret", secret)
            putString("ia_collection", collection)
            putString("ia_creator", creator)
            apply()
        }
    }

    fun clearIaCredentials() {
        securePrefs().edit().apply {
            remove("ia_access")
            remove("ia_secret")
            apply()
        }
    }

    private fun Int.toDestination(): Destination = when (this) {
        1 -> Destination.IaUpload
        2 -> Destination.IaUploadDelete
        else -> Destination.LocalOnly
    }

    companion object {
        const val FORMAT_BEST = 0
        const val FORMAT_720 = 1
        const val FORMAT_AUDIO = 2

        private val KEY_SIMPLE_MODE: Preferences.Key<Boolean> = booleanPreferencesKey("simple_mode")
        private val KEY_DYNAMIC_COLOR: Preferences.Key<Boolean> = booleanPreferencesKey("dynamic_color")
        private val KEY_DESTINATION: Preferences.Key<Int> = intPreferencesKey("destination")
        private val KEY_FORMAT: Preferences.Key<Int> = intPreferencesKey("format")
    }
}
