package com.mikaguei.downloader

import android.app.Application
import android.util.Log
import com.yausername.aria2c.Aria2c
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class MikagueiApp : Application() {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()
        appScope.launch {
            try {
                YoutubeDL.getInstance().init(this@MikagueiApp)
                FFmpeg.getInstance().init(this@MikagueiApp)
                Aria2c.getInstance().init(this@MikagueiApp)
                Log.i(TAG, "youtubedl-android initialized")
            } catch (t: Throwable) {
                Log.e(TAG, "Failed to init youtubedl-android", t)
            }
        }
    }

    companion object {
        private const val TAG = "MikagueiApp"
    }
}
