package com.mikaguei.downloader

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.mikaguei.downloader.data.SettingsStore
import com.mikaguei.downloader.ui.AppNavigation
import com.mikaguei.downloader.ui.theme.MikagueiTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT),
        )
        val settings = SettingsStore(applicationContext)
        setContent {
            val ui by settings.uiPrefs.collectAsState(initial = SettingsStore.UiPrefs())
            MikagueiTheme(
                simpleMode = ui.simpleMode,
                useDynamicColor = ui.dynamicColor,
            ) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    AppNavigation(settings = settings)
                }
            }
        }
    }
}
