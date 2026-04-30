package com.mikaguei.downloader.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mikaguei.downloader.data.SettingsStore
import com.mikaguei.downloader.ui.HomeViewModel
import com.mikaguei.downloader.ui.HomeViewModelFactory
import com.mikaguei.downloader.ui.theme.LocalSimpleMode

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    settings: SettingsStore,
    onOpenSettings: () -> Unit,
) {
    val context = LocalContext.current
    val vm: HomeViewModel = viewModel(factory = HomeViewModelFactory(context.applicationContext as android.app.Application, settings))
    val state by vm.state.collectAsState()
    val downloadPrefs by settings.downloadPrefs.collectAsState(initial = SettingsStore.DownloadPrefs())
    val simpleMode = LocalSimpleMode.current

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Mikaguei Downloader") },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
                    }
                },
                colors = if (simpleMode) {
                    TopAppBarDefaults.topAppBarColors()
                } else {
                    TopAppBarDefaults.centerAlignedTopAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface
                    )
                },
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = if (state.title.isBlank()) "Cole o link e toque em Buscar formatos." else state.title,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 8.dp),
            )

            OutlinedTextField(
                value = state.url,
                onValueChange = vm::setUrl,
                label = { Text("URL do vídeo") },
                placeholder = { Text("https://www.youtube.com/watch?v=...") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            )

            Text("Formato", style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = downloadPrefs.format == SettingsStore.FORMAT_BEST,
                    onClick = { vm.setFormat(SettingsStore.FORMAT_BEST) },
                    label = { Text("Melhor") },
                )
                FilterChip(
                    selected = downloadPrefs.format == SettingsStore.FORMAT_720,
                    onClick = { vm.setFormat(SettingsStore.FORMAT_720) },
                    label = { Text("≤ 720p") },
                )
                FilterChip(
                    selected = downloadPrefs.format == SettingsStore.FORMAT_AUDIO,
                    onClick = { vm.setFormat(SettingsStore.FORMAT_AUDIO) },
                    label = { Text("Áudio") },
                )
            }

            Text("Destino", style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = downloadPrefs.destination == SettingsStore.Destination.LocalOnly,
                    onClick = { vm.setDestination(SettingsStore.Destination.LocalOnly) },
                    label = { Text("PC") },
                )
                FilterChip(
                    selected = downloadPrefs.destination == SettingsStore.Destination.IaUpload,
                    onClick = { vm.setDestination(SettingsStore.Destination.IaUpload) },
                    label = { Text("+ IA") },
                )
                FilterChip(
                    selected = downloadPrefs.destination == SettingsStore.Destination.IaUploadDelete,
                    onClick = { vm.setDestination(SettingsStore.Destination.IaUploadDelete) },
                    label = { Text("+ IA, apagar") },
                )
            }

            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                OutlinedButton(
                    onClick = { vm.fetchInfo() },
                    enabled = !state.busy && state.url.isNotBlank(),
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(Icons.Default.Search, contentDescription = null)
                    Text("  Buscar")
                }
                if (state.busy) {
                    Button(
                        onClick = { vm.cancel() },
                        modifier = Modifier.weight(1f),
                    ) {
                        Icon(Icons.Default.Cancel, contentDescription = null)
                        Text("  Cancelar")
                    }
                } else {
                    Button(
                        onClick = { vm.startDownload(downloadPrefs) },
                        enabled = state.url.isNotBlank(),
                        modifier = Modifier.weight(1f),
                    ) {
                        Icon(Icons.Default.Download, contentDescription = null)
                        Text("  Baixar")
                    }
                }
            }

            if (state.progress >= 0f) {
                LinearProgressIndicator(
                    progress = { (state.progress / 100f).coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    text = "%.1f%%".format(state.progress) +
                        if (state.etaSeconds > 0) "  •  ETA ${state.etaSeconds}s" else "",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }

            Text(
                text = "Salvando em: Download/MikagueiDownloader/",
                style = MaterialTheme.typography.bodyMedium,
            )

            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                val listState = rememberLazyListState()
                LaunchedEffect(state.log.size) {
                    if (state.log.isNotEmpty()) listState.animateScrollToItem(state.log.size - 1)
                }
                LazyColumn(
                    state = listState,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 120.dp, max = 320.dp)
                        .padding(8.dp),
                ) {
                    if (state.log.isEmpty()) {
                        item {
                            Text(
                                "Cole um link e toque em Baixar.",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    } else {
                        items(state.log) { line ->
                            Text(
                                text = line,
                                fontFamily = FontFamily.Monospace,
                                fontSize = 12.sp,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
        }
    }
}
