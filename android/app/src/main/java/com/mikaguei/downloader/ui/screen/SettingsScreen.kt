package com.mikaguei.downloader.ui.screen

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mikaguei.downloader.data.SettingsStore
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    settings: SettingsStore,
    onBack: () -> Unit,
) {
    val ui by settings.uiPrefs.collectAsState(initial = SettingsStore.UiPrefs())
    val scope = rememberCoroutineScope()

    var iaAccess by remember { mutableStateOf("") }
    var iaSecret by remember { mutableStateOf("") }
    var iaCollection by remember { mutableStateOf("opensource_movies") }
    var iaCreator by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        iaAccess = settings.iaAccessKey()
        iaSecret = settings.iaSecretKey()
        iaCollection = settings.iaCollection()
        iaCreator = settings.iaCreator()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Configurações") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Voltar")
                    }
                },
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Aparência", style = MaterialTheme.typography.titleMedium)

            SwitchRow(
                title = "Modo simples (celular fraco)",
                subtitle = "Desliga animações, blur e cores dinâmicas. Ative em celulares com pouca RAM ou GPU fraca.",
                checked = ui.simpleMode,
                onChange = { v -> scope.launch { settings.setSimpleMode(v) } },
            )

            SwitchRow(
                title = "Cores dinâmicas (Material You)",
                subtitle = "Usa as cores do papel de parede do sistema. Android 12+. Desliga automaticamente em modo simples.",
                checked = ui.dynamicColor,
                onChange = { v -> scope.launch { settings.setDynamicColor(v) } },
            )

            HorizontalDivider()

            Text("Internet Archive", style = MaterialTheme.typography.titleMedium)

            OutlinedTextField(
                value = iaAccess,
                onValueChange = { iaAccess = it },
                label = { Text("Access key") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = iaSecret,
                onValueChange = { iaSecret = it },
                label = { Text("Secret key") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = iaCollection,
                onValueChange = { iaCollection = it },
                label = { Text("Coleção (default: opensource_movies)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = iaCreator,
                onValueChange = { iaCreator = it },
                label = { Text("Creator (vazio = canal)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = {
                        settings.setIaCredentials(iaAccess.trim(), iaSecret.trim(), iaCollection.trim(), iaCreator.trim())
                    },
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Salvar")
                }
                OutlinedButton(
                    onClick = {
                        settings.clearIaCredentials()
                        iaAccess = ""
                        iaSecret = ""
                    },
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Esquecer keys")
                }
            }

            Text(
                "As chaves ficam guardadas com EncryptedSharedPreferences (AndroidKeystore, AES-256-GCM). Não saem do celular nem aparecem em backups.",
                style = MaterialTheme.typography.bodySmall,
            )

            Spacer(Modifier.height(16.dp))
            Text(
                "Mikaguei Downloader v0.1.0",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun SwitchRow(
    title: String,
    subtitle: String,
    checked: Boolean,
    onChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            Text(subtitle, style = MaterialTheme.typography.bodySmall)
        }
        Switch(checked = checked, onCheckedChange = onChange)
    }
}
