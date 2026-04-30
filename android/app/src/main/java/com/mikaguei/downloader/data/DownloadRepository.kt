package com.mikaguei.downloader.data

import android.content.Context
import android.os.Environment
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.channels.awaitClose
import java.io.File

class DownloadRepository(private val context: Context) {

    sealed class Event {
        data class Log(val line: String) : Event()
        data class Progress(val percent: Float, val etaSeconds: Long) : Event()
        data class Done(val outputPath: String?) : Event()
        data class Error(val message: String) : Event()
    }

    fun outputDir(): File {
        val downloads = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        val dir = File(downloads, "MikagueiDownloader")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    fun download(
        url: String,
        format: Int,
        processId: String,
    ): Flow<Event> = callbackFlow {
        val outDir = outputDir()
        val outputTemplate = File(outDir, "%(title).200B [%(id)s].%(ext)s").absolutePath

        trySend(Event.Log("[info] Iniciando download em $outDir"))

        val request = YoutubeDLRequest(url).apply {
            addOption("-o", outputTemplate)
            addOption("--no-mtime")
            addOption("--no-playlist")
            addOption("--restrict-filenames")
            addOption("--write-info-json")
            when (format) {
                SettingsStore.FORMAT_AUDIO -> {
                    addOption("-x")
                    addOption("--audio-format", "m4a")
                }
                SettingsStore.FORMAT_720 -> {
                    addOption("-f", "bv*[height<=720]+ba/b[height<=720]/best")
                    addOption("--merge-output-format", "mp4")
                }
                else -> {
                    addOption("-f", "bv*+ba/b/best")
                    addOption("--merge-output-format", "mp4")
                }
            }
            // Avoid n-challenge: prefer mobile clients
            addOption("--extractor-args", "youtube:player_client=ios,mweb,android_vr,web_safari,android,web")
        }

        try {
            YoutubeDL.getInstance().execute(request, processId) { progress, eta, line ->
                if (line.isNotBlank()) trySend(Event.Log(line.trimEnd()))
                if (progress >= 0f) trySend(Event.Progress(progress, eta))
            }
            trySend(Event.Log("[ok] Download finalizado."))
            trySend(Event.Done(outDir.absolutePath))
        } catch (t: Throwable) {
            trySend(Event.Error(t.message ?: t.toString()))
        }
        close()
        awaitClose { /* nothing to do */ }
    }.flowOn(Dispatchers.IO)

    fun cancel(processId: String) {
        runCatching { YoutubeDL.getInstance().destroyProcessById(processId) }
    }
}
