# Mikaguei Downloader — Android

App Android nativo do Mikaguei Downloader. Suporta **Android 10+** (API 29+), **arm64-v8a** e **armeabi-v7a**, e usa a mesma stack do [Seal](https://github.com/JunkFood02/Seal): `youtubedl-android` (Python + yt-dlp + FFmpeg + aria2c bundlados como native libs).

## Stack

| Componente | Lib |
|------------|-----|
| UI | Jetpack Compose + Material 3 (com Material You / dynamic color em Android 12+) |
| Download | [`io.github.junkfood02.youtubedl-android:library`](https://github.com/yausername/youtubedl-android) |
| Mux/transcode | `youtubedl-android:ffmpeg` |
| Aceleração | `youtubedl-android:aria2c` |
| Settings | DataStore (preferences) |
| IA keys | EncryptedSharedPreferences (AndroidKeystore + AES-256-GCM) |
| HTTP (archive.org) | OkHttp 4 |
| JSON | kotlinx-serialization |

## Recursos da v0.1.0

- Cole URL → toque em **Buscar** pra ver o título, ou **Baixar** direto
- Formato: **Melhor**, **≤ 720p** (mobile-friendly), ou **só áudio (M4A)**
- Destino: **só baixar** / **+ archive.org** / **+ archive.org e apagar local**
- Keys do archive.org guardadas com criptografia AndroidKeystore (não saem do celular nem aparecem em backup)
- **Modo simples (celular fraco)**: toggle nas configurações que desliga animações, blur e cores dinâmicas — vira UI plana Material 2-like, mais leve em GPU/RAM
- Toggle "Cores dinâmicas (Material You)" pra Android 12+

## Build local

Requer JDK 17 e Android SDK (API 34, build-tools 34.0.0).

```bash
cd android
echo "sdk.dir=/path/to/android-sdk" > local.properties

# Debug build (sem keystore necessário)
./gradlew assembleDebug

# Release build (precisa keystore.properties)
./gradlew assembleRelease
```

APKs em `app/build/outputs/apk/{debug,release}/`:
- `app-arm64-v8a-{debug,release}.apk` (~85 MB release)
- `app-armeabi-v7a-{debug,release}.apk` (~80 MB release)
- `app-universal-{debug,release}.apk` (~115 MB release)

## Release signing

Pra rodar `assembleRelease` localmente, crie:

```bash
# 1) Gerar keystore
keytool -genkeypair -v \
  -keystore mikaguei-release.jks \
  -storetype PKCS12 \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias mikaguei \
  -storepass <senha> -keypass <senha> \
  -dname "CN=Seu Nome, O=Mikaguei, C=BR"

# 2) Criar android/keystore.properties
cat > keystore.properties << EOF
storeFile=mikaguei-release.jks
storePassword=<senha>
keyAlias=mikaguei
keyPassword=<senha>
EOF
```

`keystore.properties` e `*.jks` estão no `.gitignore` — nunca commite.

No CI (GitHub Actions), o keystore vem de 4 secrets:

- `ANDROID_KEYSTORE_BASE64` — `base64 -w0 mikaguei-release.jks`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_PASSWORD`
- `ANDROID_KEY_ALIAS`

## Instalação no celular

1. Baixe o APK da [Release](../../releases) que combina com seu CPU:
   - **arm64-v8a** — celulares dos últimos 8+ anos (recomendado)
   - **armeabi-v7a** — celulares antigos 32-bit
   - **universal** — funciona em qualquer um, mas é maior
2. Active "Instalar de fontes desconhecidas" pro app que vai abrir o APK (Files, Chrome, etc)
3. Toque no APK
4. Aceite o aviso "App não verificado pela Play Protect" e instale
5. Quando abrir o app, ele inicializa o Python+yt-dlp interno (uns 5-10 segundos na primeira vez)

## Onde os arquivos vão

`/storage/emulated/0/Download/MikagueiDownloader/`

Em Android 10 (API 29) é necessário `requestLegacyExternalStorage="true"` (já configurado). Em Android 11+ a pasta `Download/` é acessível sem permissão runtime via Scoped Storage.
