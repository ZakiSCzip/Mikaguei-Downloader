package com.mikaguei.downloader.data

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okio.BufferedSink
import okio.source
import java.io.File
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

class ArchiveOrgUploader(
    private val accessKey: String,
    private val secretKey: String,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.MINUTES)
        .writeTimeout(15, TimeUnit.MINUTES)
        .retryOnConnectionFailure(true)
        .build()

    fun makeIdentifier(videoId: String, title: String): String {
        val sanitizedTitle = title
            .replace(Regex("[^A-Za-z0-9._-]"), "-")
            .trim('-')
            .take(80)
        return "yt-${videoId}_$sanitizedTitle".take(100)
    }

    /**
     * Upload a file to archive.org via S3-like API with optional metadata headers.
     * Set isFirst=true to send metadata headers that create the item.
     */
    fun uploadFile(
        identifier: String,
        file: File,
        isFirst: Boolean,
        collection: String,
        title: String?,
        creator: String?,
        description: String?,
        sourceUrl: String?,
        date: String?,
        tags: List<String>?,
        contentType: String,
    ): Result<String> {
        val key = file.name
        val url = "https://s3.us.archive.org/${urlEnc(identifier)}/${urlEnc(key)}"

        val body = object : RequestBody() {
            override fun contentType() = contentType.toMediaType()
            override fun contentLength(): Long = file.length()
            override fun writeTo(sink: BufferedSink) {
                file.source().use { sink.writeAll(it) }
            }
        }

        val builder = Request.Builder()
            .url(url)
            .put(body)
            .header("Authorization", "LOW $accessKey:$secretKey")
            .header("x-amz-auto-make-bucket", "1")

        if (isFirst) {
            builder.header("x-archive-meta-mediatype", "movies")
            builder.header("x-archive-meta-collection", collection)
            if (!title.isNullOrBlank()) builder.header("x-archive-meta-title", title.take(255))
            if (!creator.isNullOrBlank()) builder.header("x-archive-meta-creator", creator.take(255))
            if (!description.isNullOrBlank()) builder.header("x-archive-meta-description", description.take(2048))
            if (!sourceUrl.isNullOrBlank()) builder.header("x-archive-meta-source", sourceUrl)
            if (!date.isNullOrBlank()) builder.header("x-archive-meta-date", date)
            if (!tags.isNullOrEmpty()) {
                builder.header("x-archive-meta-subject", tags.joinToString(";").take(2048))
            }
        }

        return runCatching {
            client.newCall(builder.build()).execute().use { response ->
                if (!response.isSuccessful) {
                    error("HTTP ${response.code}: ${response.message}\n${response.body?.string()?.take(500)}")
                }
                "https://archive.org/details/$identifier"
            }
        }
    }

    private fun urlEnc(s: String): String =
        URLEncoder.encode(s, "UTF-8").replace("+", "%20")
}
