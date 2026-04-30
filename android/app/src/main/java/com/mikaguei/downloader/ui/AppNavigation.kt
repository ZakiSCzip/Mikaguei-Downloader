package com.mikaguei.downloader.ui

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.mikaguei.downloader.data.SettingsStore
import com.mikaguei.downloader.ui.screen.HomeScreen
import com.mikaguei.downloader.ui.screen.SettingsScreen

@Composable
fun AppNavigation(settings: SettingsStore) {
    val nav = rememberNavController()
    NavHost(navController = nav, startDestination = "home") {
        composable("home") {
            HomeScreen(
                settings = settings,
                onOpenSettings = { nav.navigate("settings") },
            )
        }
        composable("settings") {
            SettingsScreen(
                settings = settings,
                onBack = { nav.popBackStack() },
            )
        }
    }
}
