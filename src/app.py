"""
Easy Downloader (yt-dlp) — Tkinter GUI

Features:
- Paste URL + click "Carregar" to fetch metadata via yt-dlp.
- Single video: shows big thumbnail, title, channel, duration.
- Playlist: shows scrollable list with checkbox + miniature thumbnail per entry,
  user picks which ones to download.
- Format selector applies to whatever is selected; bundled ffmpeg is used.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import urllib.parse
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk  # type: ignore[import-not-found]

    PIL_OK = True
except Exception:  # noqa: BLE001
    PIL_OK = False

try:
    import requests  # type: ignore[import-not-found]

    REQ_OK = True
except Exception:  # noqa: BLE001
    REQ_OK = False

APP_TITLE = "Mikaguei Downloader"
APP_VERSION = "1.6.1"


# ---------- helpers ----------
def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent / "bin"


def default_output_dir() -> Path:
    for c in (Path.home() / "Downloads", Path.home() / "Desktop", Path.home()):
        if c.exists():
            return c
    return Path.home()


def logs_dir() -> Path:
    """Where to persist log files."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        d = Path(base) / "EasyDownloader" / "logs"
    else:
        d = Path.home() / ".easy-downloader" / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        d = Path(os.environ.get("TEMP", "/tmp")) / "EasyDownloader"
        d.mkdir(parents=True, exist_ok=True)
    return d


class SessionLogger:
    """Append-only log file for the current session."""

    def __init__(self) -> None:
        ts = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.path: Path = logs_dir() / f"{ts}.log"
        self._lock = threading.Lock()
        self._fh = None
        try:
            self._fh = self.path.open("a", encoding="utf-8", buffering=1)
            self._raw_write(f"=== {APP_TITLE} v{APP_VERSION} — sessão iniciada {_dt.datetime.now().isoformat(timespec='seconds')} ===\n")
        except Exception:  # noqa: BLE001
            self._fh = None

    def _raw_write(self, text: str) -> None:
        if self._fh is None:
            return
        try:
            self._fh.write(text)
        except Exception:  # noqa: BLE001
            pass

    def write(self, line: str) -> None:
        with self._lock:
            ts = _dt.datetime.now().strftime("%H:%M:%S")
            self._raw_write(f"[{ts}] {line}\n")

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._raw_write(f"=== sessão encerrada {_dt.datetime.now().isoformat(timespec='seconds')} ===\n")
                    self._fh.close()
                except Exception:  # noqa: BLE001
                    pass
                self._fh = None


def hidden_startupinfo():
    si = None
    cf = 0
    if sys.platform.startswith("win"):
        cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
            si.wShowWindow = 0
        except Exception:  # noqa: BLE001
            si = None
    return si, cf


def child_env() -> dict:
    """Env for yt-dlp subprocesses with our resource dir prepended to PATH so
    bundled deno.exe / ffmpeg.exe are discoverable."""
    env = os.environ.copy()
    rd = str(resource_dir())
    sep = os.pathsep
    env["PATH"] = rd + sep + env.get("PATH", "")
    return env


