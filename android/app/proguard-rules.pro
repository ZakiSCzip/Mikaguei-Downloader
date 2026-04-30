# yt-dlp / youtubedl-android keep rules
-keep class com.yausername.** { *; }
-keep class io.github.junkfood02.** { *; }

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**

# Compose
-keep class androidx.compose.** { *; }
