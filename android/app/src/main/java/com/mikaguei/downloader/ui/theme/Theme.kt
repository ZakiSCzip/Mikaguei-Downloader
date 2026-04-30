package com.mikaguei.downloader.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val MikagueiRed = Color(0xFFD32F2F)
private val MikagueiRedDark = Color(0xFFB71C1C)

private val LightColors = lightColorScheme(
    primary = MikagueiRed,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFDAD6),
    onPrimaryContainer = Color(0xFF410002),
    secondary = Color(0xFF775653),
    onSecondary = Color.White,
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFFFB4AB),
    onPrimary = Color(0xFF690005),
    primaryContainer = MikagueiRedDark,
    onPrimaryContainer = Color(0xFFFFDAD6),
    secondary = Color(0xFFE7BDB9),
    onSecondary = Color(0xFF442927),
)

val LocalSimpleMode = staticCompositionLocalOf { false }

@Composable
fun MikagueiTheme(
    simpleMode: Boolean = false,
    useDynamicColor: Boolean = true,
    content: @Composable () -> Unit
) {
    val darkTheme = isSystemInDarkTheme()
    val context = LocalContext.current
    val colorScheme = when {
        useDynamicColor && !simpleMode && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColors
        else -> LightColors
    }

    val typography = Typography(
        titleLarge = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.SemiBold),
        titleMedium = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.Medium),
        bodyLarge = TextStyle(fontSize = 16.sp),
        bodyMedium = TextStyle(fontSize = 14.sp),
        labelLarge = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Medium),
    )

    CompositionLocalProvider(LocalSimpleMode provides simpleMode) {
        MaterialTheme(
            colorScheme = colorScheme,
            typography = typography,
            content = content,
        )
    }
}