def config_path() -> Path:
    """Where to persist user prefs (IA keys, last collection, etc.)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "EasyDownloader" / "config.json"
    return Path.home() / ".easy-downloader" / "config.json"


# ---------- DPAPI (Windows) for encrypting sensitive config fields ----------
_DPAPI_PREFIX = "dpapi:"
_SENSITIVE_KEYS = ("ia_access", "ia_secret")


def _dpapi_available() -> bool:
    return sys.platform.startswith("win")


def _dpapi_encrypt(plaintext: str) -> str | None:
    """Encrypt a string with Windows DPAPI (CurrentUser scope). Returns base64
    string with prefix 'dpapi:' or None on failure / non-Windows.
    """
    if not _dpapi_available() or not plaintext:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        data_in = plaintext.encode("utf-8")
        buf_in = ctypes.create_string_buffer(data_in, len(data_in))
        in_blob = DATA_BLOB(len(data_in), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
        out_blob = DATA_BLOB()
        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None,
                                        0x1, ctypes.byref(out_blob)):
            return None
        try:
            encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


def _dpapi_decrypt(token: str) -> str | None:
    """Reverse of _dpapi_encrypt. Returns plaintext or None on failure."""
    if not isinstance(token, str) or not token.startswith(_DPAPI_PREFIX):
        return None
    if not _dpapi_available():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        raw = base64.b64decode(token[len(_DPAPI_PREFIX):])
        buf_in = ctypes.create_string_buffer(raw, len(raw))
        in_blob = DATA_BLOB(len(raw), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None,
                                          0x1, ctypes.byref(out_blob)):
            return None
        try:
            decrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
        return decrypted.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None


def load_config() -> dict:
    """Load user config and transparently decrypt DPAPI-wrapped fields."""
    p = config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    # transparent decrypt
    for k in _SENSITIVE_KEYS:
        v = data.get(k)
        if isinstance(v, str) and v.startswith(_DPAPI_PREFIX):
            decrypted = _dpapi_decrypt(v)
            data[k] = decrypted if decrypted is not None else ""
    return data


def save_config(data: dict) -> None:
    """Save user config; DPAPI-encrypt sensitive fields when running on Windows."""
    p = config_path()
    out = dict(data)
    if _dpapi_available():
        for k in _SENSITIVE_KEYS:
            v = out.get(k)
            if isinstance(v, str) and v and not v.startswith(_DPAPI_PREFIX):
                token = _dpapi_encrypt(v)
                if token is not None:
                    out[k] = token
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        # restrict to current user where possible
        if sys.platform.startswith("win"):
            try:
                os.chmod(p, 0o600)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


def exe_sha256() -> str | None:
    """SHA256 of the running executable (when frozen). None otherwise / on error."""
    try:
        target = Path(sys.executable) if getattr(sys, "frozen", False) else None
        if target is None or not target.exists():
            return None
        h = hashlib.sha256()
        with target.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return None


_IDENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def archive_identifier(title: str, video_id: str) -> str:
    """Build a valid Internet Archive identifier (a-zA-Z0-9._-, max ~100 chars).

    Pattern: yt-<id>_<sanitized-title>
    """
    base = _IDENT_RE.sub("-", (title or "").strip())
    base = re.sub(r"-+", "-", base).strip("-_.")[:60]
    vid = _IDENT_RE.sub("", (video_id or "").strip())
    if vid:
        ident = f"yt-{vid}" + (f"_{base}" if base else "")
    else:
        ident = base or "easy-downloader-upload"
    return ident[:100].strip("-_.")


def _meta_value(s: str) -> str:
    """Encode a metadata header value for IA S3 (non-ASCII -> uri()-wrapped)."""
    if not isinstance(s, str):
        s = str(s)
    s = s.replace("\r", " ").replace("\n", " ")
    try:
        s.encode("ascii")
        return s
    except UnicodeEncodeError:
        return "uri(" + urllib.parse.quote(s, safe="") + ")"


class IAUploader:
    """Upload files to archive.org via the S3-like API."""

    BASE = "https://s3.us.archive.org"

    def __init__(self, access_key: str, secret_key: str, collection: str, log) -> None:
        self.access = (access_key or "").strip()
        self.secret = (secret_key or "").strip()
        self.collection = (collection or "opensource_movies").strip() or "opensource_movies"
        self.log = log

    def _headers(self, meta: dict | None = None, extra: dict | None = None) -> dict:
        h = {
            "Authorization": f"LOW {self.access}:{self.secret}",
            "x-archive-auto-make-bucket": "1",
            "x-archive-meta-collection": _meta_value(self.collection),
            "x-archive-meta-mediatype": "movies",
        }
        for k, v in (meta or {}).items():
            if v in (None, ""):
                continue
            h[f"x-archive-meta-{k}"] = _meta_value(v)
        if extra:
            h.update(extra)
        return h

    def upload_file(self, identifier: str, file_path: Path, meta: dict | None = None,
                    extra_headers: dict | None = None) -> bool:
        if not REQ_OK:
            self.log("[ia] erro: biblioteca 'requests' indisponível.")
            return False
        if not (self.access and self.secret):
            self.log("[ia] erro: access/secret key vazios.")
            return False
        if not file_path.exists():
            self.log(f"[ia] arquivo não existe: {file_path}")
            return False
        url = f"{self.BASE}/{urllib.parse.quote(identifier)}/{urllib.parse.quote(file_path.name)}"
        size = file_path.stat().st_size
        self.log(f"[ia] PUT {url} ({size / 1024 / 1024:.1f} MiB)")
        headers = self._headers(meta=meta, extra=extra_headers)
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                with file_path.open("rb") as f:
                    resp = requests.put(url, data=f, headers=headers, timeout=(30, 1800))
                if 200 <= resp.status_code < 300:
                    self.log(f"[ia] ok ({resp.status_code}) https://archive.org/details/{identifier}")
                    return True
                self.log(f"[ia] tentativa {attempt} falhou: HTTP {resp.status_code} {resp.text[:300]}")
                if resp.status_code in (400, 401, 403, 409):
                    return False  # auth / collection problems won't recover
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.log(f"[ia] tentativa {attempt} exception: {exc}")
            time.sleep(2 * attempt)
        if last_exc is not None:
            self.log(f"[ia] desistindo: {last_exc}")
        return False


def fmt_duration(secs) -> str:
    try:
        s = int(secs or 0)
    except Exception:  # noqa: BLE001
        return "?"
    if s <= 0:
        return "?"
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


_NON_BMP_RE = re.compile(r"[^\u0000-\uFFFF]")


def safe_tk(s) -> str:
    """Replace astral (>U+FFFF) chars Tk's UCS-2 build can't render."""
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    return _NON_BMP_RE.sub("□", s)


def short(s: str, n: int) -> str:
    s = safe_tk(s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# Player clients that don't require the YouTube n-challenge JS solver.
# Order matters: yt-dlp tries them left-to-right.
YT_EXTRACTOR_ARGS = [
    "--extractor-args",
    "youtube:player_client=ios,mweb,android_vr,web_safari,android,web,tv",
]


FORMATS = {
    "Vídeo — Melhor qualidade (MP4)": [
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/best",
        "--merge-output-format", "mp4",
    ],
    "Vídeo — 1080p máx (MP4)": [
        "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/best[height<=1080]",
        "--merge-output-format", "mp4",
    ],
    "Vídeo — 720p máx (MP4)": [
        "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/best[height<=720]",
        "--merge-output-format", "mp4",
    ],
    "Áudio — MP3 (320 kbps)": [
        "-f", "bestaudio/best",
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
    ],
    "Áudio — M4A (original)": [
        "-f", "bestaudio[ext=m4a]/bestaudio",
    ],
    "Melhor disponível (qualquer formato)": [
        "-f", "bv*+ba/best",
    ],
}


# ---------- entry rows ----------
class EntryRow(ttk.Frame):
    """One row in the playlist list: checkbox + thumb + title + duration."""

    def __init__(self, master, entry: dict, on_thumb_request) -> None:
        super().__init__(master, padding=(6, 4))
        self.entry = entry
        self.var_check = tk.BooleanVar(value=True)
        self.thumb_img = None  # keep reference to avoid GC
        self.configure(height=80)

        chk = ttk.Checkbutton(self, variable=self.var_check)
        chk.pack(side="left")

        # thumbnail placeholder — Frame with explicit pixel size so it is sized
        # in pixels (tk.Label width/height are in characters/lines without an image).
        thumb_holder = tk.Frame(self, width=120, height=68, bg="#1a2230")
        thumb_holder.pack(side="left", padx=(6, 8))
        thumb_holder.pack_propagate(False)
        self.lbl_thumb = tk.Label(thumb_holder, bg="#1a2230", relief="flat", borderwidth=0)
        self.lbl_thumb.pack(fill="both", expand=True)

        info = ttk.Frame(self)
        info.pack(side="left", fill="both", expand=True)
        title = entry.get("title") or entry.get("id") or "(sem título)"
        ttk.Label(
            info,
            text=short(title, 90),
            font=("TkDefaultFont", 10, "bold"),
            wraplength=600,
            justify="left",
        ).pack(anchor="w")
        meta = []
        if entry.get("uploader") or entry.get("channel"):
            meta.append(safe_tk(entry.get("uploader") or entry.get("channel")))
        d = fmt_duration(entry.get("duration"))
        if d != "?":
            meta.append(d)
        if meta:
            ttk.Label(info, text="  •  ".join(meta), foreground="#9aa7b8").pack(anchor="w")

        try:
            on_thumb_request(self)
        except Exception:  # noqa: BLE001
            pass

    def selected(self) -> bool:
        return bool(self.var_check.get())

    def url(self) -> str:
        # Prefer full URL if available; else build from extractor + id
        return self.entry.get("url") or self.entry.get("webpage_url") or ""

    def video_id(self) -> str:
        return self.entry.get("id") or ""

    def set_thumb(self, pil_image) -> None:
        if not PIL_OK:
            return
        try:
            img = pil_image.copy()
            img.thumbnail((120, 68))
            self.thumb_img = ImageTk.PhotoImage(img)
            self.lbl_thumb.configure(image=self.thumb_img, width=120, height=68)
        except Exception:  # noqa: BLE001
            pass


# ---------- main app ----------
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} — v{APP_VERSION}")
        self.geometry("960x700")
        self.minsize(820, 560)
        self.configure(bg="#0f1620")
        self._apply_window_icon()

        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.session_log = SessionLogger()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.entries: list[EntryRow] = []
        self.single_meta: dict | None = None
        self.single_thumb_img = None  # GC anchor

        self._setup_style()
        self._build_ui()
        self._check_binaries()
        self.after(80, self._drain_log_queue)

    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:  # noqa: BLE001
            pass
        style.configure(".", background="#0f1620", foreground="#d6e1ee", fieldbackground="#1a2230")
        style.configure("TFrame", background="#0f1620")
        style.configure("Card.TFrame", background="#141d2a")
        style.configure("TLabel", background="#0f1620", foreground="#d6e1ee")
        style.configure("Card.TLabel", background="#141d2a", foreground="#d6e1ee")
        style.configure("TLabelframe", background="#0f1620", foreground="#9aa7b8")
        style.configure("TLabelframe.Label", background="#0f1620", foreground="#9aa7b8")
        style.configure("TCheckbutton", background="#0f1620", foreground="#d6e1ee")
        style.map("TCheckbutton", background=[("active", "#0f1620")])
        style.configure("Accent.TButton", background="#2563eb", foreground="white")
        style.map("Accent.TButton", background=[("active", "#1d4ed8")])

    # ---------- UI ----------
    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        # --- top: URL + load
        frm_top = ttk.Frame(self)
        frm_top.pack(fill="x", **pad)
        ttk.Label(frm_top, text="URL:").grid(row=0, column=0, sticky="w")
        self.var_url = tk.StringVar()
        self.entry_url = ttk.Entry(frm_top, textvariable=self.var_url)
        self.entry_url.grid(row=0, column=1, sticky="we", padx=(6, 6))
        self.entry_url.bind("<Return>", lambda _e: self._start_load())
        self.btn_load = ttk.Button(frm_top, text="Carregar", style="Accent.TButton", command=self._start_load)
        self.btn_load.grid(row=0, column=2, sticky="e")
        frm_top.columnconfigure(1, weight=1)

        # --- format + output
        frm_cfg = ttk.Frame(self)
        frm_cfg.pack(fill="x", **pad)
        ttk.Label(frm_cfg, text="Formato:").grid(row=0, column=0, sticky="w")
        self.var_fmt = tk.StringVar(value=next(iter(FORMATS)))
        self.combo_fmt = ttk.Combobox(
            frm_cfg, textvariable=self.var_fmt, values=list(FORMATS.keys()), state="readonly", width=42
        )
        self.combo_fmt.grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(frm_cfg, text="Pasta:").grid(row=0, column=2, sticky="w")
        self.var_out = tk.StringVar(value=str(default_output_dir()))
        ent_out = ttk.Entry(frm_cfg, textvariable=self.var_out)
        ent_out.grid(row=0, column=3, sticky="we", padx=(6, 6))
        ttk.Button(frm_cfg, text="…", width=3, command=self._pick_dir).grid(row=0, column=4)
        frm_cfg.columnconfigure(3, weight=1)

        # --- options
        frm_opts = ttk.Frame(self)
        frm_opts.pack(fill="x", **pad)
        self.var_subs = tk.BooleanVar(value=False)
        self.var_thumb = tk.BooleanVar(value=False)
        self.var_cookie_mode = tk.StringVar(value="none")  # none | browser | file
        self.var_browser = tk.StringVar(value="chrome")
        self.var_cookie_file = tk.StringVar(value="")
        ttk.Checkbutton(frm_opts, text="Embutir legendas (PT/EN, quando houver)", variable=self.var_subs).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(frm_opts, text="Embutir thumbnail no arquivo", variable=self.var_thumb).pack(side="left")

        # Cookies row 1: mode selection
        frm_ck1 = ttk.Frame(self)
        frm_ck1.pack(fill="x", **pad)
        ttk.Label(frm_ck1, text="Cookies:").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(frm_ck1, text="Nenhum", variable=self.var_cookie_mode, value="none",
                        command=self._refresh_cookie_widgets).pack(side="left")
        ttk.Radiobutton(frm_ck1, text="Do navegador", variable=self.var_cookie_mode, value="browser",
                        command=self._refresh_cookie_widgets).pack(side="left", padx=(8, 0))
        self.combo_browser = ttk.Combobox(
            frm_ck1,
            textvariable=self.var_browser,
            values=["chrome", "edge", "firefox", "brave", "opera", "vivaldi", "chromium", "safari"],
            state="readonly",
            width=10,
        )
        self.combo_browser.pack(side="left", padx=(6, 12))
        ttk.Radiobutton(frm_ck1, text="Arquivo (.txt)", variable=self.var_cookie_mode, value="file",
                        command=self._refresh_cookie_widgets).pack(side="left")

        # Cookies row 2: file path (only enabled when mode=file)
        frm_ck2 = ttk.Frame(self)
        frm_ck2.pack(fill="x", **pad)
        ttk.Label(frm_ck2, text="Arquivo:").pack(side="left", padx=(0, 6))
        self.ent_cookie_file = ttk.Entry(frm_ck2, textvariable=self.var_cookie_file)
        self.ent_cookie_file.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_cookie_file = ttk.Button(frm_ck2, text="…", width=3, command=self._pick_cookie_file)
        self.btn_cookie_file.pack(side="left")
        self._refresh_cookie_widgets()

        # --- destination / archive.org upload
        cfg = load_config()
        self.var_dest = tk.StringVar(value=cfg.get("dest_mode", "local"))  # local | ia | ia_delete
        self.var_ia_access = tk.StringVar(value=cfg.get("ia_access", os.environ.get("IA_ACCESS_KEY", "")))
        self.var_ia_secret = tk.StringVar(value=cfg.get("ia_secret", os.environ.get("IA_SECRET_KEY", "")))
        self.var_ia_collection = tk.StringVar(value=cfg.get("ia_collection", "opensource_movies"))
        self.var_ia_creator = tk.StringVar(value=cfg.get("ia_creator", ""))

        frm_dst1 = ttk.Frame(self)
        frm_dst1.pack(fill="x", **pad)
        ttk.Label(frm_dst1, text="Destino:").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(frm_dst1, text="Só baixar (PC)", variable=self.var_dest, value="local",
                        command=self._refresh_ia_widgets).pack(side="left")
        ttk.Radiobutton(frm_dst1, text="Baixar + enviar pro archive.org",
                        variable=self.var_dest, value="ia",
                        command=self._refresh_ia_widgets).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(frm_dst1, text="Baixar + IA + apagar local",
                        variable=self.var_dest, value="ia_delete",
                        command=self._refresh_ia_widgets).pack(side="left", padx=(8, 0))

        self.frm_ia = ttk.LabelFrame(self, text="Internet Archive (S3 keys em https://archive.org/account/s3.php)")
        self.frm_ia.pack(fill="x", padx=10, pady=(4, 0))
        # row 1: access + secret
        frm_ia1 = ttk.Frame(self.frm_ia)
        frm_ia1.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(frm_ia1, text="Access:").pack(side="left")
        self.ent_ia_access = ttk.Entry(frm_ia1, textvariable=self.var_ia_access, width=22)
        self.ent_ia_access.pack(side="left", padx=(6, 12))
        ttk.Label(frm_ia1, text="Secret:").pack(side="left")
        self.ent_ia_secret = ttk.Entry(frm_ia1, textvariable=self.var_ia_secret, width=22, show="•")
        self.ent_ia_secret.pack(side="left", padx=(6, 12))
        self.var_ia_show = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm_ia1, text="Mostrar", variable=self.var_ia_show,
                        command=self._toggle_ia_show).pack(side="left")
        # row 2: collection + creator
        frm_ia2 = ttk.Frame(self.frm_ia)
        frm_ia2.pack(fill="x", padx=8, pady=(2, 6))
        ttk.Label(frm_ia2, text="Collection:").pack(side="left")
        self.combo_ia_coll = ttk.Combobox(
            frm_ia2, textvariable=self.var_ia_collection,
            values=["opensource_movies", "community_video", "test_collection"],
            width=20,
        )
        self.combo_ia_coll.pack(side="left", padx=(6, 12))
        ttk.Label(frm_ia2, text="Creator:").pack(side="left")
        self.ent_ia_creator = ttk.Entry(frm_ia2, textvariable=self.var_ia_creator, width=24)
        self.ent_ia_creator.pack(side="left", padx=(6, 12))
        ttk.Label(frm_ia2, text="(vazio = canal do vídeo)", foreground="#6b7a8c").pack(side="left")
        ttk.Button(frm_ia2, text="Esquecer keys salvas", command=self._forget_ia_keys
                   ).pack(side="right")
        self._refresh_ia_widgets()

        # Pack bottom-to-top so the action bar and status are always visible
        # even when the content area is tall.

        # --- status bar (very bottom)
        self.var_status = tk.StringVar(value="Cole uma URL e clique em Carregar.")
        ttk.Label(self, textvariable=self.var_status, anchor="w").pack(
            side="bottom", fill="x", padx=12, pady=(0, 8)
        )

        # --- action bar
        frm_btn = ttk.Frame(self)
        frm_btn.pack(side="bottom", fill="x", padx=10, pady=(4, 6))
        self.btn_download = ttk.Button(
            frm_btn, text="Baixar selecionados", style="Accent.TButton",
            command=self._start_download, state="disabled",
        )
        self.btn_download.pack(side="left")
        self.btn_cancel = ttk.Button(frm_btn, text="Cancelar", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=(8, 0))
        self.btn_open = ttk.Button(frm_btn, text="Abrir pasta", command=self._open_dir)
        self.btn_open.pack(side="right")
        ttk.Button(frm_btn, text="Pasta de logs", command=self._open_logs_dir).pack(side="right", padx=(0, 6))
        ttk.Button(frm_btn, text="Abrir log", command=self._open_current_log).pack(side="right", padx=(0, 6))

        # --- log
        frm_log = ttk.LabelFrame(self, text="Log")
        frm_log.pack(side="bottom", fill="x", padx=10, pady=(4, 0))
        self.txt_log = tk.Text(
            frm_log, height=6, wrap="word", state="disabled",
            bg="#0b0f14", fg="#d6e1ee", insertbackground="#d6e1ee", relief="flat",
        )
        self.txt_log.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb = ttk.Scrollbar(frm_log, orient="vertical", command=self.txt_log.yview)
        sb.pack(side="right", fill="y")
        self.txt_log.config(yscrollcommand=sb.set)

        # --- progress
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.pack(side="bottom", fill="x", padx=10, pady=(4, 0))

        # --- main content area (takes any remaining space)
        self.frm_content = ttk.Frame(self, style="Card.TFrame")
        self.frm_content.pack(side="top", fill="both", expand=True, padx=10, pady=4)

        # initial empty view (after all buttons exist)
        self._show_empty_view()

    # ---------- view switchers ----------
    def _clear_content(self) -> None:
        for w in self.frm_content.winfo_children():
            w.destroy()
        self.entries = []
        self.single_meta = None
        self.single_thumb_img = None

    def _show_empty_view(self) -> None:
        self._clear_content()
        f = ttk.Frame(self.frm_content, style="Card.TFrame")
        f.pack(fill="both", expand=True)
        ttk.Label(
            f,
            text="Cole o link de um vídeo ou playlist e clique em Carregar.\n"
                 "Os itens vão aparecer aqui pra você escolher o que baixar.",
            style="Card.TLabel",
            justify="center",
        ).place(relx=0.5, rely=0.5, anchor="center")
        self.btn_download.config(state="disabled")

    def _show_loading_view(self, msg: str = "Carregando metadados…") -> None:
        self._clear_content()
        f = ttk.Frame(self.frm_content, style="Card.TFrame")
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=msg, style="Card.TLabel").place(relx=0.5, rely=0.5, anchor="center")
        self.btn_download.config(state="disabled")

    def _show_single_view(self, meta: dict) -> None:
        self._clear_content()
        self.single_meta = meta
        f = ttk.Frame(self.frm_content, style="Card.TFrame", padding=14)
        f.pack(fill="both", expand=True)

        self.lbl_single_thumb = tk.Label(f, bg="#0b0f14", width=480, height=270)
        self.lbl_single_thumb.pack(side="top", pady=(0, 10))

        ttk.Label(f, text=safe_tk(meta.get("title") or "(sem título)"), style="Card.TLabel",
                  font=("TkDefaultFont", 12, "bold"), wraplength=860, justify="left").pack(anchor="w")
        meta_line = []
        if meta.get("uploader") or meta.get("channel"):
            meta_line.append(safe_tk(meta.get("uploader") or meta.get("channel")))
        d = fmt_duration(meta.get("duration"))
        if d != "?":
            meta_line.append(d)
        if meta.get("view_count"):
            meta_line.append(f"{meta['view_count']:,} views".replace(",", "."))
        ttk.Label(f, text="  •  ".join(meta_line), style="Card.TLabel", foreground="#9aa7b8").pack(anchor="w", pady=(2, 0))

        self.btn_download.config(state="normal", text="Baixar")
        # async fetch big thumbnail
        thumb_url = self._best_thumbnail(meta)
        if thumb_url and PIL_OK:
            threading.Thread(target=self._fetch_single_thumb, args=(thumb_url,), daemon=True).start()

    def _show_playlist_view(self, info: dict) -> None:
        self._clear_content()
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            self._show_empty_view()
            self._log("[aviso] Playlist sem itens.")
            return

        outer = ttk.Frame(self.frm_content, style="Card.TFrame", padding=8)
        outer.pack(fill="both", expand=True)

        # header
        head = ttk.Frame(outer, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=short(info.get("title") or "Playlist", 110), style="Card.TLabel",
                  font=("TkDefaultFont", 11, "bold")).pack(side="left")
        ttk.Label(head, text=f"  ({len(entries)} itens)", style="Card.TLabel", foreground="#9aa7b8").pack(side="left")
        ttk.Button(head, text="Marcar todos", command=lambda: self._set_all(True)).pack(side="right", padx=(4, 0))
        ttk.Button(head, text="Desmarcar todos", command=lambda: self._set_all(False)).pack(side="right")

        # scrollable list
        list_frame = tk.Frame(outer, bg="#141d2a")
        list_frame.pack(fill="both", expand=True, pady=(8, 0))
        canvas = tk.Canvas(list_frame, bg="#141d2a", highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="#141d2a")
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Force layout pass so canvas has its real width before we add rows.
        self.update_idletasks()

        def _sync_size(_e=None):
            w = max(canvas.winfo_width(), 1)
            canvas.itemconfigure(win, width=w)
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", _sync_size)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        added = 0
        for entry in entries:
            try:
                row = EntryRow(inner, entry, on_thumb_request=self._queue_thumb)
                row.pack(fill="x", pady=2, padx=2)
                tk.Frame(inner, bg="#1f2a3a", height=1).pack(fill="x")
                self.entries.append(row)
                added += 1
            except Exception as exc:  # noqa: BLE001
                self._log(f"[aviso] item {added + 1} ignorado: {exc}")

        self._log(f"[info] {added}/{len(entries)} itens montados na lista.")

        # Force a final size sync so rows render even if <Configure> hasn't fired yet
        self.update_idletasks()
        _sync_size()
        self.after(50, _sync_size)
        self.after(200, _sync_size)

        self.btn_download.config(state="normal", text="Baixar selecionados")

    def _set_all(self, value: bool) -> None:
        for r in self.entries:
            r.var_check.set(value)

    # ---------- thumbnails ----------
    def _best_thumbnail(self, meta: dict) -> str | None:
        thumbs = meta.get("thumbnails") or []
        if thumbs:
            for t in reversed(thumbs):
                if t.get("url"):
                    return t["url"]
        if meta.get("thumbnail"):
            return meta["thumbnail"]
        vid = meta.get("id")
        if vid and (meta.get("extractor") or "").lower().startswith("youtube"):
            return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        return None

    def _queue_thumb(self, row: EntryRow) -> None:
        if not PIL_OK:
            return
        url = self._best_thumbnail(row.entry)
        if not url:
            return
        threading.Thread(target=self._fetch_row_thumb, args=(row, url), daemon=True).start()

    def _fetch_row_thumb(self, row: EntryRow, url: str) -> None:
        img = self._download_image(url)
        if img is not None:
            self.after(0, lambda: row.set_thumb(img))

    def _fetch_single_thumb(self, url: str) -> None:
        img = self._download_image(url)
        if img is None:
            return
        try:
            img2 = img.copy()
            img2.thumbnail((640, 360))
            tkimg = ImageTk.PhotoImage(img2)

            def apply():
                self.single_thumb_img = tkimg
                self.lbl_single_thumb.configure(image=tkimg, width=tkimg.width(), height=tkimg.height())

            self.after(0, apply)
        except Exception:  # noqa: BLE001
            pass

    def _download_image(self, url: str):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:  # noqa: BLE001
            return None

    # ---------- metadata loading ----------
    def _start_load(self) -> None:
        url = self.var_url.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Cole uma URL primeiro.")
            return
        ytdlp = resource_dir() / "yt-dlp.exe"
        if not ytdlp.exists() and not (resource_dir() / "yt-dlp").exists():
            messagebox.showerror(APP_TITLE, f"yt-dlp não encontrado em:\n{resource_dir()}")
            return

        self._show_loading_view()
        self.var_status.set("Carregando metadados…")
        self.btn_load.config(state="disabled")
        threading.Thread(target=self._load_meta, args=(url,), daemon=True).start()

    def _load_meta(self, url: str) -> None:
        ytdlp = resource_dir() / ("yt-dlp.exe" if sys.platform.startswith("win") else "yt-dlp")
        cmd = [str(ytdlp), "-J", "--flat-playlist", "--no-warnings"]
        cmd += self._cookie_args()
        cmd += YT_EXTRACTOR_ARGS
        cmd.append(url)
        si, cf = hidden_startupinfo()
        try:
            res = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=cf,
                startupinfo=si,
                env=child_env(),
                timeout=120,
            )
            if res.returncode != 0:
                err = (res.stderr or b"").decode("utf-8", "replace").strip()
                self.after(0, lambda: self._on_meta_error(err or f"yt-dlp falhou (código {res.returncode})"))
                return
            info = json.loads(res.stdout.decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._on_meta_error(str(exc)))
            return

        def apply():
            self.btn_load.config(state="normal")
            if info.get("_type") == "playlist" or info.get("entries"):
                self._show_playlist_view(info)
                self.var_status.set(f"Playlist carregada: {len(info.get('entries') or [])} itens.")
            else:
                self._show_single_view(info)
                self.var_status.set("Vídeo carregado.")

        self.after(0, apply)

    def _on_meta_error(self, msg: str) -> None:
        self.btn_load.config(state="normal")
        self._show_empty_view()
        self.var_status.set("Falha ao carregar.")
        self._log(f"[erro] {msg}")
        messagebox.showerror(APP_TITLE, f"Falha ao carregar a URL:\n\n{msg}")

    # ---------- download ----------
    def _start_download(self) -> None:
        out_dir = Path(self.var_out.get()).expanduser()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Não foi possível criar a pasta:\n{exc}")
            return

        dest_mode = self.var_dest.get()
        if dest_mode in ("ia", "ia_delete"):
            if not REQ_OK:
                messagebox.showerror(APP_TITLE, "Biblioteca 'requests' indisponível neste build — upload IA desativado.")
                return
            if not self.var_ia_access.get().strip() or not self.var_ia_secret.get().strip():
                messagebox.showwarning(APP_TITLE, "Preencha Access key e Secret key do archive.org.")
                return

        # persist user prefs
        self._save_user_config()

        urls: list[str] = []
        if self.entries:
            for r in self.entries:
                if r.selected():
                    u = r.url() or ""
                    if u.startswith("http"):
                        urls.append(u)
                    elif r.video_id():
                        urls.append(f"https://www.youtube.com/watch?v={r.video_id()}")
            if not urls:
                messagebox.showwarning(APP_TITLE, "Selecione ao menos um item.")
                return
        elif self.single_meta:
            u = self.single_meta.get("webpage_url") or self.single_meta.get("original_url") or self.var_url.get().strip()
            if u:
                urls.append(u)
        else:
            urls.append(self.var_url.get().strip())

        self.btn_download.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.btn_load.config(state="disabled")
        self.progress["value"] = 0
        threading.Thread(target=self._run_downloads, args=(urls, out_dir, dest_mode), daemon=True).start()

    def _run_downloads(self, urls: list[str], out_dir: Path, dest_mode: str = "local") -> None:
        rd = resource_dir()
        ytdlp = rd / ("yt-dlp.exe" if sys.platform.startswith("win") else "yt-dlp")
        ffmpeg_exists = (rd / "ffmpeg.exe").exists() or (rd / "ffmpeg").exists()
        ia_active = dest_mode in ("ia", "ia_delete")

        uploader: IAUploader | None = None
        if ia_active:
            uploader = IAUploader(
                self.var_ia_access.get().strip(),
                self.var_ia_secret.get().strip(),
                self.var_ia_collection.get().strip() or "opensource_movies",
                self._enqueue_log,
            )

        # marker yt-dlp will print AFTER the final merged file is in place
        DLFILE_PREFIX = "DLFILE="
        INFOJSON_PREFIX = "INFOJSON="

        total = len(urls)
        ok = 0
        ok_uploads = 0
        for idx, url in enumerate(urls, start=1):
            if self.proc is not None and self.proc.poll() is None:
                pass  # safety
            self.log_queue.put(f"\n=== [{idx}/{total}] {url} ===")
            self.after(0, lambda i=idx, t=total: self.var_status.set(f"Baixando {i}/{t}…"))
            cmd = [str(ytdlp)]
            cmd += FORMATS[self.var_fmt.get()]
            if ffmpeg_exists:
                cmd += ["--ffmpeg-location", str(rd)]
            cmd += ["--no-playlist"]  # we already iterate explicitly
            cmd += self._cookie_args()
            cmd += YT_EXTRACTOR_ARGS
            if self.var_subs.get():
                cmd += ["--write-subs", "--write-auto-subs", "--sub-langs", "pt.*,en.*", "--embed-subs"]
            if self.var_thumb.get():
                cmd += ["--embed-thumbnail"]
            if ia_active:
                cmd += ["--write-info-json"]
                cmd += ["--print", f"after_move:{INFOJSON_PREFIX}%(infojson_filename)s"]
            cmd += ["--print", f"after_move:{DLFILE_PREFIX}%(filepath)s"]
            cmd += [
                "--no-mtime",
                "--newline",
                "--progress",
                "--no-part",
                "-o", str(out_dir / "%(title).200B [%(id)s].%(ext)s"),
                url,
            ]
            self.log_queue.put("$ " + " ".join(_quote(c) for c in cmd))

            final_path: Path | None = None
            info_json_path: Path | None = None

            si, cf = hidden_startupinfo()
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=cf,
                    startupinfo=si,
                    env=child_env(),
                    cwd=str(out_dir),
                )
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    line = line.rstrip("\r\n")
                    if line.startswith(DLFILE_PREFIX):
                        try:
                            final_path = Path(line[len(DLFILE_PREFIX):]).resolve()
                        except Exception:  # noqa: BLE001
                            pass
                        continue
                    if line.startswith(INFOJSON_PREFIX):
                        try:
                            info_json_path = Path(line[len(INFOJSON_PREFIX):]).resolve()
                        except Exception:  # noqa: BLE001
                            pass
                        continue
                    self.log_queue.put(line)
                rc = self.proc.wait()
            except FileNotFoundError as exc:
                self.log_queue.put(f"[erro] {exc}")
                rc = -1
            except Exception as exc:  # noqa: BLE001
                self.log_queue.put(f"[erro] {exc}")
                rc = -1
            finally:
                self.proc = None

            if rc == 0:
                ok += 1
                self.log_queue.put(f"[ok] item {idx}/{total} concluído.")
                if ia_active and uploader is not None and final_path is not None:
                    uploaded = self._upload_to_ia(uploader, final_path, info_json_path, idx, total)
                    if uploaded:
                        ok_uploads += 1
                        if dest_mode == "ia_delete":
                            self._cleanup_local(final_path, info_json_path)
                elif ia_active:
                    self.log_queue.put("[ia] aviso: caminho final do arquivo não capturado, upload pulado.")
            else:
                self.log_queue.put(f"[falha] item {idx}/{total} (código {rc}).")

            # update overall progress per-item
            self.after(0, lambda v=(idx / total) * 100: self.progress.configure(value=v))

        def done():
            self.btn_download.config(state="normal")
            self.btn_cancel.config(state="disabled")
            self.btn_load.config(state="normal")
            if ia_active:
                self.var_status.set(f"Concluído: {ok}/{total} baixados, {ok_uploads}/{ok} subidos pro IA.")
            else:
                self.var_status.set(f"Concluído: {ok}/{total} ok.")
            if ok == total:
                self.progress["value"] = 100

        self.after(0, done)

    def _enqueue_log(self, line: str) -> None:
        """Thread-safe log entry point used by IAUploader."""
        self.log_queue.put(line)

    def _upload_to_ia(
        self,
        uploader: IAUploader,
        media_path: Path,
        info_json_path: Path | None,
        idx: int,
        total: int,
    ) -> bool:
        """Upload the merged media file (and optional info.json) to IA."""
        info: dict = {}
        if info_json_path is not None and info_json_path.exists():
            try:
                info = json.loads(info_json_path.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:  # noqa: BLE001
                self.log_queue.put(f"[ia] aviso: info.json ilegível ({exc})")

        title = info.get("title") or media_path.stem
        video_id = info.get("id") or ""
        if not video_id:
            m = re.search(r"\[([A-Za-z0-9_-]{6,32})\]", media_path.stem)
            if m:
                video_id = m.group(1)
        identifier = archive_identifier(title, video_id)

        creator_override = self.var_ia_creator.get().strip()
        creator = creator_override or info.get("uploader") or info.get("channel") or ""
        source = info.get("webpage_url") or info.get("original_url") or ""
        description = info.get("description") or ""
        tags = info.get("tags") or []
        if isinstance(tags, list):
            subject = ";".join(str(t) for t in tags[:25])
        else:
            subject = str(tags) if tags else ""
        upload_date = info.get("upload_date") or ""  # YYYYMMDD
        date_iso = ""
        if isinstance(upload_date, str) and len(upload_date) == 8 and upload_date.isdigit():
            date_iso = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

        meta = {
            "title": title,
            "creator": creator,
            "description": description,
            "source": source,
            "subject": subject,
            "date": date_iso,
            "language": (info.get("language") or "").strip(),
        }

        self.log_queue.put(f"[ia] subindo item {idx}/{total} -> {identifier}")
        ok_main = uploader.upload_file(identifier, media_path, meta=meta)
        if ok_main and info_json_path is not None and info_json_path.exists():
            # also upload the info.json (no metadata headers needed on second file)
            uploader.upload_file(identifier, info_json_path, meta=None)
        return ok_main

    def _cleanup_local(self, media_path: Path, info_json_path: Path | None) -> None:
        for p in (media_path, info_json_path):
            if p is None:
                continue
            try:
                if p.exists():
                    p.unlink()
                    self.log_queue.put(f"[ia] arquivo local removido: {p.name}")
            except Exception as exc:  # noqa: BLE001
                self.log_queue.put(f"[ia] aviso: não consegui apagar {p.name}: {exc}")

    def _cancel(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.var_status.set("Cancelando…")
            except Exception as exc:  # noqa: BLE001
                self._log(f"[erro] cancelar: {exc}")

    # ---------- log + misc ----------
    def _log(self, line: str) -> None:
        # File log keeps the original chars; UI log gets sanitized for Tk.
        self.session_log.write(line.rstrip("\n"))
        ui_line = safe_tk(line)
        try:
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", ui_line if ui_line.endswith("\n") else ui_line + "\n")
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        except Exception:  # noqa: BLE001
            pass

    def _open_current_log(self) -> None:
        p = self.session_log.path
        if not p.exists():
            messagebox.showinfo(APP_TITLE, "Ainda não há arquivo de log.")
            return
        self._open_path(p)

    def _open_logs_dir(self) -> None:
        self._open_path(logs_dir())

    def _open_path(self, path: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Falha ao abrir:\n{exc}")

    def _on_close(self) -> None:
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        self.session_log.close()
        self.destroy()

    def _drain_log_queue(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._handle_line(line)
        except queue.Empty:
            pass
        self.after(80, self._drain_log_queue)

    def _handle_line(self, line: str) -> None:
        line = line.rstrip("\r\n")
        if not line:
            return
        m = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line)
        if m:
            try:
                self.progress["value"] = float(m.group(1))
            except Exception:  # noqa: BLE001
                pass
        self._log(line)

    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.var_out.get() or str(Path.home()))
        if d:
            self.var_out.set(d)

    def _pick_cookie_file(self) -> None:
        f = filedialog.askopenfilename(
            title="Selecione o arquivo de cookies (Netscape .txt)",
            filetypes=[("Cookies (Netscape)", "*.txt"), ("Todos os arquivos", "*.*")],
            initialdir=str(Path.home()),
        )
        if f:
            self.var_cookie_file.set(f)
            self.var_cookie_mode.set("file")
            self._refresh_cookie_widgets()

    def _refresh_cookie_widgets(self) -> None:
        mode = self.var_cookie_mode.get()
        try:
            self.combo_browser.configure(state="readonly" if mode == "browser" else "disabled")
            self.ent_cookie_file.configure(state="normal" if mode == "file" else "disabled")
            self.btn_cookie_file.configure(state="normal" if mode == "file" else "disabled")
        except Exception:  # noqa: BLE001
            pass

    def _cookie_args(self) -> list:
        mode = self.var_cookie_mode.get()
        if mode == "browser":
            return ["--cookies-from-browser", self.var_browser.get()]
        if mode == "file":
            p = self.var_cookie_file.get().strip()
            if p and Path(p).exists():
                return ["--cookies", p]
            self._log("[aviso] arquivo de cookies não encontrado, ignorando.")
        return []

    def _refresh_ia_widgets(self) -> None:
        ia_active = self.var_dest.get() in ("ia", "ia_delete")
        state = "normal" if ia_active else "disabled"
        try:
            for w in (self.ent_ia_access, self.ent_ia_secret, self.ent_ia_creator):
                w.configure(state=state)
            self.combo_ia_coll.configure(state=("normal" if ia_active else "disabled"))
        except Exception:  # noqa: BLE001
            pass

    def _toggle_ia_show(self) -> None:
        try:
            self.ent_ia_secret.configure(show="" if self.var_ia_show.get() else "•")
        except Exception:  # noqa: BLE001
            pass

    def _save_user_config(self) -> None:
        try:
            data = load_config()
            data.update({
                "dest_mode": self.var_dest.get(),
                "ia_access": self.var_ia_access.get().strip(),
                "ia_secret": self.var_ia_secret.get().strip(),
                "ia_collection": self.var_ia_collection.get().strip(),
                "ia_creator": self.var_ia_creator.get().strip(),
            })
            save_config(data)
        except Exception:  # noqa: BLE001
            pass

    def _forget_ia_keys(self) -> None:
        if not messagebox.askyesno(APP_TITLE,
                                   "Apagar Access key e Secret key salvas em config.json?"):
            return
        self.var_ia_access.set("")
        self.var_ia_secret.set("")
        try:
            data = load_config()
            for k in ("ia_access", "ia_secret"):
                data.pop(k, None)
            save_config(data)
        except Exception as exc:  # noqa: BLE001
            self._log(f"[aviso] falha ao limpar config: {exc}")
        self._log("[ok] IA keys removidas do config.")

    def _open_dir(self) -> None:
        path = self.var_out.get()
        if not path or not Path(path).exists():
            messagebox.showwarning(APP_TITLE, "Pasta inválida.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Falha ao abrir a pasta:\n{exc}")

    def _check_binaries(self) -> None:
        rd = resource_dir()
        self._log(f"[info] {APP_TITLE} v{APP_VERSION}")
        self._log(f"[info] Arquivo de log: {self.session_log.path}")
        if getattr(sys, "frozen", False):
            self._log(f"[info] Executável: {sys.executable}")
            threading.Thread(target=self._log_exe_sha256, daemon=True).start()
        names = (
            ["yt-dlp.exe", "ffmpeg.exe", "deno.exe"]
            if sys.platform.startswith("win")
            else ["yt-dlp", "ffmpeg", "deno"]
        )
        missing = [n for n in names if not (rd / n).exists()]
        if missing:
            self._log(f"[aviso] binários ausentes em {rd}: {', '.join(missing)}")
        else:
            self._log(f"[ok] binários encontrados em: {rd}")
        if not PIL_OK:
            self._log("[aviso] Pillow não disponível — thumbnails desativadas.")
        if not REQ_OK:
            self._log("[aviso] requests não disponível — upload IA desativado.")
        if _dpapi_available():
            self._log("[info] DPAPI disponível — IA keys serão criptografadas em config.json.")
        cfg = config_path()
        if cfg.exists():
            self._log(f"[info] Config: {cfg}")

    def _log_exe_sha256(self) -> None:
        try:
            digest = exe_sha256()
            if digest:
                self.log_queue.put(f"[info] SHA256 do .exe: {digest}")
        except Exception:  # noqa: BLE001
            pass

    def _apply_window_icon(self) -> None:
        """Set the Tk window/taskbar icon from bundled icon.ico / logo_square.png."""
        rd = resource_dir()
        # On Windows .ico is preferred for crisp taskbar/title-bar icons.
        if sys.platform.startswith("win"):
            ico = rd / "icon.ico"
            if ico.exists():
                try:
                    self.iconbitmap(default=str(ico))
                    return
                except Exception:  # noqa: BLE001
                    pass
        png = rd / "logo_square.png"
        if png.exists() and PIL_OK:
            try:
                img = Image.open(png)
                self._win_icon = ImageTk.PhotoImage(img)  # keep ref alive
                self.iconphoto(True, self._win_icon)
            except Exception:  # noqa: BLE001
                pass


def _quote(s: str) -> str:
    if " " in s or '"' in s:
        return '"' + s.replace('"', '\\"') + '"'
    return s


def main() -> None:
    try:
        app = App()
        try:
            from tkinter import font as tkfont

            tkfont.nametofont("TkDefaultFont").configure(size=10)
        except Exception:  # noqa: BLE001
            pass
        app.mainloop()
    except Exception as exc:  # noqa: BLE001
        try:
            messagebox.showerror(APP_TITLE, str(exc))
        except Exception:  # noqa: BLE001
            print(f"Erro fatal: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
