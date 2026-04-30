package com.mikaguei.downloader.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.mikaguei.downloader.data.ArchiveOrgUploader
import com.mikaguei.downloader.data.DownloadRepository
import com.mikaguei.downloader.data.SettingsStore
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import java.io.File
import java.util.UUID

data class HomeState(
    val url: String = "",
    val title: String = "",
    val busy: Boolean = false,
    val progress: Float = -1f,
    val etaSeconds: Long = 0L,
    val log: List<String> = emptyList(),
    val processId: String = "",
)

class HomeViewModel(
    app: Application,
    private val settings: SettingsStore,
) : AndroidViewModel(app) {

    private val repo = DownloadRepository(app)
    private val _state = MutableStateFlow(HomeState())
    val state = _state.asStateFlow()

    private var currentJob: Job? = null

    fun setUrl(value: String) {
        _state.value = _state.value.copy(url = value.trim())
    }

    fun setFormat(format: Int) {
        viewModelScope.launch { settings.setFormat(format) }
    }

    fun setDestination(d: SettingsStore.Destination) {
        viewModelScope.launch { settings.setDestination(d) }
    }

    fun fetchInfo() {
        if (_state.value.busy) return
        val url = _state.value.url
        if (url.isBlank()) return
        appendLog("[info] Buscando informações do vídeo...")
        _state.value = _state.value.copy(busy = true)
        viewModelScope.launch {
            try {
                val info = withContext(Dispatchers.IO) {
                    YoutubeDL.getInstance().getInfo(YoutubeDLRequest(url))
                }
                _state.value = _state.value.copy(
                    title = info.title ?: url,
                    busy = false,
                )
                appendLog("[ok] ${info.title}")
            } catch (t: Throwable) {
                _state.value = _state.value.copy(busy = false)
                appendLog("[erro] ${t.message ?: t.toString()}")
            }
        }
    }

    fun startDownload(prefs: SettingsStore.DownloadPrefs) {
        if (_state.value.busy) return
        val url = _state.value.url
        if (url.isBlank()) return
        val processId = UUID.randomUUID().toString()
        _state.value = _state.value.copy(busy = true, processId = processId, progress = 0f)
        appendLog("[info] Iniciando download...")
        currentJob = viewModelScope.launch {
            repo.download(url, prefs.format, processId).collect { event ->
                when (event) {
                    is DownloadRepository.Event.Log -> appendLog(event.line)
                    is DownloadRepository.Event.Progress -> _state.value = _state.value.copy(
                        progress = event.percent,
                        etaSeconds = event.etaSeconds,
                    )
                    is DownloadRepository.Event.Done -> {
                        appendLog("[ok] Salvo em ${event.outputPath}")
                        if (prefs.destination != SettingsStore.Destination.LocalOnly) {
                            uploadToIa(event.outputPath, prefs.destination == SettingsStore.Destination.IaUploadDelete)
                        }
                        _state.value = _state.value.copy(busy = false, progress = -1f)
                    }
                    is DownloadRepository.Event.Error -> {
                        appendLog("[erro] ${event.message}")
                        _state.value = _state.value.copy(busy = false, progress = -1f)
                    }
                }
            }
        }
    }

    private suspend fun uploadToIa(outputPath: String?, deleteAfter: Boolean) = withContext(Dispatchers.IO) {
        outputPath ?: return@withContext
        val access = settings.iaAccessKey()
        val secret = settings.iaSecretKey()
        if (access.isBlank() || secret.isBlank()) {
            appendLog("[erro] Faltam IA keys. Configura nas Settings.")
            return@withContext
        }
        val collection = settings.iaCollection()
        val creator = settings.iaCreator()

        val dir = File(outputPath)
        val files = dir.listFiles().orEmpty().filter { it.isFile && (it.extension == "mp4" || it.extension == "m4a" || it.name.endsWith(".info.json")) }
        if (files.isEmpty()) {
            appendLog("[erro] Nada pra enviar pro archive.org.")
            return@withContext
        }

        val infoJson = files.find { it.name.endsWith(".info.json") }
        val mediaFile = files.firstOrNull { it.extension == "mp4" || it.extension == "m4a" }
        if (mediaFile == null) {
            appendLog("[erro] Não encontrei o arquivo de mídia.")
            return@withContext
        }

        val info = parseInfoJson(infoJson)
        val uploader = ArchiveOrgUploader(access, secret)
        val identifier = uploader.makeIdentifier(info.videoId, info.title)

        appendLog("[ia] Enviando $identifier ...")
        val r1 = uploader.uploadFile(
            identifier = identifier,
            file = mediaFile,
            isFirst = true,
            collection = collection,
            title = info.title,
            creator = if (creator.isBlank()) info.channel else creator,
            description = info.description,
            sourceUrl = info.sourceUrl,
            date = info.date,
            tags = info.tags,
            contentType = if (mediaFile.extension == "m4a") "audio/mp4" else "video/mp4",
        )
        r1.fold(
            onSuccess = { appendLog("[ia] OK: $it") },
            onFailure = { appendLog("[ia] erro: ${it.message}"); return@withContext },
        )

        if (infoJson != null) {
            uploader.uploadFile(
                identifier = identifier,
                file = infoJson,
                isFirst = false,
                collection = collection,
                title = null, creator = null, description = null, sourceUrl = null, date = null, tags = null,
                contentType = "application/json",
            ).onFailure {
                appendLog("[ia] aviso: info.json falhou: ${it.message}")
            }
        }

        if (deleteAfter) {
            files.forEach { it.delete() }
            appendLog("[info] Arquivos locais apagados.")
        }
    }

    private data class InfoFields(
        val title: String,
        val videoId: String,
        val sourceUrl: String,
        val description: String,
        val tags: List<String>,
        val date: String,
        val channel: String,
    )

    private fun parseInfoJson(file: File?): InfoFields {
        if (file == null || !file.exists()) {
            return InfoFields("untitled", "noid", "", "", emptyList(), "", "")
        }
        return try {
            val json: JsonObject = Json.parseToJsonElement(file.readText()).jsonObject
            fun str(key: String) = (json[key] as? JsonPrimitive)?.contentOrNull.orEmpty()
            val tagsArr = (json["tags"] as? JsonArray)?.mapNotNull {
                (it as? JsonPrimitive)?.contentOrNull
            } ?: emptyList()
            InfoFields(
                title = str("title").ifBlank { "untitled" },
                videoId = str("id").ifBlank { "noid" },
                sourceUrl = str("webpage_url"),
                description = str("description").take(2000),
                tags = tagsArr,
                date = str("upload_date"),
                channel = str("uploader").ifBlank { str("channel") },
            )
        } catch (t: Throwable) {
            InfoFields("untitled", "noid", "", "", emptyList(), "", "")
        }
    }

    fun cancel() {
        val pid = _state.value.processId
        if (pid.isNotBlank()) {
            repo.cancel(pid)
            appendLog("[info] Cancelado.")
        }
        currentJob?.cancel()
        _state.value = _state.value.copy(busy = false, progress = -1f, processId = "")
    }

    private fun appendLog(line: String) {
        val current = _state.value.log.toMutableList()
        current.add(line)
        if (current.size > 500) current.subList(0, current.size - 500).clear()
        _state.value = _state.value.copy(log = current)
    }
}

class HomeViewModelFactory(
    private val app: Application,
    private val settings: SettingsStore,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return HomeViewModel(app, settings) as T
    }
}
