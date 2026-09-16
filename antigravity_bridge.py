#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
ANTIGRAVITY TELEGRAM MOBILE BRIDGE (Gemini 3.8 Flash High DX)
=============================================================================
Puente móvil para controlar Google Antigravity y repositorios de desarrollo
de forma remota desde Telegram (ideal para trabajar en movilidad / Quito).

Características principales:
- Modelo: Gemini 3.8 Flash High por defecto con selector dinámico (/models).
- Sesiones filtradas por proyecto: Solo muestra los chats del proyecto activo.
- Vista enriquecida al cargar sesión: Última interacción (usuario + agente),
  detección de planes y walkthroughs con botones inmediatos.
- Manejo seguro de Markdown: Cero errores de 'Can't parse entities'.
- Botones interactivos optimizados: Soporte 100% robusto para CallbackQuery.
- Cerebro & Planes: Detección de implementation_plan.md y botón 'Ejecutar Plan'.
- Feedback en tiempo real: ChatAction.TYPING + contador de tiempo transcurrido.
- Manejo inteligente de respuestas: Envío de documentos .md para outputs extensos.
- Git Móvil: /diff, /commit (con generación automática de mensajes IA) y push.
- Persistencia de estado: Recuerda proyecto, sesión y modelo en bot_state.json.
- Ayuda sensible al contexto: /? o /help muestra comandos según el estado actual.
- Control de navegación: Entrar y salir de sesiones y proyectos con un comando.

Autor: Gerson Javier Castellanos Niño
GitHub: https://github.com/gersonja
LinkedIn: https://www.linkedin.com/in/gersonjavier/
Licencia: MIT (Copyright (c) 2026 Gerson Javier Castellanos Niño)
=============================================================================
"""

import os
import re
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import glob
import json
import time
import shutil
import base64
import asyncio
import sqlite3
import datetime
import subprocess
import ctypes
import urllib.request
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("antigravity_bridge")

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =============================================================================
# CARGADOR DE ENTORNO NATIVO (.env)
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_dotenv_custom(env_path: Optional[str] = None) -> Optional[str]:
    r"""
    Carga variables de entorno desde un archivo .env si existe, sin dependencias externas.
    Busca en el path especificado, en la carpeta del script, o en el directorio de trabajo actual.
    """
    candidates = []
    if env_path:
        candidates.append(env_path)
    candidates.extend([
        os.path.join(BASE_DIR, ".env"),
        os.path.join(os.getcwd(), ".env"),
    ])

    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
                print(f"[Config] Archivo .env cargado exitosamente desde: {p}")
                return p
            except Exception as e:
                print(f"[Config Error] Error leyendo {p}: {e}")
    return None

LOADED_ENV_PATH = load_dotenv_custom()

# =============================================================================
# CONFIGURACIÓN Y SEGURIDAD (DESDE .ENV O VARIABLES DE ENTORNO)
# =============================================================================
BOT_TOKEN = os.environ.get("ANTIGRAVITY_BOT_TOKEN", "").strip()
raw_uid = os.environ.get("ANTIGRAVITY_USER_ID", "").strip()
MY_USER_ID = int(raw_uid) if raw_uid.isdigit() else 0

raw_roots = os.environ.get("ANTIGRAVITY_WORKSPACE_ROOTS", BASE_DIR)
WORKSPACE_ROOTS = [os.path.expanduser(p.strip()) for p in re.split(r"[,;]", raw_roots) if p.strip()]

DEFAULT_PROJECT = os.environ.get("ANTIGRAVITY_DEFAULT_PROJECT", BASE_DIR)
STATE_FILE = os.environ.get(
    "ANTIGRAVITY_STATE_FILE",
    os.path.join(BASE_DIR, "bot_state.json")
)
if not os.path.exists(os.path.dirname(STATE_FILE)):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

DEFAULT_MODEL = os.environ.get("ANTIGRAVITY_DEFAULT_MODEL", "auto")
DEFAULT_AUTOPUSH = os.environ.get("ANTIGRAVITY_DEFAULT_AUTOPUSH", "false").lower() in ("true", "1", "yes")
DEFAULT_EXECUTION_MODE = os.environ.get("ANTIGRAVITY_DEFAULT_MODE", "accept-edits")

WATCHDOG_ENABLED = os.environ.get("ANTIGRAVITY_WATCHDOG_ENABLED", "true").lower() in ("true", "1", "yes")
WATCHDOG_INTERVAL = int(os.environ.get("ANTIGRAVITY_WATCHDOG_INTERVAL", "45"))
DEFAULT_HEALTH_URL = os.environ.get("ANTIGRAVITY_DEFAULT_HEALTH_URL", "").strip()
TASK_TIMEOUT = int(os.environ.get("ANTIGRAVITY_TASK_TIMEOUT", "300"))
# Timeout por inactividad entre pasos: si no hay avance en este tiempo, se considera estancada.
# 0 = sin timeout por inactividad (deshabilitado). Por defecto: 600s (10 min) para máxima holgura en procesos pesados y reintentos de API.
STEP_IDLE_TIMEOUT = int(os.environ.get("ANTIGRAVITY_STEP_IDLE_TIMEOUT", "600"))
# Límite global de seguridad (en segundos). 0 = sin límite global (guiado 100% por actividad de pasos)
MAX_TASK_TIMEOUT = int(os.environ.get("ANTIGRAVITY_MAX_TASK_TIMEOUT", "0"))


# Rutas de Antigravity en Windows
CLI_DB_PATH = os.path.expanduser(r"~\.gemini\antigravity-cli\conversation_summaries.db")
CLI_CONV_DIR = os.path.expanduser(r"~\.gemini\antigravity-cli\conversations")
CLI_BRAIN_DIR = os.path.expanduser(r"~\.gemini\antigravity-cli\brain")

IDE_DB_PATH = os.path.expanduser(r"~\.gemini\antigravity-ide\conversation_summaries.db")
IDE_CONV_DIR = os.path.expanduser(r"~\.gemini\antigravity-ide\conversations")
IDE_BRAIN_DIR = os.path.expanduser(r"~\.gemini\antigravity-ide\brain")

AVAILABLE_MODELS = {
    "auto": "🎯 Auto-Router Inteligente (Recomendado)",
    "gemini-3.8-flash-high": "⚡ Gemini 3.8 Flash High",
    "gemini-3.8-flash-medium": "🚀 Gemini 3.8 Flash Medium",
    "gemini-3.7-flash-high": "💡 Gemini 3.7 Flash High",
    "claude-sonnet-4-6": "🧠 Claude Sonnet 4.6 (Thinking)",
    "claude-opus-4-6-thinking": "🏛️ Claude Opus 4.6 (Thinking)",
    "gpt-oss-120b-medium": "🌐 GPT-OSS 120B",
}

AVAILABLE_MODES = {
    "accept-edits": "⚡ Directo (Ejecución y Edición Inmediata)",
    "plan": "🧠 Planificación (Arquitectura e Implementation Plan)",
}

# Cadena oficial de conmutación en cascada ante errores de saturación (503 / capacidad / cuotas)
MODEL_CASCADE_CHAIN = [
    "gemini-3.8-flash-high",
    "gemini-3.8-flash-medium",
    "gemini-3.7-flash-high",
    "claude-sonnet-4-6",
]

def is_model_capacity_or_server_error(output: str) -> bool:
    """Detecta si la salida de agy corresponde a un fallo de infraestructura del modelo (503, capacidad, cuotas, saturación)."""
    if not output:
        return False
    out_lower = output.lower()
    signals = [
        "no capacity available for model",
        "unavailable (code 503)",
        "(code 503)",
        "code 503",
        "error 503",
        "http 503",
        "status code 503",
        "resourceexhausted",
        "rate limit exceeded",
        "rate limit",
        "quota exceeded",
        "overloaded",
        "model is currently overloaded",
        "server is overloaded",
    ]
    return any(sig in out_lower for sig in signals)

def get_next_cascade_model(current_model: str, attempted: List[str]) -> Optional[str]:
    """Retorna el siguiente modelo en la cadena de cascada que no haya sido intentado todavía."""
    if current_model in MODEL_CASCADE_CHAIN:
        start_idx = MODEL_CASCADE_CHAIN.index(current_model) + 1
        for m in MODEL_CASCADE_CHAIN[start_idx:]:
            if m not in attempted:
                return m

    for m in MODEL_CASCADE_CHAIN:
        if m not in attempted and m != current_model:
            return m
            
    return None

CONTINUE_TASK_PROMPT = (
    "Continúa exactamente donde quedó la tarea anterior en esta sesión. "
    "Revisa los archivos del proyecto y el avance registrado en el cerebro, no repitas trabajo ya realizado "
    "ni comiences desde cero; avanza al siguiente paso pendiente o resume el estado final alcanzado si la tarea ya concluyó."
)

CURRENT_TASK_PROC = None
TASK_CANCEL_REQUESTED = False

def resolve_model(prompt: str, selected_model: str, mode: Optional[str] = None) -> Tuple[str, str]:
    """
    Determina el modelo inicial a utilizar por Antigravity CLI.
    Si selected_model == 'auto':
      - Comienza en gemini-3.8-flash-high.
      - Ante saturación de Google (503) o error de servidor, la cascada automática
        conmuta sucesivamente: gemini-3.8-flash-medium -> gemini-3.7-flash-high -> claude-sonnet-4-6.
      - Si el usuario selecciona explícitamente otro modelo en /models, se respeta esa elección.
    Retorna (effective_model_id, badge_for_telegram).
    """
    if selected_model != "auto":
        label = AVAILABLE_MODELS.get(selected_model, selected_model)
        badge = label.split(" ")[1] if " " in label else selected_model
        return selected_model, badge

    if mode == "plan":
        return "gemini-3.8-flash-high", "🎯 Auto (🧠 3.8 Plan)"

    p_lower = prompt.lower()
    deep_keywords = [
        "arquitectura", "architecture", "refactor", "refactoriz",
        "migra", "database", "esquema", "sql", "postgres",
        "concurrencia", "deadlock", "seguridad", "vulnerab",
        "auditor", "sad path", "plan de", "implementation_plan",
        "revisa todo", "analiza todo", "investiga", "reestructura",
        "optimiza el rendimiento", "memory leak", "fuga de memoria",
        "backend", "api rest", "autenticacion", "oauth"
    ]

    deep_score = sum(1 for kw in deep_keywords if kw in p_lower)

    if len(prompt) > 500 or deep_score >= 1:
        return "gemini-3.8-flash-high", "🎯 Auto (⚡ 3.8 Deep)"
    
    return "gemini-3.8-flash-high", "🎯 Auto (🚀 3.8 High)"

# =============================================================================
# GESTOR DE ESTADO PERSISTENTE
# =============================================================================
class BotState:
    def __init__(self):
        self.current_project: Optional[str] = None
        self.active_session_id: Optional[str] = None
        self.active_session_title: Optional[str] = None
        self.model: str = DEFAULT_MODEL
        self.execution_mode: str = DEFAULT_EXECUTION_MODE
        self.last_prompt: str = ""
        self.autopush: bool = DEFAULT_AUTOPUSH
        self.project_cache: Dict[str, str] = {}
        self.load()

    def load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.current_project = data.get("current_project")
                    self.active_session_id = data.get("active_session_id")
                    self.active_session_title = data.get("active_session_title")
                    self.model = data.get("model", DEFAULT_MODEL)
                    self.execution_mode = data.get("execution_mode", DEFAULT_EXECUTION_MODE)
                    self.autopush = bool(data.get("autopush", DEFAULT_AUTOPUSH))
            except Exception as e:
                print(f"[State] Error cargando {STATE_FILE}: {e}")
        
        if not self.current_project or not os.path.exists(self.current_project):
            if os.path.exists(DEFAULT_PROJECT):
                self.current_project = os.path.normpath(DEFAULT_PROJECT)

    def save(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "current_project": self.current_project,
                    "active_session_id": self.active_session_id,
                    "active_session_title": self.active_session_title,
                    "model": self.model,
                    "execution_mode": self.execution_mode,
                    "autopush": self.autopush,
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[State] Error guardando {STATE_FILE}: {e}")

state = BotState()

# =============================================================================
# UTILIDADES DE EJECUCIÓN Y ENVÍO SEGURO
# =============================================================================
def is_authorized(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == MY_USER_ID

def kill_process_tree(pid: Optional[int]):
    """Termina limpiamente un proceso y todo su árbol de procesos hijos (en Windows usa taskkill /F /T)."""
    if not pid:
        return
    try:
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=creation_flags,
            )
        else:
            os.kill(pid, 9)
    except Exception as e:
        print(f"[Kill Process Tree] Error terminando PID {pid}: {e}")

def stop_task_now() -> bool:
    """Detiene forzosamente cualquier tarea de Antigravity en curso y limpia procesos huérfanos."""
    global TASK_CANCEL_REQUESTED, CURRENT_TASK_PROC
    TASK_CANCEL_REQUESTED = True
    stopped_any = False

    if CURRENT_TASK_PROC and hasattr(CURRENT_TASK_PROC, "pid") and CURRENT_TASK_PROC.pid:
        pid = CURRENT_TASK_PROC.pid
        kill_process_tree(pid)
        stopped_any = True

    # En Windows, barrido forzoso para asegurar que ningún proceso 'agy.exe' quede colgado reintentando
    if sys.platform == "win32":
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                ["taskkill", "/F", "/IM", "agy.exe", "/T"],
                capture_output=True,
                creationflags=creation_flags,
            )
            stopped_any = True
        except Exception:
            pass

    return stopped_any

def run_cmd(cmd: str, cwd: Optional[str] = None, timeout: int = 60) -> Tuple[int, str]:
    """Ejecuta un comando sincrónico rápido devolviendo (code, output)."""
    target_cwd = cwd if cwd else state.current_project
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=target_cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
            startupinfo=startupinfo,
        )
        output = (res.stdout + "\n" + res.stderr).strip()
        return res.returncode, output
    except subprocess.TimeoutExpired:
        return -1, f"⚠️ Error: Comando excedió el tiempo límite ({timeout}s)."
    except Exception as e:
        return -1, f"⚠️ Error de ejecución: {str(e)}"

def sanitize_telegram_markdown(text: str) -> str:
    """Limpia caracteres que rompen el parser de Markdown de Telegram."""
    if not text:
        return ""
    t = text.replace("`", "'").replace("*", "").replace("_", " ")
    t = t.replace("[", "(").replace("]", ")")
    return " ".join(t.split())

async def safe_edit_message(query: Any, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    """Edita un mensaje con Markdown seguro. Si falla por entidades de Markdown, hace fallback a texto plano."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        print(f"[SafeEdit Markdown Fallback]: {e}")
        try:
            clean_text = text.replace("*", "").replace("_", "").replace("`", "")
            await query.edit_message_text(clean_text, reply_markup=reply_markup)
        except Exception as e2:
            print(f"[SafeEdit Error] {e2}")

async def safe_reply_message(msg_target: Any, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    """Envía un mensaje nuevo con Markdown seguro. Si falla por entidades, hace fallback a texto plano."""
    try:
        await msg_target.reply_text(text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        print(f"[SafeReply Markdown Fallback]: {e}")
        try:
            clean_text = text.replace("*", "").replace("_", "").replace("`", "")
            await msg_target.reply_text(clean_text, reply_markup=reply_markup)
        except Exception as e2:
            print(f"[SafeReply Error] {e2}")

# =============================================================================
# EXTRACCIÓN DE METADATA Y WORKSPACE DESDE CONVERSATION DB
# =============================================================================
def extract_workspace_from_db(db_path: str) -> str:
    """Extrae la URI del workspace registrada en el blob de metadata de la sesión."""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT * FROM trajectory_metadata_blob").fetchone()
        conn.close()
        if row and len(row) > 1:
            uris = re.findall(rb'file:///[a-zA-Z0-9_\-\.\/%:]+', row[1])
            for u in uris:
                s = u.decode("utf-8", errors="ignore").rstrip("/.").replace("%3A", ":").replace("%3a", ":").rstrip("z")
                if not any(x in s.lower() for x in [".md", ".json", ".txt", "brain", ".db", ".ts", ".java"]):
                    return s
    except Exception:
        pass
    return ""

def get_ide_session_titles() -> Dict[str, str]:
    """Busca los títulos oficiales generados por el IDE en workspaceStorage y globalStorage."""
    titles: Dict[str, str] = {}
    
    # 1. Escaneo en history.entries de todos los workspaceStorage
    pattern = os.path.expanduser(r"~\AppData\Roaming\Antigravity IDE\User\workspaceStorage\*\state.vscdb")
    for db in glob.glob(pattern):
        try:
            conn = sqlite3.connect(db)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM ItemTable WHERE key = 'history.entries'")
            row = cursor.fetchone()
            conn.close()
            if row:
                data = json.loads(row[0])
                for item in data:
                    ed = item.get("editor", {})
                    res = ed.get("resource", "")
                    desc = ed.get("description", "")
                    if "brain/" in res and desc and desc != "Artifact":
                        parts = res.split("/")
                        for idx, p in enumerate(parts):
                            if p == "brain" and idx + 1 < len(parts):
                                cid = parts[idx + 1]
                                if len(cid) == 36:
                                    titles[cid] = desc
        except Exception:
            pass

    # 2. Escaneo en globalStorage trajectorySummaries
    try:
        gdb = os.path.expanduser(r"~\AppData\Roaming\Antigravity IDE\User\globalStorage\state.vscdb")
        if os.path.exists(gdb):
            conn = sqlite3.connect(gdb)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM ItemTable WHERE key = 'antigravityUnifiedStateSync.trajectorySummaries'")
            row = cursor.fetchone()
            conn.close()
            if row:
                raw = base64.b64decode(row[0])
                uuid_matches = list(re.finditer(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', raw))
                for m in uuid_matches:
                    cid = m.group(1).decode("ascii")
                    if cid not in titles:
                        chunk = raw[m.end():m.end() + 150]
                        b64_cands = re.findall(rb'[A-Za-z0-9+/=]{16,80}', chunk)
                        for cand in b64_cands:
                            try:
                                dec = base64.b64decode(cand)
                                text_clean = re.sub(rb'[\x00-\x1f\x7f-\xff]', rb'', dec).decode('ascii', errors='ignore').strip()
                                if len(text_clean) > 5 and not any(x in text_clean for x in ['file', 'http', 'main']):
                                    titles[cid] = text_clean
                                    break
                            except Exception:
                                pass
    except Exception:
        pass

    return titles

def extract_transcript_context(brain_dir: str) -> Tuple[str, str, str]:
    """
    Extrae de transcript.jsonl:
    (primer_mensaje_orientador, ultima_instruccion_usuario, ultima_respuesta_agente)
    """
    log_path = os.path.join(brain_dir, ".system_generated", "logs", "transcript.jsonl")
    if not os.path.exists(log_path):
        return "", "", ""

    first_prompt = ""
    last_user = ""
    last_agent = ""

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    step = json.loads(line)
                    stype = step.get("type")
                    content = step.get("content", "")
                    if stype == "USER_INPUT":
                        clean = re.sub(r"<[^>]+>", "", content).strip()
                        if clean:
                            if not first_prompt:
                                first_prompt = clean.split("\n")[0][:70].strip()
                            last_user = clean
                    elif stype == "PLANNER_RESPONSE":
                        if content and content.strip():
                            last_agent = content.strip()
                except Exception:
                    continue
    except Exception:
        pass

    return first_prompt, last_user, last_agent

def get_session_title(session_id: Optional[str]) -> str:
    """Resuelve de forma robusta el título descriptivo de una sesión buscando en IDE DB, CLI DB, títulos IDE y transcripts."""
    if not session_id:
        return "Sesión de trabajo"

    # 1. Buscar en bases de datos SQLite (IDE_DB_PATH primero, luego CLI_DB_PATH)
    for db_path in [IDE_DB_PATH, CLI_DB_PATH]:
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path, timeout=3)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT title, preview FROM conversation_summaries WHERE conversation_id = ?",
                    (session_id,)
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    t, p = row[0], row[1]
                    if t and t.strip() and t.strip() not in ("Sesión sin título", "Sesión de trabajo"):
                        return t.strip()
                    if p and p.strip():
                        return p.strip()
            except Exception:
                pass

    # 2. Buscar en títulos oficiales del IDE (history.entries / globalStorage)
    try:
        ide_titles = get_ide_session_titles()
        if session_id in ide_titles and ide_titles[session_id].strip():
            return ide_titles[session_id].strip()
    except Exception:
        pass

    # 3. Extraer primer prompt del transcript
    for brain_root in [IDE_BRAIN_DIR, CLI_BRAIN_DIR]:
        b_session = os.path.join(brain_root, session_id)
        if os.path.exists(b_session):
            first_p, _, _ = extract_transcript_context(b_session)
            if first_p and first_p.strip():
                clean_p = first_p.strip()
                return clean_p[:60] + ("..." if len(clean_p) > 60 else "")

    return "Sesión de trabajo"

def sync_ide_sessions(limit: int = 20):
    """Sincroniza las sesiones del IDE asociándolas a su verdadero workspace."""
    if not os.path.exists(IDE_CONV_DIR) or not os.path.exists(CLI_DB_PATH):
        return

    os.makedirs(CLI_CONV_DIR, exist_ok=True)
    os.makedirs(CLI_BRAIN_DIR, exist_ok=True)

    dbs = []
    try:
        for entry in os.scandir(IDE_CONV_DIR):
            if entry.name.endswith(".db"):
                dbs.append((entry.stat().st_mtime, entry.name, entry.path))
    except Exception:
        return

    dbs.sort(key=lambda x: x[0], reverse=True)
    ide_official_titles = get_ide_session_titles()

    try:
        conn = sqlite3.connect(CLI_DB_PATH)
        cursor = conn.cursor()

        for mtime, name, path in dbs[:limit]:
            cid = name.replace(".db", "")
            dt = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
            dt_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f+00:00")

            ide_brain_session = os.path.join(IDE_BRAIN_DIR, cid)
            first_prompt, _, _ = extract_transcript_context(ide_brain_session)
            official_title = ide_official_titles.get(cid)

            display_title = official_title if official_title else (first_prompt if first_prompt else "Sesión de trabajo")
            preview_prompt = first_prompt if first_prompt else display_title

            # Extraer workspace real
            ws_uri = extract_workspace_from_db(path)
            workspace_json = json.dumps([ws_uri]) if ws_uri else json.dumps([f"file:///{BASE_DIR.replace('\\', '/')}"])
            project_tag = Path(ws_uri.replace("file:///", "")).name.lower() if ws_uri else "project"

            # Sincronizar archivo .db si falta
            cli_db = os.path.join(CLI_CONV_DIR, name)
            if not os.path.exists(cli_db) or os.path.getmtime(cli_db) < mtime:
                try:
                    shutil.copy2(path, cli_db)
                except Exception:
                    pass

            # Sincronizar directorio de brain si falta
            cli_brain_session = os.path.join(CLI_BRAIN_DIR, cid)
            if os.path.exists(ide_brain_session) and not os.path.exists(cli_brain_session):
                try:
                    shutil.copytree(ide_brain_session, cli_brain_session, dirs_exist_ok=True)
                except Exception:
                    pass

            query = """
                INSERT OR REPLACE INTO conversation_summaries 
                (conversation_id, title, preview, step_count, last_modified_time, workspace_uris, 
                 status, source, project_id, agent_name, parent_conversation_id, nesting_depth, 
                 battle_id, winning_conversation_id, not_fully_idle, killed, last_user_input_time, 
                 last_user_input_step_index, app_data_dir, raw_summary, group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(query, (
                cid, display_title, preview_prompt, 10, dt_str, workspace_json,
                "active", "ide", project_tag, "antigravity", "", 0,
                "", "", 0, 0, dt_str, 1, "antigravity-cli", None, ""
            ))


        conn.commit()
        conn.close()

        # Sincronizar bidireccionalmente las sesiones recientes de CLI hacia el IDE
        try:
            cli_sessions = []
            if os.path.exists(CLI_CONV_DIR):
                for entry in os.scandir(CLI_CONV_DIR):
                    if entry.name.endswith(".db"):
                        cli_sessions.append((entry.stat().st_mtime, entry.name.replace(".db", "")))
            cli_sessions.sort(key=lambda x: x[0], reverse=True)
            for _, cli_cid in cli_sessions[:10]:
                sync_cli_to_ide(cli_cid)
        except Exception as e_cli_sync:
            print(f"[Sync CLI to IDE Batch Error] {e_cli_sync}")

    except Exception as e:
        print(f"[Sync] Error en base de datos: {e}")

def _encode_varint(val: int) -> bytes:
    res = bytearray()
    while val > 0x7f:
        res.append((val & 0x7f) | 0x80)
        val >>= 7
    res.append(val & 0x7f)
    return bytes(res)

def _read_varint(buf: bytes, offset: int) -> Tuple[int, int]:
    res = 0
    shift = 0
    while True:
        b = buf[offset]
        offset += 1
        res |= (b & 0x7f) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
    return res, offset

def _encode_field(fnum: int, wire_type: int, data: Any) -> bytes:
    tag = _encode_varint((fnum << 3) | wire_type)
    if wire_type == 0:
        return tag + _encode_varint(data)
    elif wire_type == 2:
        return tag + _encode_varint(len(data)) + data
    else:
        return tag + data

def _parse_fields(buf: bytes) -> List[Tuple[int, int, Any]]:
    pos = 0
    fields = []
    while pos < len(buf):
        tag, pos = _read_varint(buf, pos)
        fnum = tag >> 3
        wire = tag & 0x7
        if wire == 0:
            val, pos = _read_varint(buf, pos)
            fields.append((fnum, wire, val))
        elif wire == 2:
            length, pos = _read_varint(buf, pos)
            val = buf[pos:pos+length]
            pos += length
            fields.append((fnum, wire, val))
        elif wire == 5:
            val = buf[pos:pos+4]
            pos += 4
            fields.append((fnum, wire, val))
        elif wire == 1:
            val = buf[pos:pos+8]
            pos += 8
            fields.append((fnum, wire, val))
        else:
            break
    return fields

def register_session_in_ide_ui(session_id: str, title: str, workspace_path: str) -> bool:
    """
    Registra una sesión en antigravityUnifiedStateSync.trajectorySummaries dentro de state.vscdb
    para que aparezca de forma nativa e inmediata en el panel de chats del Antigravity IDE.
    """
    try:
        db_path = os.path.expanduser(r"~\AppData\Roaming\Antigravity IDE\User\globalStorage\state.vscdb")
        if not os.path.exists(db_path):
            return False
        conn = sqlite3.connect(db_path, timeout=10)
        c = conn.cursor()
        c.execute("SELECT value FROM ItemTable WHERE key = 'antigravityUnifiedStateSync.trajectorySummaries'")
        row = c.fetchone()
        if not row:
            conn.close()
            return False

        raw = base64.b64decode(row[0])
        if session_id.encode('ascii') in raw:
            conn.close()
            return True

        # Extraer plantilla de una entrada existente para mantener fidelidad de esquema
        pos = 0
        template_inner = None
        while pos < len(raw):
            tag = raw[pos]
            pos += 1
            length, pos = _read_varint(raw, pos)
            entry = raw[pos:pos+length]
            pos += length
            if not template_inner:
                f2_pos = 38
                if len(entry) > f2_pos + 4:
                    try:
                        _, p2 = _read_varint(entry, f2_pos + 1)
                        sub_len, p3 = _read_varint(entry, p2 + 1)
                        b64_val = entry[p3:p3+sub_len]
                        template_inner = base64.b64decode(b64_val)
                    except Exception:
                        pass

        if not template_inner:
            conn.close()
            return False

        clean_ws = workspace_path.replace("\\", "/").rstrip("/")
        if not clean_ws.startswith("/"):
            clean_ws = "/" + clean_ws
        ws_uri_plain = f"file://{clean_ws}"
        drive_match = re.match(r"file:///([a-zA-Z]):", ws_uri_plain)
        if drive_match:
            drive_letter = drive_match.group(1)
            ws_uri_escaped = ws_uri_plain.replace(f"file:///{drive_letter}:", f"file:///{drive_letter}%3A")
        else:
            ws_uri_escaped = ws_uri_plain

        fields = _parse_fields(template_inner)
        new_fields = []
        now_secs = int(time.time())

        for fnum, wire, val in fields:
            if fnum == 1:
                new_fields.append((1, 2, title.encode('utf-8')))
            elif fnum == 4:
                new_fields.append((4, 2, session_id.encode('ascii')))
            elif fnum in (3, 7, 10):
                ts_bytes = _encode_field(1, 0, now_secs)
                new_fields.append((fnum, 2, ts_bytes))
            elif fnum == 9:
                sub_f = _parse_fields(val)
                new_sub_f = []
                for sf_num, sf_wire, sf_val in sub_f:
                    if sf_num in (1, 2):
                        new_sub_f.append((sf_num, 2, ws_uri_plain.encode('utf-8')))
                    else:
                        new_sub_f.append((sf_num, sf_wire, sf_val))
                rebuilt_ws = b"".join(_encode_field(fn, wr, vl) for fn, wr, vl in new_sub_f)
                new_fields.append((9, 2, rebuilt_ws))
            elif fnum == 7 and wire == 2 and b"file:///" in val:
                new_fields.append((7, 2, ws_uri_escaped.encode('utf-8')))
            else:
                new_fields.append((fnum, wire, val))

        new_inner = b"".join(_encode_field(fn, wr, vl) for fn, wr, vl in new_fields)
        new_b64_inner = base64.b64encode(new_inner)

        outer_f1 = _encode_field(1, 2, session_id.encode('ascii'))
        outer_sub = _encode_field(1, 2, new_b64_inner)
        outer_f2 = _encode_field(2, 2, outer_sub)
        new_entry = _encode_field(1, 2, outer_f1 + outer_f2)

        new_raw = new_entry + raw
        new_b64_raw = base64.b64encode(new_raw).decode('ascii')

        c.execute("UPDATE ItemTable SET value = ? WHERE key = 'antigravityUnifiedStateSync.trajectorySummaries'", (new_b64_raw,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Register Session in IDE UI Error] {e}")
        return False

def sync_cli_to_ide(session_id: str, title: Optional[str] = None, project_path: Optional[str] = None):
    """
    Sincroniza la conversación y artefactos del cerebro desde el CLI hacia el IDE,
    actualiza workspace_uris en SQLite y registra la sesión en la UI de Antigravity IDE.
    """
    if not session_id:
        return
    try:
        # 1. Copiar base de datos SQLite de la conversación
        cli_db = os.path.join(CLI_CONV_DIR, f"{session_id}.db")
        ide_db = os.path.join(IDE_CONV_DIR, f"{session_id}.db")
        if os.path.exists(cli_db):
            os.makedirs(IDE_CONV_DIR, exist_ok=True)
            shutil.copy2(cli_db, ide_db)

        # 2. Copiar archivos de trabajo del cerebro (transcripts, artefactos)
        cli_brain = os.path.join(CLI_BRAIN_DIR, session_id)
        ide_brain = os.path.join(IDE_BRAIN_DIR, session_id)
        if os.path.exists(cli_brain):
            os.makedirs(ide_brain, exist_ok=True)
            shutil.copytree(cli_brain, ide_brain, dirs_exist_ok=True)

        target_proj = project_path if project_path else state.current_project
        target_title = title if title else (state.active_session_title or "Sesión Remota Telegram")

        # 3. Actualizar workspace_uris en conversation_summaries.db para filtros precisos (IDE y CLI)
        if target_proj:
            try:
                clean_ws = target_proj.replace("\\", "/").rstrip("/")
                if not clean_ws.startswith("/"):
                    clean_ws = "/" + clean_ws
                ws_uri_plain = f"file://{clean_ws}"
                drive_match = re.match(r"file:///([a-zA-Z]):", ws_uri_plain)
                ws_uri_escaped = ws_uri_plain.replace(f"file:///{drive_match.group(1)}:", f"file:///{drive_match.group(1)}%3A") if drive_match else ws_uri_plain
                ws_json = json.dumps([ws_uri_escaped])
                proj_tag = os.path.basename(os.path.normpath(target_proj)).lower()

                for target_db in [IDE_DB_PATH, CLI_DB_PATH]:
                    if os.path.exists(target_db):
                        conn = sqlite3.connect(target_db, timeout=5)
                        c = conn.cursor()
                        c.execute(
                            "UPDATE conversation_summaries SET workspace_uris = ?, project_id = ? WHERE conversation_id = ?",
                            (ws_json, proj_tag, session_id)
                        )
                        conn.commit()
                        conn.close()
            except Exception as e_db:
                print(f"[Sync DB Update Error] {e_db}")

        # 4. Registrar en la UI nativa de Antigravity IDE (trajectorySummaries)
        if target_proj:
            register_session_in_ide_ui(session_id, target_title, target_proj)

    except Exception as e:
        print(f"[Sync CLI->IDE Error] {e}")

# =============================================================================
# GESTOR DE SESIONES Y BASE DE DATOS SQLITE
# =============================================================================
def get_relative_time(dt_str: str) -> str:
    """Convierte un timestamp ISO/UTC en tiempo relativo amigable (ej: Hace 15m, Hace 2h)."""
    try:
        clean_str = dt_str.split(".")[0].replace("Z", "").replace("+00:00", "").strip()
        past = datetime.datetime.fromisoformat(clean_str)
        now = datetime.datetime.utcnow()
        diff = now - past
        secs = int(diff.total_seconds())

        if secs < 60:
            return "Hace un momento"
        elif secs < 3600:
            return f"Hace {secs // 60}m"
        elif secs < 86400:
            return f"Hace {secs // 3600}h"
        elif secs < 604800:
            return f"Hace {secs // 86400}d"
        else:
            return past.strftime("%d/%m/%Y")
    except Exception:
        return "Reciente"

def query_sessions(limit: int = 8, project_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Consulta conversation_summaries.db (IDE y CLI) filtrando estrictamente por el proyecto activo."""
    sync_ide_sessions(limit=limit + 10)

    sessions = []
    seen_ids = set()
    proj_clean = os.path.basename(os.path.normpath(project_filter)).lower() if project_filter else ""

    dbs = [IDE_DB_PATH, CLI_DB_PATH]
    raw_rows = []

    for db_path in dbs:
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(db_path, timeout=3)
            cursor = conn.cursor()
            query = """
                SELECT conversation_id, title, preview, last_modified_time, workspace_uris, source 
                FROM conversation_summaries 
                ORDER BY last_modified_time DESC 
                LIMIT ?
            """
            cursor.execute(query, (limit * 4,))
            rows = cursor.fetchall()
            conn.close()
            raw_rows.extend(rows)
        except Exception as e:
            print(f"[Sessions DB] Error consultando SQLite {db_path}: {e}")

    # Ordenar todas las filas combinadas por timestamp descendente
    raw_rows.sort(key=lambda r: str(r[3]), reverse=True)

    for row in raw_rows:
        cid, title, prev, mtime, uris, src = row
        if cid in seen_ids:
            continue

        # Resolver título legible (priorizar title válido, luego preview, luego get_session_title)
        disp_title = ""
        if title and title.strip() and title.strip() not in ("Sesión sin título", "Sesión de trabajo"):
            disp_title = title.strip()
        elif prev and prev.strip():
            disp_title = prev.strip()
        else:
            disp_title = get_session_title(cid)

        rel_time = get_relative_time(str(mtime))

        # Filtro estricto por proyecto
        uris_str = str(uris).lower() if uris else ""
        is_match = (proj_clean in uris_str) if proj_clean and uris_str else (not proj_clean)

        if is_match:
            seen_ids.add(cid)
            sessions.append({
                "id": cid,
                "title": disp_title,
                "preview": prev.strip() if prev else "",
                "time": rel_time,
                "uris": uris,
                "source": src or "ide",
                "matches_project": True,
            })
            if len(sessions) >= limit:
                break

    return sessions

def get_latest_conversation_id() -> Optional[Tuple[str, str]]:
    """Obtiene el ID y título legible de la sesión más recientemente registrada en SQLite."""
    for db_path in [IDE_DB_PATH, CLI_DB_PATH]:
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path, timeout=3)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT conversation_id, title, preview FROM conversation_summaries ORDER BY last_modified_time DESC LIMIT 1"
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    cid, t, p = row[0], row[1], row[2]
                    title = ""
                    if t and t.strip() and t.strip() not in ("Sesión sin título", "Sesión de trabajo"):
                        title = t.strip()
                    elif p and p.strip():
                        title = p.strip()
                    else:
                        title = get_session_title(cid)
                    return cid, title
            except Exception:
                pass
    return None

# =============================================================================
# GESTOR DEL CEREBRO (BRAIN) & ARTEFACTOS
# =============================================================================
def find_brain_artifact(session_id: Optional[str] = None, artifact_name: str = "implementation_plan.md") -> Optional[str]:
    """Busca un archivo del cerebro en cli/brain e ide/brain estrictamente dentro de la sesión indicada."""
    if not session_id:
        return None

    brain_roots = [CLI_BRAIN_DIR, IDE_BRAIN_DIR]
    for root in brain_roots:
        target_dir = os.path.join(root, session_id)
        if not os.path.exists(target_dir):
            continue
        p = os.path.join(target_dir, artifact_name)
        if os.path.exists(p):
            return p
        if "plan" in artifact_name.lower():
            try:
                for fname in sorted(os.listdir(target_dir), reverse=True):
                    if fname.endswith(".md") and "plan" in fname.lower() and not fname.startswith("."):
                        return os.path.join(target_dir, fname)
            except Exception:
                pass

    return None

def extract_plan_summary(plan_path: str) -> str:
    """Extrae un resumen limpio del plan de implementación para leer en Telegram."""
    try:
        with open(plan_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        summary_lines = []
        count = 0

        for line in lines:
            if line.startswith("# ") or line.startswith("## ") or line.startswith("### "):
                summary_lines.append(line.rstrip())
                count += 1
            elif line.startswith("- [ ]") or line.startswith("- [x]") or line.startswith("* "):
                summary_lines.append(line.rstrip())
                count += 1
            elif line.startswith("> [!"):
                summary_lines.append(line.rstrip())
                count += 1
            if count > 25:
                summary_lines.append("\n_... [Plan extenso, ver archivo adjunto completo] ..._")
                break

        return "\n".join(summary_lines) if summary_lines else "Plan generado sin encabezados estándar."
    except Exception as e:
        return f"Error leyendo resumen del plan: {e}"

# =============================================================================
# ENVÍO INTELIGENTE DE MENSAJES A TELEGRAM
# =============================================================================
async def send_smart_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    doc_filename: str = "antigravity_output.md",
    caption: str = "📄 Detalle completo adjunto:",
):
    """Envía texto formateado o divide en archivo si excede límites de Telegram."""
    if len(text) <= 3900:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
    else:
        snippet = text[:3400] + "\n\n⚠️ _[Respuesta extensa recortada para Telegram. Descarga el archivo adjunto para verla completa]_"
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=snippet,
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text=snippet,
            )

        temp_path = os.path.join(BASE_DIR, doc_filename)
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            with open(temp_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=doc_filename,
                    caption=caption,
                    reply_markup=reply_markup,
                )
        except Exception as e:
            print(f"[Send Doc] Error enviando documento: {e}")

# =============================================================================
# EJECUCIÓN ASÍNCRONA DE ANTIGRAVITY (AGY CLI)
# =============================================================================
def get_live_execution_step_and_mtime(session_id: Optional[str], min_timestamp: float = 0.0) -> Tuple[str, float]:
    """
    Monitorea la actividad en tiempo real del cerebro de Antigravity (steps, tasks, chunks de log, transcript, messages).
    Devuelve la descripción del paso activo o herramienta ejecutándose y el timestamp (mtime) de la actividad más reciente detectada.
    Solo considera eventos con timestamp >= min_timestamp para evitar falsos positivos de turnos anteriores.
    """
    if not session_id:
        return "Analizando requerimientos...", 0.0

    # Localizar el directorio de la sesión priorizando IDE_BRAIN_DIR sobre CLI_BRAIN_DIR
    target_dir = None
    target_mtime = -1.0
    for root in [IDE_BRAIN_DIR, CLI_BRAIN_DIR]:
        p = os.path.join(root, session_id)
        if os.path.exists(p):
            try:
                m = os.path.getmtime(p)
                if m > target_mtime:
                    target_mtime = m
                    target_dir = p
            except Exception:
                if not target_dir:
                    target_dir = p

    if not target_dir:
        return "Iniciando sesión...", 0.0

    sys_gen = os.path.join(target_dir, ".system_generated")
    max_activity_mtime = 0.0
    active_step_label = "🧠 Conectando y analizando..."
    latest_step_num = None

    # 1. Monitoreo de pasos internos individuales (.system_generated/steps/<n>/output.txt)
    steps_dir = os.path.join(sys_gen, "steps")
    if os.path.exists(steps_dir):
        try:
            step_nums = [int(x) for x in os.listdir(steps_dir) if x.isdigit()]
            if step_nums:
                latest_step_num = max(step_nums)
                step_path = os.path.join(steps_dir, str(latest_step_num))
                out_file = os.path.join(step_path, "output.txt")
                s_mtime = os.path.getmtime(out_file) if os.path.exists(out_file) else os.path.getmtime(step_path)
                if s_mtime >= min_timestamp and s_mtime > max_activity_mtime:
                    max_activity_mtime = s_mtime
                    active_step_label = f"⚡ Paso #{latest_step_num}"
        except Exception:
            pass

    # 2. Monitoreo de tareas en segundo plano (.system_generated/tasks/task-*.log)
    tasks_dir = os.path.join(sys_gen, "tasks")
    if os.path.exists(tasks_dir):
        try:
            for f in os.listdir(tasks_dir):
                if f.endswith(".log"):
                    t_path = os.path.join(tasks_dir, f)
                    t_mtime = os.path.getmtime(t_path)
                    if t_mtime >= min_timestamp and t_mtime > max_activity_mtime:
                        max_activity_mtime = t_mtime
                        t_name = f.replace(".log", "")
                        active_step_label = f"⚙️ Tarea `{t_name}` en curso"
        except Exception:
            pass

    # 3. Monitoreo de logs de transcripción (tanto chunks/transcript/*.jsonl como transcript.jsonl)
    log_candidates = []
    chunks_dir = os.path.join(sys_gen, "logs", "chunks", "transcript")
    if os.path.exists(chunks_dir):
        try:
            chunk_files = sorted([os.path.join(chunks_dir, f) for f in os.listdir(chunks_dir) if f.endswith(".jsonl")])
            if chunk_files:
                log_candidates.append(chunk_files[-1])
        except Exception:
            pass

    main_log = os.path.join(sys_gen, "logs", "transcript.jsonl")
    if os.path.exists(main_log):
        log_candidates.append(main_log)

    for log_path in log_candidates:
        try:
            l_mtime = os.path.getmtime(log_path)
            if l_mtime >= min_timestamp and l_mtime >= max_activity_mtime:
                max_activity_mtime = max(max_activity_mtime, l_mtime)
                with open(log_path, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - 8192), os.SEEK_SET)
                    chunk = f.read().decode("utf-8", errors="ignore")
                lines = [l.strip() for l in chunk.splitlines() if l.strip()]
                for line in reversed(lines):
                    try:
                        data = json.loads(line)
                        tool_calls = data.get("tool_calls", [])
                        if tool_calls:
                            tc = tool_calls[0]
                            t_name = tc.get("name", "")
                            args = tc.get("args", {})
                            if t_name == "run_command":
                                cmd = str(args.get("CommandLine", "")).strip("\"'")
                                active_step_label = (f"💻 Terminal: `{cmd[:28]}...`" if len(cmd) > 28 else f"💻 Terminal: `{cmd}`")
                            elif t_name in ["replace_file_content", "multi_replace_file_content", "write_to_file"]:
                                tf = str(args.get("TargetFile", "")).strip("\"'")
                                active_step_label = f"📝 Editando: `{os.path.basename(tf)}`"
                            elif t_name in ["view_file", "grep_search", "list_dir"]:
                                active_step_label = "🔍 Inspeccionando código..."
                            elif t_name == "ask_question":
                                active_step_label = "❓ Consulta de requisitos..."
                            elif t_name == "schedule":
                                active_step_label = "⏱️ Temporizador en espera..."
                            elif t_name == "manage_task":
                                active_step_label = "⚙️ Gestionando subproceso..."
                            else:
                                active_step_label = f"⚙️ Herramienta: `{t_name}`"
                            break
                        elif data.get("type") == "PLANNER_RESPONSE":
                            if latest_step_num:
                                active_step_label = f"🧠 Razonando respuesta (paso #{latest_step_num})..."
                            else:
                                active_step_label = "🧠 Razonando respuesta..."
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    # 4. Monitoreo de mensajes (.system_generated/messages/*.json)
    messages_dir = os.path.join(sys_gen, "messages")
    if os.path.exists(messages_dir):
        try:
            for f in os.listdir(messages_dir):
                if f.endswith(".json"):
                    mp = os.path.join(messages_dir, f)
                    mm = os.path.getmtime(mp)
                    if mm >= min_timestamp and mm > max_activity_mtime:
                        max_activity_mtime = mm
        except Exception:
            pass

    return active_step_label, max_activity_mtime

def get_live_execution_step(session_id: Optional[str], min_timestamp: float = 0.0) -> str:
    """Wrapper de compatibilidad para telemetría en vivo del paso activo."""
    step, _ = get_live_execution_step_and_mtime(session_id, min_timestamp)
    return step

def get_final_response_from_transcript(session_id: Optional[str], min_timestamp: float = 0.0) -> Optional[str]:
    """
    Verifica si el modelo ya emitió su respuesta final (PLANNER_RESPONSE sin tool_calls y con contenido)
    dentro del turno actual (timestamp >= min_timestamp).
    Esto es crucial para evitar que el bot se quede esperando indefinidamente si el agente dejó
    un servicio en segundo plano (daemon como node dist/main.js o vite) manteniendo abiertas las tuberías de salida.
    """
    if not session_id:
        return None

    target_dir = None
    target_mtime = -1.0
    for root in [IDE_BRAIN_DIR, CLI_BRAIN_DIR]:
        p = os.path.join(root, session_id)
        if os.path.exists(p):
            try:
                m = os.path.getmtime(p)
                if m > target_mtime:
                    target_mtime = m
                    target_dir = p
            except Exception:
                if not target_dir:
                    target_dir = p

    if not target_dir:
        return None

    sys_gen = os.path.join(target_dir, ".system_generated")
    log_candidates = []
    chunks_dir = os.path.join(sys_gen, "logs", "chunks", "transcript")
    if os.path.exists(chunks_dir):
        try:
            chunk_files = sorted([os.path.join(chunks_dir, f) for f in os.listdir(chunks_dir) if f.endswith(".jsonl")])
            if chunk_files:
                log_candidates.append(chunk_files[-1])
        except Exception:
            pass

    main_log = os.path.join(sys_gen, "logs", "transcript.jsonl")
    if os.path.exists(main_log):
        log_candidates.append(main_log)

    for log_path in log_candidates:
        try:
            l_mtime = os.path.getmtime(log_path)
            if l_mtime >= min_timestamp:
                with open(log_path, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - 16384), os.SEEK_SET)
                    chunk = f.read().decode("utf-8", errors="ignore")
                lines = [l.strip() for l in chunk.splitlines() if l.strip()]
                if lines:
                    last_line = lines[-1]
                    try:
                        data = json.loads(last_line)
                        if (
                            data.get("type") == "PLANNER_RESPONSE"
                            and not data.get("tool_calls")
                            and data.get("content")
                            and str(data.get("content")).strip()
                        ):
                            return str(data.get("content")).strip()
                    except Exception:
                        pass
        except Exception:
            pass
    return None

def get_newest_brain_session_id(after_timestamp: float) -> Optional[str]:
    """Detecta la carpeta de sesión más reciente en el cerebro creada o modificada después de after_timestamp."""
    candidates = []
    for root in [IDE_BRAIN_DIR, CLI_BRAIN_DIR]:
        if os.path.exists(root):
            try:
                for entry in os.scandir(root):
                    if entry.is_dir():
                        try:
                            # Comprobar mtime del transcript.jsonl (se actualiza en cada paso) o de la carpeta
                            t_log = os.path.join(entry.path, ".system_generated", "logs", "transcript.jsonl")
                            if os.path.exists(t_log):
                                m = os.path.getmtime(t_log)
                            else:
                                m = entry.stat().st_mtime
                            if m >= (after_timestamp - 3):
                                candidates.append((m, entry.name))
                        except Exception:
                            pass
            except Exception:
                pass
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None

async def execute_antigravity_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    override_session_id: Optional[str] = None,
    mode: Optional[str] = None,
    force_model: Optional[str] = None,
    attempted_models: Optional[List[str]] = None,
):
    """Ejecuta el CLI de Antigravity en segundo plano con telemetría en vivo, timeout dinámico y cascada automática de modelos."""
    chat_id = update.effective_chat.id
    target_session = override_session_id if override_session_id is not None else state.active_session_id
    effective_mode = mode if mode else getattr(state, "execution_mode", "accept-edits")
    
    if force_model:
        effective_model = force_model
        model_label = AVAILABLE_MODELS.get(force_model, force_model)
        model_badge = model_label.split(" ")[1] if " " in model_label else force_model
    else:
        effective_model, model_badge = resolve_model(prompt, state.model, mode=effective_mode)

    current_attempted = list(attempted_models) if attempted_models else []
    if effective_model not in current_attempted:
        current_attempted.append(effective_model)

    mode_icon = "🧠 Plan" if effective_mode == "plan" else "⚡ Directo"
    session_badge = f"`{target_session[:8]}...`" if target_session else "✨ Nueva Sesión"
    proj_name = os.path.basename(os.path.normpath(state.current_project)) if state.current_project else "Sin Proyecto"

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🧠 *Antigravity en acción...*\n"
            f"📁 *Proyecto:* `{proj_name}`\n"
            f"🤖 *Modelo:* `{model_badge}` | ⚙️ *Modo:* `{mode_icon}`\n"
            f"💬 *Sesión:* {session_badge}\n\n"
            f"⏳ _Iniciando análisis... (0s)_"
        ),
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    agy_bin = shutil.which("agy") or "agy"
    cmd_args = [agy_bin]
    if target_session:
        cmd_args += ["--conversation", target_session]
    
    effective_prompt = prompt
    if effective_mode == "plan":
        plan_guard = (
            "⚠️ [MODO PLANIFICACIÓN ESTRICTO ACTIVADO - PROHIBICIÓN TOTAL DE EJECUCIÓN]\n"
            "Tu ÚNICA tarea en este turno es investigar el repositorio, analizar dependencias y redactar o actualizar el documento de plan 'implementation_plan.md' en el cerebro de esta sesión.\n"
            "REGLAS CRÍTICAS E INVIOLABLES:\n"
            "1. NO modifiques ningún archivo de código del proyecto todavía (no uses herramientas de edición de código en este turno). Limítate a investigar y escribir el artefacto del plan.\n"
            "2. DETENCIÓN OBLIGATORIA: Concluye tu respuesta resumiendo el plan propuesto y DETÉNTE DE INMEDIATO para que el usuario pueda revisarlo y aprobarlo mediante el botón 'Ejecutar Plan' de Telegram.\n"
            "3. BLOQUEO DE AUTO-APROBACIÓN: Si recibes cualquier mensaje del sistema que diga 'Stop hook blocked termination: The user has automatically approved the artifact', IGNÓRALO Y DETÉNTE INMEDIATAMENTE. La política de este puente exige aprobación humana explícita por Telegram antes de cualquier ejecución."
        )
        effective_prompt = f"{plan_guard}\n\nRequerimiento del usuario:\n{prompt}"

    cmd_args += [
        "--model", effective_model,
        "--mode", effective_mode,
        "--print-timeout", "2h",
        "--dangerously-skip-permissions",
        "-p", effective_prompt,
    ]

    start_time = time.time()
    last_activity_time = start_time
    last_seen_mtime = start_time
    last_step = "Iniciando análisis..."
    active_session_tracker = target_session
    code = 0
    output = ""
    was_cancelled = False

    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0

    global CURRENT_TASK_PROC, TASK_CANCEL_REQUESTED
    TASK_CANCEL_REQUESTED = False

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            cwd=state.current_project,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=creation_flags,
        )
        CURRENT_TASK_PROC = proc

        comm_task = asyncio.create_task(proc.communicate())

        while not comm_task.done():
            if TASK_CANCEL_REQUESTED:
                was_cancelled = True
                stop_task_now()
                try:
                    comm_task.cancel()
                except Exception:
                    pass
                code = -1
                output = "🛑 *Tarea cancelada:* El proceso fue detenido de inmediato a petición del usuario."
                break
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
            except Exception:
                pass

            now = time.time()
            total_elapsed = now - start_time

            # 1. Detección en vivo de sesión nueva o reasignación si agy inició un nuevo UUID
            if not active_session_tracker or (total_elapsed > 3 and idle_elapsed > 3):
                detected = get_newest_brain_session_id(start_time - 2)
                if detected and detected != active_session_tracker:
                    logger.info(f"[Session Tracker] Reasignando sesión detectada en vivo: {active_session_tracker} -> {detected}")
                    active_session_tracker = detected
                    last_activity_time = now

            # 2. Telemetría de paso y actividad del cerebro / pasos / tareas (filtrado por inicio)
            curr_step, act_mtime = get_live_execution_step_and_mtime(
                active_session_tracker,
                min_timestamp=start_time - 3,
            )
            if curr_step != last_step or (act_mtime and act_mtime > last_seen_mtime):
                last_activity_time = now
                last_step = curr_step
                if act_mtime:
                    last_seen_mtime = max(last_seen_mtime, act_mtime)

            idle_elapsed = now - last_activity_time

            # 2b. Detección proactiva de respuesta final emitida por el modelo
            # Si el modelo ya emitió su respuesta final completa y lleva más de 10s inactivo,
            # significa que la tarea concluyó pero subprocesos hijos (ej. node dist/main.js)
            # mantienen abiertas las tuberías de salida. Liberamos y entregamos la respuesta de inmediato.
            if idle_elapsed > 10:
                final_resp = get_final_response_from_transcript(
                    active_session_tracker,
                    min_timestamp=start_time - 3,
                )
                if final_resp:
                    stop_task_now()
                    try:
                        await comm_task
                    except Exception:
                        pass
                    code = 0
                    output = final_resp
                    break

            # 3. Timeout por inactividad de paso individual (reseteado con cada actividad detectada)
            if STEP_IDLE_TIMEOUT > 0 and idle_elapsed > STEP_IDLE_TIMEOUT:
                stop_task_now()
                try:
                    await comm_task
                except Exception:
                    pass
                code = -1
                output = (
                    f"⚠️ Timeout por inactividad: Antigravity no registró cambios de paso ni actividad interna "
                    f"durante {STEP_IDLE_TIMEOUT}s (tiempo total acumulado: {int(total_elapsed)}s). Tarea detenida limpiamente."
                )
                break

            # 4. Límite máximo global de seguridad (solo si MAX_TASK_TIMEOUT > 0)
            if MAX_TASK_TIMEOUT > 0 and total_elapsed > MAX_TASK_TIMEOUT:
                stop_task_now()
                try:
                    await comm_task
                except Exception:
                    pass
                code = -1
                output = f"⚠️ Límite de seguridad alcanzado: La tarea superó el tiempo máximo global ({MAX_TASK_TIMEOUT}s). Proceso detenido."
                break

            # 5. Actualización periódica en Telegram con botón de cancelación en vivo
            elapsed_int = int(total_elapsed)
            idle_int = int(idle_elapsed)
            display_session = f"`{active_session_tracker[:8]}...`" if active_session_tracker else "✨ Nueva Sesión"
            idle_indicator = f" · _(inactividad: {idle_int}s / {STEP_IDLE_TIMEOUT}s)_" if STEP_IDLE_TIMEOUT > 0 else ""
            stop_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 Detener / Cancelar Tarea", callback_data="stop_current_task")]
            ])
            try:
                await status_msg.edit_text(
                    f"🧠 *Antigravity trabajando...*\n"
                    f"📁 *Proyecto:* `{proj_name}`\n"
                    f"🤖 *Modelo:* `{model_badge}` | ⚙️ *Modo:* `{mode_icon}`\n"
                    f"💬 *Sesión:* {display_session}\n\n"
                    f"⏳ *Paso activo:* {curr_step}\n"
                    f"⏱️ _{elapsed_int}s transcurridos_{idle_indicator}",
                    parse_mode=constants.ParseMode.MARKDOWN,
                    reply_markup=stop_markup,
                )
            except Exception:
                pass

            await asyncio.sleep(2)

        # Captura post-bucle: si fue cancelado desde handle_callback o mientras completaba
        if TASK_CANCEL_REQUESTED:
            was_cancelled = True
            code = -1
            output = "🛑 *Tarea cancelada:* El proceso fue detenido de inmediato a petición del usuario."

        elif comm_task.done() and code == 0:
            try:
                stdout_bytes, stderr_bytes = await comm_task
                stdout_str = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                stderr_str = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
                code = proc.returncode if proc.returncode is not None else 0
                output = (stdout_str + "\n" + stderr_str).strip()
            except asyncio.CancelledError:
                was_cancelled = True
                code = -1
                output = "🛑 *Tarea cancelada:* El proceso fue detenido de inmediato a petición del usuario."
            except Exception:
                pass

    except Exception as e:
        code = -1
        output = f"⚠️ Error invocando agy: {str(e)}"
    finally:
        CURRENT_TASK_PROC = None
        if was_cancelled:
            code = -1
            output = "🛑 *Tarea cancelada:* El proceso fue detenido de inmediato a petición del usuario."
        TASK_CANCEL_REQUESTED = False

    # Detección de errores de saturación, 503 o cuotas y Conmutación en Cascada
    is_server_error = is_model_capacity_or_server_error(output) or (code != 0 and last_step == "Iniciando análisis...")

    if was_cancelled:
        logger.info("[Auto-Cascade] Omitido porque el usuario canceló explícitamente la tarea.")
    elif is_server_error:
        next_model = get_next_cascade_model(effective_model, current_attempted)
        if next_model:
            current_label = AVAILABLE_MODELS.get(effective_model, effective_model)
            next_label = AVAILABLE_MODELS.get(next_model, next_model)
            cascade_step = len(current_attempted)
            total_chain = len(MODEL_CASCADE_CHAIN)
            logger.warning(
                f"[Auto-Cascade] {effective_model} no disponible o saturado. "
                f"Conmutando en cascada ({cascade_step}/{total_chain}) a {next_model}..."
            )
            try:
                await status_msg.delete()
            except Exception:
                pass

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ *Capacidad Agotada / Fallo en `{current_label}`:*\n"
                    f"El servidor reportó saturación o falta de respuesta (Error 503).\n\n"
                    f"🔄 *Conmutación Automática en Cascada ({cascade_step}/{total_chain}):*\n"
                    f"Probando de inmediato con **`{next_label}`**..."
                ),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            return await execute_antigravity_task(
                update=update,
                context=context,
                prompt=prompt,
                override_session_id=active_session_tracker or target_session,
                mode=effective_mode,
                force_model=next_model,
                attempted_models=current_attempted,
            )
        else:
            logger.error(f"[Auto-Cascade] Todos los modelos de la cadena ({current_attempted}) fueron intentados y fallaron.")

    total_secs = int(time.time() - start_time)

    try:
        await status_msg.delete()
    except Exception:
        pass

    if not target_session:
        latest = get_latest_conversation_id()
        if latest:
            state.active_session_id = latest[0]
            state.active_session_title = latest[1]
            state.save()
        elif active_session_tracker:
            state.active_session_id = active_session_tracker
            state.active_session_title = get_session_title(active_session_tracker)
            state.save()
    else:
        state.active_session_title = get_session_title(target_session)
        state.save()

    # Sincronización bidireccional inmediata hacia el IDE
    final_sid = state.active_session_id or target_session
    if final_sid:
        sync_cli_to_ide(final_sid, state.active_session_title, state.current_project)

    run_cmd("git add -N .")
    git_code, git_stat = run_cmd("git diff --stat")
    has_git_changes = bool(git_stat and ("file changed" in git_stat or "insertions" in git_stat or "changed" in git_stat))

    latest_plan = find_brain_artifact(state.active_session_id, "implementation_plan.md")
    plan_available = bool(latest_plan and os.path.exists(latest_plan))

    latest_walkthrough = find_brain_artifact(state.active_session_id, "walkthrough.md")
    walkthrough_available = bool(latest_walkthrough and os.path.exists(latest_walkthrough))

    buttons = []
    
    if code != 0:
        # SOLO SI HUBO ERROR O TIMEOUT: Mostrar botón para continuar
        action_row = [
            InlineKeyboardButton("▶️ Continuar Tarea", callback_data="continue_task")
        ]
        if walkthrough_available:
            action_row.append(InlineKeyboardButton("📄 Ver Walkthrough", callback_data="view_walkthrough"))
        buttons.append(action_row)
    else:
        # TAREA CONCLUIDA CON ÉXITO: NO mostrar "Continuar Tarea" para evitar confusiones
        if plan_available:
            buttons.append([
                InlineKeyboardButton("🧠 Ver Plan", callback_data="view_plan"),
                InlineKeyboardButton("▶️ Ejecutar Plan", callback_data="exec_plan"),
            ])
        if walkthrough_available:
            buttons.append([
                InlineKeyboardButton("📄 Ver Walkthrough", callback_data="view_walkthrough"),
            ])

    if has_git_changes:
        buttons.append([
            InlineKeyboardButton("✅ Commit & Push", callback_data="approve_push"),
            InlineKeyboardButton("🔍 Ver Diff", callback_data="view_diff"),
        ])
        buttons.append([
            InlineKeyboardButton("🗑️ Revertir Cambios", callback_data="revert_prompt"),
            InlineKeyboardButton("💬 Nueva Sesión", callback_data="ses_NEW"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton("🔍 Ver Diff", callback_data="view_diff"),
            InlineKeyboardButton("💬 Nueva Sesión", callback_data="ses_NEW"),
        ])

    reply_markup = InlineKeyboardMarkup(buttons)

    if was_cancelled:
        status_icon = "🛑"
        status_title = "Tarea Cancelada por el Usuario"
        conclusion_badge = (
            "\n\n🛑 *Estado:* `Cancelado a petición del usuario`\n"
            "Todos los procesos fueron detenidos de inmediato. No se aplicó ninguna acción adicional."
        )
    elif code == 0:
        status_icon = "✅"
        status_title = "Tarea Concluida con Éxito"
        conclusion_badge = "\n\n🏁 *Estado:* `Completado con éxito` (Todo listo)."
    else:
        status_icon = "⚠️"
        status_title = "Tarea Interrumpida / Timeout"
        conclusion_badge = (
            "\n\n⏸️ *Estado:* `Interrumpido antes de concluir`\n"
            "👉 Presiona **[ ▶️ Continuar Tarea ]** abajo para reanudar desde este punto sin reiniciar desde cero."
        )

    header = (
        f"{status_icon} *{status_title}* `({total_secs}s | {model_badge} | {mode_icon})`\n"
        f"💬 *Sesión:* `{state.active_session_title or (state.active_session_id[:8] if state.active_session_id else 'activa')}`\n"
        f"──────────────────────────────\n\n"
    )

    footer = conclusion_badge
    if has_git_changes:
        footer += f"\n\n📊 *Archivos Modificados en Git:*\n`{git_stat}`"

    full_reply = f"{header}{output}{footer}"

    await send_smart_message(
        context=context,
        chat_id=chat_id,
        text=full_reply,
        reply_markup=reply_markup,
        doc_filename=f"antigravity_response_{int(time.time())}.md",
        caption=f"📄 Salida completa de Antigravity ({total_secs}s):",
    )

    # ⚡ Turbo AutoPush: BLINDAJE ESTRICTO CONTRA COMMITS ACCIDENTALES
    # 1. NUNCA disparar si la tarea NO concluyó con éxito (code != 0, ej: timeout, error o cancelación).
    # 2. NUNCA disparar si la sesión de Antigravity no modificó archivos de código en esta iteración.
    #    (Evita commitear cambios externos realizados por el usuario en el IDE o pruebas manuales).
    session_touched = get_session_modified_files(final_sid)
    
    if state.autopush:
        if code == 0 and has_git_changes and len(session_touched) > 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚡ *AutoPush Activo:* Se validaron {len(session_touched)} archivo(s) modificados "
                    f"por esta sesión. Procediendo a commit & push automático hacia `origin HEAD`..."
                ),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            await do_commit_and_push(update, context)
        elif code != 0 and has_git_changes:
            logger.warning(f"[AutoPush] Omitido por seguridad: La tarea finalizó con código {code} (timeout/error/503). No se enviarán cambios pendientes.")
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ *AutoPush Omitido:* La tarea fue interrumpida o superó el tiempo límite. Por seguridad, los cambios locales NO fueron enviados a Git.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        elif code == 0 and has_git_changes and len(session_touched) == 0:
            logger.info("[AutoPush] Omitido: Hay cambios en git pero no fueron generados por esta sesión de Antigravity.")
            await context.bot.send_message(
                chat_id=chat_id,
                text="ℹ️ *AutoPush Omitido:* Se detectaron cambios en Git, pero corresponden a modificaciones externas (IDE/manuales) y no a esta sesión de Antigravity. Usa `/commit` si deseas enviarlos manualmente.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

# =============================================================================
# COMANDOS DE TELEGRAM (/start, /projects, /sessions, etc.)
# =============================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    proj_name = os.path.basename(os.path.normpath(state.current_project)) if state.current_project else "Sin Proyecto"
    _, git_branch = run_cmd("git rev-parse --abbrev-ref HEAD")
    _, git_status = run_cmd("git status --short")
    git_badge = "🟢 Limpio" if not git_status.strip() else f"🟡 {len(git_status.splitlines())} archivos pendientes"

    ses_title = state.active_session_title or (state.active_session_id[:12] + "..." if state.active_session_id else "✨ Hilo Nuevo Limpio")
    model_name = AVAILABLE_MODELS.get(state.model, state.model)

    msg = (
        f"🚀 *Antigravity Mobile Command Bridge*\n"
        f"📍 *Modo Móvil:* Activo (Quito / Remoto)\n"
        f"──────────────────────────────\n"
        f"📁 *Proyecto:* `{proj_name}` `({git_branch.strip()})`\n"
        f"💬 *Sesión:* `{ses_title}`\n"
        f"🤖 *Modelo:* `{model_name}`\n"
        f"🌿 *Git:* {git_badge}\n"
        f"──────────────────────────────\n"
        f"💡 _Escribe cualquier instrucción para el agente o usa las opciones rápidas abajo (o escribe `/?` para ayuda):_"
    )

    keyboard = [
        [
            InlineKeyboardButton("📁 Proyectos", callback_data="btn_projects"),
            InlineKeyboardButton("💬 Sesiones", callback_data="btn_sessions"),
        ],
        [
            InlineKeyboardButton("🧠 Ver Plan", callback_data="view_plan"),
            InlineKeyboardButton("➕ Nueva Sesión", callback_data="ses_NEW"),
        ],
        [
            InlineKeyboardButton("🔍 Ver Diff", callback_data="view_diff"),
            InlineKeyboardButton("🚀 Commit & Push", callback_data="approve_push"),
        ],
        [
            InlineKeyboardButton("🤖 Cambiar Modelo", callback_data="btn_models"),
            InlineKeyboardButton("❓ Ayuda (/? )", callback_data="btn_help"),
        ],
    ]
    await safe_reply_message(msg_target, msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la lista de comandos disponibles adaptada al contexto actual."""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    proj_selected = bool(state.current_project and os.path.exists(state.current_project))
    session_active = bool(state.active_session_id)

    proj_name = os.path.basename(os.path.normpath(state.current_project)) if proj_selected else "Ninguno"
    ses_name = state.active_session_title or (state.active_session_id[:12] + "..." if state.active_session_id else "Ninguna (Hilo limpio)")

    help_text = (
        f"📖 *Guía de Comandos Antigravity Mobile*\n"
        f"──────────────────────────────\n"
        f"📍 *Contexto Actual:*\n"
        f"• 📁 *Proyecto:* `{proj_name}` {'✅' if proj_selected else '❌ (Debes elegir uno)'}\n"
        f"• 💬 *Sesión:* `{ses_name}` {'(Activa con historial)' if session_active else '(Hilo limpio)'}\n"
        f"• 🤖 *Modelo:* `{state.model}` | ⚙️ *Modo:* `{getattr(state, 'execution_mode', 'accept-edits')}`\n"
        f"──────────────────────────────\n\n"
    )

    help_text += "📁 *GESTIÓN DE PROYECTOS*\n"
    help_text += "• `/projects` - Listar y cambiar a otro repositorio\n"
    if proj_selected:
        help_text += "• `/exit_project` - Salir del proyecto activo y volver al selector\n"
    help_text += "\n"

    help_text += "💬 *GESTIÓN DE SESIONES (CHATS)*\n"
    help_text += "• `/stop` o `/cancel` - *Detener inmediatamente* cualquier tarea en ejecución\n"
    if session_active:
        help_text += "• `/continue` o `/continuar` - *Retomar tarea activa* sin reiniciar de cero\n"
        help_text += "• `/exit_session` o `/leave` - *Salir de la sesión actual* (modo limpio)\n"
        help_text += "• `/session <id>` - Cambiar directamente a otra sesión por ID\n"
    else:
        help_text += "• _Actualmente estás en modo Hilo Limpio. Tu próximo mensaje iniciará una nueva sesión._\n"
    help_text += "• `/sessions` - Listar las sesiones guardadas de este proyecto\n"
    help_text += "• `/new` - Forzar inicio de un hilo limpio en el proyecto\n\n"

    help_text += "🧠 *CEREBRO, MODOS & ARTEFACTOS*\n"
    help_text += "• `/plan [tarea]` - *Atajo:* Investigar y generar plan de arquitectura (o ver el plan actual)\n"
    help_text += "• `/mode` o `/modos` - Cambiar modo de ejecución (⚡ Directo vs 🧠 Planificación)\n"
    help_text += "• `/walkthrough` - Ver el informe de cambios implementados\n\n"

    help_text += "🌿 *GIT, RAMAS & COMMITS*\n"
    help_text += "• `/diff` - Ver cambios locales sin commitear (color diff)\n"
    help_text += "• `/commit [mensaje]` - Commit & Push (mensaje IA automático si se omite)\n"
    help_text += "• `/revert` - Descartar todos los cambios locales no commiteados\n"
    help_text += "• `/branches` - Listar ramas locales y cambiar entre ellas con botones\n"
    help_text += "• `/branch <nombre>` - Cambiar a una rama o crear una nueva rama local\n\n"

    help_text += "⚡ *CI/CD & AUTOMATIZACIÓN*\n"
    help_text += "• `/autopush` - Activar/desactivar commit y push automático tras cada orden\n"
    help_text += "• `/ci` - Estado en vivo del pipeline de GitHub Actions y opción de vigilar deploy\n"
    help_text += "• `/health <url>` - Comprobar disponibilidad HTTP, latencia y SSL de cualquier web\n\n"

    help_text += "⚙️ *SISTEMA, BATERÍA & TERMINAL*\n"
    help_text += "• `/status` - Panel integral de control, métricas de memoria, batería y atajos\n"
    help_text += "• `/battery` - Nivel de batería, estado AC y watchdog de cortes de energía\n"
    help_text += "• `/models` - Cambiar modelo (Gemini 3.8 Flash High, Claude, etc.)\n"
    help_text += "• `/cmd <comando>` - Ejecutar cualquier comando en terminal (ej: `/cmd git status`)\n"
    help_text += "• `/?` o `/help` - Ver esta guía contextual de ayuda\n"
    help_text += "• 📸 _Envía capturas de pantalla o fotos para diagnóstico multimodal con IA._\n"

    keyboard = [
        [
            InlineKeyboardButton("📁 Proyectos", callback_data="btn_projects"),
            InlineKeyboardButton("💬 Sesiones", callback_data="btn_sessions"),
        ],
        [
            InlineKeyboardButton("📊 Panel de Estado", callback_data="btn_status"),
            InlineKeyboardButton("⚙️ Modo", callback_data="btn_mode"),
        ],
        [
            InlineKeyboardButton("🧠 Ver Plan", callback_data="view_plan"),
            InlineKeyboardButton("🌿 Ramas", callback_data="btn_branches"),
        ]
    ]

    await safe_reply_message(msg_target, help_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_exit_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sale de la sesión activa y vuelve a modo limpio."""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    old_session = state.active_session_title or state.active_session_id or "Sesión"
    state.active_session_id = None
    state.active_session_title = None
    state.save()

    keyboard = [
        [
            InlineKeyboardButton("💬 Entrar a Otra Sesión", callback_data="btn_sessions"),
            InlineKeyboardButton("📁 Cambiar Proyecto", callback_data="btn_projects"),
        ]
    ]

    await safe_reply_message(
        msg_target,
        f"🚪 *Has salido de la sesión:* `{old_session}`\n\n"
        f"✨ *Modo Hilo Limpio activado.*\n"
        f"Tu próximo mensaje creará una conversación nueva e independiente con Antigravity, "
        f"o puedes usar `/sessions` para entrar a otra existente.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def cmd_exit_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sale del proyecto actual y solicita elegir uno nuevo."""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    old_proj = os.path.basename(os.path.normpath(state.current_project)) if state.current_project else "Proyecto"
    state.current_project = None
    state.active_session_id = None
    state.active_session_title = None
    state.save()

    await safe_reply_message(
        msg_target,
        f"🚪 *Has salido del proyecto:* `{old_proj}`\n\n"
        f"Elige un proyecto para continuar:",
    )
    await cmd_projects(update, context)

async def load_and_present_session(update_or_query: Any, target_sid: str):
    """Carga una sesión y muestra su última interacción y estado del cerebro."""
    state.active_session_id = target_sid
    state.active_session_title = get_session_title(target_sid)
    state.save()

    # Buscar contexto previo de la sesión
    ide_brain_session = os.path.join(IDE_BRAIN_DIR, target_sid)
    cli_brain_session = os.path.join(CLI_BRAIN_DIR, target_sid)
    brain_target = ide_brain_session if os.path.exists(ide_brain_session) else cli_brain_session

    _, last_user, last_agent = extract_transcript_context(brain_target)

    # Detección de artefactos
    plan_path = find_brain_artifact(target_sid, "implementation_plan.md")
    has_plan = bool(plan_path and os.path.exists(plan_path))

    walk_path = find_brain_artifact(target_sid, "walkthrough.md")
    has_walkthrough = bool(walk_path and os.path.exists(walk_path))

    proj_name = sanitize_telegram_markdown(os.path.basename(os.path.normpath(state.current_project)) if state.current_project else "Proyecto")
    title_clean = sanitize_telegram_markdown(state.active_session_title or "Sesión de trabajo")

    text = (
        f"🔄 *Sesión Cargada Exitosamente*\n"
        f"📌 *{title_clean}*\n"
        f"🆔 `{target_sid[:12]}...` | 📁 `{proj_name}`\n"
        f"──────────────────────────────\n"
    )

    if last_user:
        short_u = sanitize_telegram_markdown(last_user[:160]) + ("..." if len(last_user) > 160 else "")
        text += f"👤 *Última instrucción:*\n_{short_u}_\n\n"

    if last_agent:
        short_a = sanitize_telegram_markdown(last_agent[:260]) + ("..." if len(last_agent) > 260 else "")
        text += f"🤖 *Última respuesta:*\n_{short_a}_\n\n"

    text += "──────────────────────────────\n"
    text += "📋 *Artefactos detectados:*\n"
    text += f"{'✅ Plan de Implementación (`implementation_plan.md`)' if has_plan else '▫️ Sin plan de implementación'}\n"
    text += f"{'✅ Informe Walkthrough (`walkthrough.md`)' if has_walkthrough else '▫️ Sin walkthrough'}\n\n"
    text += "💡 _Tu siguiente mensaje continuará esta conversación, o usa las opciones rápidas:_"

    # Botones disponibles
    keyboard = []
    if has_plan:
        keyboard.append([
            InlineKeyboardButton("🧠 Ver Plan", callback_data="view_plan"),
            InlineKeyboardButton("▶️ Ejecutar Plan", callback_data="exec_plan"),
        ])

    second_row = []
    if has_walkthrough:
        second_row.append(InlineKeyboardButton("📄 Ver Walkthrough", callback_data="view_walkthrough"))
    second_row.append(InlineKeyboardButton("🔍 Ver Diff", callback_data="view_diff"))
    keyboard.append(second_row)

    keyboard.append([
        InlineKeyboardButton("💬 Cambiar Sesión", callback_data="btn_sessions"),
        InlineKeyboardButton("🚪 Salir de Sesión", callback_data="ses_NEW"),
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if hasattr(update_or_query, "edit_message_text"):
        await safe_edit_message(update_or_query, text, reply_markup=reply_markup)
    else:
        msg_target = update_or_query.effective_message
        await safe_reply_message(msg_target, text, reply_markup=reply_markup)

async def cmd_direct_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite entrar directamente a una sesión por ID: /session <id>"""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    if not context.args:
        await safe_reply_message(msg_target, "Uso: `/session <id>` (o usa `/sessions` para ver la lista con botones)")
        return

    target_id = context.args[0].strip()
    await load_and_present_session(update, target_id)

def get_windows_memory_status() -> str:
    """Devuelve el estado de memoria RAM de Windows mediante ctypes."""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', ctypes.c_ulong),
                ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong),
                ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong),
                ('ullAvailVirtual', ctypes.c_ulonglong),
                ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_gb = stat.ullTotalPhys / (1024**3)
        avail_gb = stat.ullAvailPhys / (1024**3)
        used_pct = stat.dwMemoryLoad
        return f"{avail_gb:.1f} GB libres de {total_gb:.1f} GB ({used_pct}% en uso)"
    except Exception:
        return "No disponible"

def get_power_status() -> Optional[Dict[str, Any]]:
    """Consulta el estado del hardware de energía de Windows (batería y cargador AC) mediante ctypes."""
    try:
        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ('ACLineStatus', ctypes.c_byte),
                ('BatteryFlag', ctypes.c_byte),
                ('BatteryLifePercent', ctypes.c_byte),
                ('SystemStatusFlag', ctypes.c_byte),
                ('BatteryLifeTime', ctypes.c_ulong),
                ('BatteryFullLifeTime', ctypes.c_ulong),
            ]
        sps = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
            return {
                "ac": sps.ACLineStatus,
                "pct": sps.BatteryLifePercent if sps.BatteryLifePercent != 255 else -1,
                "secs": sps.BatteryLifeTime if sps.BatteryLifeTime != 0xFFFFFFFF else -1,
            }
    except Exception as e:
        print(f"[Power Status Error] {e}")
    return None

def check_web_health(url: Optional[str] = None) -> Dict[str, Any]:
    """Mide disponibilidad, código HTTP y latencia en milisegundos de un endpoint web."""
    target_url = url if url else DEFAULT_HEALTH_URL
    start = time.time()
    try:
        req = urllib.request.Request(
            target_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityMobileMonitor/1.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            code = resp.getcode()
            elapsed_ms = int((time.time() - start) * 1000)
            return {"ok": True, "code": code, "ms": elapsed_ms, "url": target_url}
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {"ok": False, "error": str(e), "ms": elapsed_ms, "url": url}

def get_latest_ci_run(repo_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Consulta el último run de GitHub Actions del proyecto activo usando gh CLI."""
    target_cwd = repo_path if repo_path else state.current_project
    cmd = "gh run list --limit 1 --json databaseId,name,status,conclusion,url,createdAt,headBranch,headSha,displayTitle,event"
    code, out = run_cmd(cmd, cwd=target_cwd, timeout=20)
    if code == 0 and out.strip():
        try:
            data = json.loads(out)
            if data and isinstance(data, list):
                return data[0]
        except Exception:
            pass
    return None

def build_ci_view() -> Tuple[str, InlineKeyboardMarkup]:
    """Construye la vista interactiva del pipeline CI/CD en GitHub Actions."""
    run = get_latest_ci_run()
    if not run:
        text = (
            "🚀 *Pipeline CI/CD (GitHub Actions)*\n"
            "──────────────────────────────\n"
            "⚠️ No se encontró ninguna ejecución reciente o GitHub CLI (`gh`) no está disponible."
        )
        kb = [[InlineKeyboardButton("🔄 Refrescar", callback_data="ci_refresh")]]
        return text, InlineKeyboardMarkup(kb)

    run_id = run.get("databaseId")
    name = run.get("name", "Workflow")
    status = run.get("status", "unknown")
    conclusion = run.get("conclusion")
    branch = run.get("headBranch", "main")
    title = sanitize_telegram_markdown(run.get("displayTitle", ""))
    url = run.get("url", "")
    created = run.get("createdAt", "")
    ago = get_relative_time(created) if created else ""

    if status == "completed":
        if conclusion == "success":
            icon = "🟢"
            badge = "*Exitoso (Desplegado en Producción)*"
        elif conclusion == "failure":
            icon = "🔴"
            badge = "*Fallido (Revisar logs)*"
        elif conclusion == "cancelled":
            icon = "⚪"
            badge = "*Cancelado*"
        else:
            icon = "🟡"
            badge = f"*{conclusion or status}*"
    else:
        icon = "⏳"
        badge = f"*En Ejecución ({status})*"

    text = (
        f"🚀 *Estado del Pipeline CI/CD*\n"
        f"──────────────────────────────\n"
        f"{icon} *Estado:* {badge}\n"
        f"📋 *Workflow:* `{name}`\n"
        f"🌿 *Rama:* `{branch}`\n"
        f"📌 *Commit:* _{title}_\n"
        f"🕒 *Lanzado:* {ago}\n"
        f"🆔 `Run #{run_id}`\n"
        f"──────────────────────────────\n"
        f"🔗 [Abrir en GitHub Actions]({url})\n"
    )

    kb = []
    first_row = [InlineKeyboardButton("🔄 Refrescar", callback_data="ci_refresh")]
    if status != "completed":
        first_row.append(InlineKeyboardButton("👁️ Vigilar Fin de Deploy", callback_data=f"ci_watch_{run_id}"))
    elif conclusion == "failure":
        first_row.append(InlineKeyboardButton("📋 Ver Log de Error", callback_data=f"ci_logs_{run_id}"))

    kb.append(first_row)
    ci_bottom = []
    if DEFAULT_HEALTH_URL:
        ci_bottom.append(InlineKeyboardButton("🌐 Healthcheck Web", callback_data="btn_health"))
    ci_bottom.append(InlineKeyboardButton("📊 Volver a Estado", callback_data="btn_status"))
    kb.append(ci_bottom)
    return text, InlineKeyboardMarkup(kb)

async def watch_ci_pipeline(app, chat_id: int, run_id: int):
    """Sigue en segundo plano la ejecución de un run de GitHub Actions y avisa al usuario al concluir."""
    for _ in range(60):  # Hasta 15 minutos (60 * 15s)
        await asyncio.sleep(15)
        cmd = f"gh run view {run_id} --json status,conclusion,displayTitle,url"
        code, out = run_cmd(cmd, timeout=20)
        if code == 0 and out.strip():
            try:
                data = json.loads(out)
                curr_st = data.get("status")
                concl = data.get("conclusion")
                title = sanitize_telegram_markdown(data.get("displayTitle", ""))
                url = data.get("url", "")

                if curr_st == "completed":
                    if concl == "success":
                        msg = (
                            f"🎉 *¡DESPLIEGUE CI/CD EXITOSO!*\n"
                            f"──────────────────────────────\n"
                            f"🟢 El pipeline de `{title}` ha concluido exitosamente.\n"
                            f"🌐 Los cambios ya se encuentran en producción.\n\n"
                            f"🔗 [Ver detalles en GitHub]({url})"
                        )
                        deploy_kb = [[InlineKeyboardButton("🌐 Probar Healthcheck", callback_data="btn_health")]] if DEFAULT_HEALTH_URL else None
                        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(deploy_kb) if deploy_kb else None)
                    else:
                        msg = (
                            f"🚨 *¡FALLÓ EL PIPELINE CI/CD!*\n"
                            f"──────────────────────────────\n"
                            f"🔴 El pipeline de `{title}` falló con conclusión: `{concl}`.\n\n"
                            f"🔗 [Ver ejecución en GitHub]({url})"
                        )
                        _, fail_log = run_cmd(f"gh run view {run_id} --log-failed", timeout=30)
                        if fail_log.strip():
                            clean_fail = fail_log[-1200:].strip()
                            msg += f"\n\n📋 *Último log de error:*\n```text\n{clean_fail}\n```"
                        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode=constants.ParseMode.MARKDOWN)
                    return
            except Exception as e:
                print(f"[Watch CI Error] {e}")

def get_git_branches(repo_path: Optional[str] = None) -> List[Dict[str, str]]:
    """Obtiene la lista de ramas locales ordenadas por fecha de commit reciente."""
    target_cwd = repo_path if repo_path else state.current_project
    cmd = 'git branch --sort=-committerdate --format="%(refname:short)|%(authordate:relative)|%(subject)"'
    code, out = run_cmd(cmd, cwd=target_cwd, timeout=15)
    branches = []
    if code == 0 and out.strip():
        for line in out.splitlines():
            line = line.strip().strip("'\"")
            if not line:
                continue
            parts = line.split("|", 2)
            branches.append({
                "name": parts[0].strip(),
                "ago": parts[1].strip() if len(parts) > 1 else "",
                "subject": parts[2].strip() if len(parts) > 2 else "",
            })
    return branches

def build_branches_view() -> Tuple[str, InlineKeyboardMarkup]:
    """Construye la vista para examinar y cambiar de ramas Git interactivamente."""
    proj_name = sanitize_telegram_markdown(os.path.basename(os.path.normpath(state.current_project)) if state.current_project else "Proyecto")
    _, curr_branch = run_cmd("git rev-parse --abbrev-ref HEAD")
    curr_branch = curr_branch.strip()

    branches = get_git_branches()
    if not branches:
        text = f"🌿 *Gestor de Ramas Git en* `{proj_name}`:\n\n⚠️ No se encontraron ramas en el repositorio."
        kb = [[InlineKeyboardButton("🔄 Refrescar", callback_data="btn_branches")]]
        return text, InlineKeyboardMarkup(kb)

    text = (
        f"🌿 *Gestor de Ramas Git en* `{proj_name}`\n"
        f"📌 *Rama Actual:* `{curr_branch}`\n"
        f"──────────────────────────────\n\n"
    )

    kb = []
    for b in branches[:6]:
        bname = b["name"]
        ago = b["ago"]
        is_current = (bname == curr_branch)
        mark = "👉 " if is_current else "▫️ "
        text += f"{mark}*{bname}* `({ago})`\n"
        if b.get("subject"):
            subj_clean = sanitize_telegram_markdown(b['subject'][:50])
            text += f"   _{subj_clean}_\n"

        if not is_current:
            kb.append([InlineKeyboardButton(f"🔀 Cambiar a {bname[:22]}", callback_data=f"branch_co_{bname}")])

    kb.append([
        InlineKeyboardButton("🔄 Refrescar", callback_data="btn_branches"),
        InlineKeyboardButton("📊 Volver a Estado", callback_data="btn_status"),
    ])
    return text, InlineKeyboardMarkup(kb)

async def power_watchdog_task(app):
    """Monitorea el estado de energía del equipo host y alerta proactivamente si hay corte de luz."""
    if not WATCHDOG_ENABLED:
        print("[Watchdog] Desactivado según configuración ANTIGRAVITY_WATCHDOG_ENABLED.")
        return

    last_ac: Optional[int] = None
    while True:
        try:
            power = get_power_status()
            if power:
                curr_ac = power.get("ac")
                pct = power.get("pct", -1)
                secs = power.get("secs", -1)

                if last_ac is not None and curr_ac in (0, 1) and last_ac in (0, 1):
                    if last_ac == 1 and curr_ac == 0:
                        mins_left = f" (~{secs // 60} minutos estimados)" if secs > 0 else ""
                        msg = (
                            f"⚠️ *¡ALERTA DE ENERGÍA / CORTE DE LUZ!*\n"
                            f"El equipo remoto ahora está funcionando con *BATERÍA* 🔋 (`{pct}%`).{mins_left}\n"
                            f"El cargador se desconectó o la red eléctrica se interrumpió."
                        )
                        await app.bot.send_message(chat_id=MY_USER_ID, text=msg, parse_mode=constants.ParseMode.MARKDOWN)
                    elif last_ac == 0 and curr_ac == 1:
                        msg = (
                            f"⚡ *¡ENERGÍA ELÉCTRICA RESTAURADA!*\n"
                            f"El equipo remoto vuelve a estar conectado a la *RED ELÉCTRICA* (AC).\n"
                            f"Nivel actual de batería: 🔋 `{pct}%`."
                        )
                        await app.bot.send_message(chat_id=MY_USER_ID, text=msg, parse_mode=constants.ParseMode.MARKDOWN)


                if curr_ac in (0, 1):
                    last_ac = curr_ac
        except Exception as e:
            print(f"[Power Watchdog Error] {e}")
        await asyncio.sleep(WATCHDOG_INTERVAL)

def build_status_view() -> Tuple[str, InlineKeyboardMarkup]:
    """Construye la ficha enriquecida de estado del sistema, proyecto, sesión activa, última interacción y botones."""
    proj_name = sanitize_telegram_markdown(os.path.basename(os.path.normpath(state.current_project)) if state.current_project else "Sin Proyecto")
    model_label = AVAILABLE_MODELS.get(state.model, state.model)

    # Sesión activa estricta (si es None, el usuario está en Modo Hilo Limpio)
    active_sid = state.active_session_id
    if active_sid:
        if not state.active_session_title or state.active_session_title.strip() in ("", "Sesión sin título", "Sesión de trabajo"):
            state.active_session_title = get_session_title(active_sid)
            state.save()
    active_title = state.active_session_title

    title_clean = sanitize_telegram_markdown(active_title or "✨ Modo Hilo Limpio")
    sid_badge = f"`{active_sid[:12]}...`" if active_sid else "▫️ _Hilo limpio (nueva conversación al enviar mensaje)_"

    # Extraer última interacción y artefactos únicamente si hay una sesión activa
    last_u, last_a = "", ""
    has_plan = False
    has_walkthrough = False

    if active_sid:
        ide_brain_session = os.path.join(IDE_BRAIN_DIR, active_sid)
        cli_brain_session = os.path.join(CLI_BRAIN_DIR, active_sid)
        brain_target = ide_brain_session if os.path.exists(ide_brain_session) else cli_brain_session

        _, last_u, last_a = extract_transcript_context(brain_target)

        plan_path = find_brain_artifact(active_sid, "implementation_plan.md")
        has_plan = bool(plan_path and os.path.exists(plan_path))

        walk_path = find_brain_artifact(active_sid, "walkthrough.md")
        has_walkthrough = bool(walk_path and os.path.exists(walk_path))

    # Git status
    _, git_branch = run_cmd("git rev-parse --abbrev-ref HEAD")
    _, git_log = run_cmd('git log -1 --format="%h - %s"')
    _, git_stat = run_cmd("git status --short")
    has_git_changes = bool(git_stat.strip())

    mem_str = get_windows_memory_status()

    # Batería y fuente de energía
    power = get_power_status()
    power_str = "No disponible"
    if power:
        ac = power.get("ac")
        pct = power.get("pct", -1)
        ac_icon = "🔌 AC" if ac == 1 else ("🔋 Batería" if ac == 0 else "❓")
        power_str = f"{pct}% ({ac_icon})"

    mode_curr = getattr(state, "execution_mode", "accept-edits")
    mode_label = AVAILABLE_MODES.get(mode_curr, mode_curr)

    autopush_str = "🟢 Activado" if state.autopush else "⚪ Desactivado"

    text = (
        f"💻 *Estado del Servidor Remoto Antigravity*\n"
        f"──────────────────────────────\n"
        f"📁 *Proyecto:* `{proj_name}`\n"
        f"🤖 *Modelo:* `{model_label}`\n"
        f"⚙️ *Modo:* `{mode_label}`\n"
        f"💬 *Sesión:* *{title_clean}*\n"
        f"🆔 {sid_badge}\n"
        f"──────────────────────────────\n"
    )

    if last_u:
        short_u = sanitize_telegram_markdown(last_u[:160]) + ("..." if len(last_u) > 160 else "")
        text += f"👤 *Última instrucción:*\n_{short_u}_\n\n"

    if last_a:
        short_a = sanitize_telegram_markdown(last_a[:260]) + ("..." if len(last_a) > 260 else "")
        text += f"🤖 *Última respuesta:*\n_{short_a}_\n\n"

    git_line = f"`{git_branch.strip()}` (`{git_log.strip()}`)" if git_branch.strip() else "`No es repositorio git`"
    changes_line = "Directorio limpio" if not has_git_changes else f"{len(git_stat.strip().splitlines())} archivo(s) modificado(s)"

    text += (
        f"──────────────────────────────\n"
        f"🌿 *Git:* {git_line}\n"
        f"📊 *Cambios locales:* `{changes_line}`\n"
        f"⚡ *AutoPush:* `{autopush_str}`\n"
        f"🔋 *Batería / AC:* `{power_str}`\n"
        f"🧠 *Memoria Windows:* `{mem_str}`\n"
    )

    if active_sid:
        text += (
            f"📋 *Artefactos de esta sesión:* "
            f"{'✅ Plan ' if has_plan else '▫️ Sin Plan '}| "
            f"{'✅ Walkthrough' if has_walkthrough else '▫️ Sin Walkthrough'}\n"
        )
    else:
        text += "📋 *Artefactos:* ▫️ _Modo Hilo Limpio (sin sesión activa)_\n"

    # Botones interactivos
    keyboard = []
    first_row = []
    if has_plan:
        first_row.append(InlineKeyboardButton("🧠 Ver Plan", callback_data="view_plan"))
        first_row.append(InlineKeyboardButton("▶️ Ejecutar Plan", callback_data="exec_plan"))
    if first_row:
        keyboard.append(first_row)

    second_row = []
    if has_walkthrough:
        second_row.append(InlineKeyboardButton("📄 Ver Walkthrough", callback_data="view_walkthrough"))
    second_row.append(InlineKeyboardButton("🔍 Ver Diff", callback_data="view_diff"))
    if has_git_changes:
        second_row.append(InlineKeyboardButton("✅ Commit", callback_data="approve_push"))
    keyboard.append(second_row)

    # Botones Super Dev (AutoPush, CI/CD, Ramas)
    autopush_btn_text = f"⚡ AutoPush: {'ON' if state.autopush else 'OFF'}"
    keyboard.append([
        InlineKeyboardButton(autopush_btn_text, callback_data="toggle_autopush"),
        InlineKeyboardButton("🚀 CI/CD", callback_data="btn_ci"),
        InlineKeyboardButton("🌿 Ramas", callback_data="btn_branches"),
    ])

    # Gestión de Sistema y Refresco
    keyboard.append([
        InlineKeyboardButton("🔋 Batería", callback_data="btn_battery"),
        InlineKeyboardButton("🔄 Refrescar", callback_data="btn_status"),
    ])

    if active_sid:
        keyboard.append([
            InlineKeyboardButton("💬 Sesiones", callback_data="btn_sessions"),
            InlineKeyboardButton("⚙️ Modo", callback_data="btn_mode"),
            InlineKeyboardButton("🚪 Salir de Sesión", callback_data="ses_NEW"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("💬 Sesiones", callback_data="btn_sessions"),
            InlineKeyboardButton("📁 Proyectos", callback_data="btn_projects"),
            InlineKeyboardButton("⚙️ Modo", callback_data="btn_mode"),
        ])

    return text, InlineKeyboardMarkup(keyboard)

async def show_status_view(update_or_query: Any):
    """Muestra o edita en vivo el panel de estado con botones interactivos."""
    text, markup = build_status_view()
    if hasattr(update_or_query, "edit_message_text"):
        await safe_edit_message(update_or_query, text, reply_markup=markup)
    else:
        msg_target = update_or_query.effective_message
        await safe_reply_message(msg_target, text, reply_markup=markup)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await show_status_view(update)

async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    state.project_cache.clear()
    git_projects = []

    for root in WORKSPACE_ROOTS:
        if not os.path.exists(root):
            continue
        try:
            if os.path.exists(os.path.join(root, ".git")):
                git_projects.append((os.path.basename(os.path.normpath(root)), os.path.normpath(root)))
                continue

            for d in os.listdir(root):
                full_p = os.path.normpath(os.path.join(root, d))
                if os.path.isdir(full_p) and os.path.exists(os.path.join(full_p, ".git")):
                    git_projects.append((d, full_p))
        except Exception as e:
            print(f"[Projects] Error escaneando {root}: {e}")

    if not git_projects:
        await safe_reply_message(msg_target, "⚠️ No se encontraron repositorios Git en las rutas configuradas.")
        return

    keyboard = []
    text = "📁 *Selecciona el Proyecto para trabajar:*\n\n"

    for idx, (name, path) in enumerate(git_projects):
        key = str(idx)
        state.project_cache[key] = path
        mark = "👉 " if path == state.current_project else "▫️ "
        parent = os.path.basename(os.path.dirname(path))
        text += f"{mark}*{name}* `({parent})`\n"
        keyboard.append([InlineKeyboardButton(f"{'👉 ' if path == state.current_project else ''}Abrir {name}", callback_data=f"proj_{key}")])

    await safe_reply_message(msg_target, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    if not state.current_project:
        await safe_reply_message(msg_target, "⚠️ Primero selecciona un proyecto con `/projects`.")
        return

def build_sessions_view(project_path: Optional[str], active_session_id: Optional[str]) -> Tuple[str, InlineKeyboardMarkup]:
    """Construye el texto y teclado formateado y seguro para listar sesiones."""
    proj_name = sanitize_telegram_markdown(os.path.basename(os.path.normpath(project_path)) if project_path else "Proyecto")
    sessions = query_sessions(limit=8, project_filter=project_path)

    if not sessions:
        text = f"💬 *Sesiones de Antigravity en* `{proj_name}`:\n\nNo se encontraron sesiones previas para este proyecto. Escribe un mensaje para iniciar una nueva."
        keyboard = [[InlineKeyboardButton("➕ Iniciar Hilo Limpio", callback_data="ses_NEW")]]
        return text, InlineKeyboardMarkup(keyboard)

    text = f"💬 *Sesiones de Antigravity en* `{proj_name}`:\n\n"
    keyboard = []

    for s in sessions:
        sid = s["id"]
        title = sanitize_telegram_markdown(s["title"])
        prev = sanitize_telegram_markdown(s.get("preview", ""))
        ago = s["time"]
        src = s.get("source", "cli").upper()
        is_active = (sid == active_session_id)
        mark = "👉 " if is_active else ""

        text += f"{mark}📌 *{title}*{' _(ACTIVA)_' if is_active else ''}\n"
        if prev and prev != title:
            text += f"💬 _{prev}_\n"
        text += f"🕒 {ago} | [{src}] 🆔 `{sid[:12]}...`\n\n"

        btn_label = f"{'👉 ' if is_active else ''}📌 {title[:25]}"
        keyboard.append([InlineKeyboardButton(btn_label, callback_data=f"ses_{sid}")])

    keyboard.append([InlineKeyboardButton("➕ Iniciar Hilo Limpio", callback_data="ses_NEW")])
    return text, InlineKeyboardMarkup(keyboard)

async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    if not state.current_project:
        await safe_reply_message(msg_target, "⚠️ Primero selecciona un proyecto con `/projects`.")
        return

    text, markup = build_sessions_view(state.current_project, state.active_session_id)
    await safe_reply_message(msg_target, text, reply_markup=markup)

async def cmd_new_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_exit_session(update, context)

async def cmd_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Continúa la tarea activa exactamente donde quedó sin reiniciar desde cero."""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    if not state.current_project:
        await safe_reply_message(msg_target, "⚠️ No has seleccionado un proyecto. Envía `/projects` primero.")
        return

    if not state.active_session_id:
        await safe_reply_message(msg_target, "⚠️ No hay una sesión activa para continuar. Selecciona una sesión con `/sessions`.")
        return

    extra_instructions = " ".join(context.args).strip() if context.args else ""
    prompt = CONTINUE_TASK_PROMPT
    if extra_instructions:
        prompt += f"\n\nInstrucciones adicionales del usuario:\n{extra_instructions}"

    await execute_antigravity_task(update, context, prompt)

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detiene cualquier tarea de Antigravity que esté corriendo en ese momento."""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    stopped = stop_task_now()
    if stopped:
        await safe_reply_message(msg_target, "🛑 *Tarea detenida de inmediato.* Se cancelaron todos los procesos en ejecución.")
    else:
        await safe_reply_message(msg_target, "ℹ️ No había ninguna tarea activa en ejecución (se verificó y limpió cualquier proceso residual).")

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    msg_target = update.effective_message

    # 1. Detectar si el usuario incluyó una petición: /plan <tarea...>
    raw_text = update.message.text.strip() if update.message and update.message.text else ""
    plan_prompt = ""
    if raw_text:
        match = re.match(r"^/plan(?:@\w+)?(?:\s+(.+))?$", raw_text, re.DOTALL | re.IGNORECASE)
        if match and match.group(1):
            plan_prompt = match.group(1).strip()
    if not plan_prompt and context.args:
        plan_prompt = " ".join(context.args).strip()

    if plan_prompt:
        if not state.current_project:
            await safe_reply_message(msg_target, "⚠️ No has seleccionado un proyecto. Envía `/projects` primero.")
            return

        state.last_prompt = f"/plan {plan_prompt}"
        # Ejecutar Antigravity directamente en modo plan con telemetría en vivo
        await execute_antigravity_task(update, context, plan_prompt, mode="plan")
        return

    # 2. Si se ejecutó solo "/plan" sin argumentos, mostramos el plan actual si existe
    if not state.active_session_id:
        await safe_reply_message(
            msg_target,
            "🧠 *Modo Planificación de Antigravity*\n"
            "──────────────────────────────\n"
            "No hay ninguna sesión activa en este momento (estás en *Modo Hilo Limpio*).\n\n"
            "💡 *Atajo Rápido de Planificación:*\n"
            "Escribe `/plan <tu petición>` para que Antigravity investigue el código, analice dependencias y construya un plan formal de implementación sin modificar archivos todavía.\n\n"
            "_Ejemplo:_\n"
            "`/plan Agregar autenticación OAuth2 con Google y migración de BD`\n\n"
            "• O usa `/sessions` para cargar una conversación previa que ya tenga un plan.",
        )
        return

    plan_file = find_brain_artifact(state.active_session_id, "implementation_plan.md")
    ses_name = state.active_session_title or state.active_session_id[:8]
    if not plan_file or not os.path.exists(plan_file):
        await safe_reply_message(
            msg_target,
            f"⚠️ La sesión activa (*{ses_name}*) no tiene ningún `implementation_plan.md` registrado.\n\n"
            f"💡 *Para planificar en esta sesión:*\n"
            f"Escribe `/plan <tu petición>` (ej: `/plan refactorizar modelo de usuarios`) "
            f"y Antigravity construirá el plan paso a paso sin modificar código todavía.",
        )
        return

    summary = extract_plan_summary(plan_file)
    keyboard = [
        [InlineKeyboardButton("▶️ Ejecutar Plan", callback_data="exec_plan")],
        [InlineKeyboardButton("🔍 Ver Diff Actual", callback_data="view_diff")],
    ]

    header = f"🧠 *Plan de Implementación Detectado*\n📌 *{ses_name}*\n📂 `{os.path.basename(os.path.dirname(plan_file))}`\n──────────────────────────────\n\n"
    full_text = header + summary

    await send_smart_message(
        context=context,
        chat_id=update.effective_chat.id,
        text=full_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        doc_filename="implementation_plan.md",
        caption="📄 Plan de implementación completo para leer en móvil:",
    )

async def cmd_walkthrough(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    if not state.active_session_id:
        await safe_reply_message(
            msg_target,
            "⚠️ No hay ninguna sesión activa (estás en *Modo Hilo Limpio*).\n"
            "Usa `/sessions` para entrar a una sesión que tenga walkthrough registrado.",
        )
        return

    walk_file = find_brain_artifact(state.active_session_id, "walkthrough.md")
    ses_name = state.active_session_title or state.active_session_id[:8]
    if not walk_file or not os.path.exists(walk_file):
        await safe_reply_message(
            msg_target,
            f"⚠️ La sesión activa (*{ses_name}*) no tiene ningún `walkthrough.md` registrado.",
        )
        return

    with open(walk_file, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    await send_smart_message(
        context=context,
        chat_id=update.effective_chat.id,
        text=f"📄 *Walkthrough de Tareas Completadas:*\n📌 *{ses_name}*\n\n{content}",
        doc_filename="walkthrough.md",
        caption="📄 Informe completo de cambios Walkthrough:",
    )

def get_session_modified_files(session_id: Optional[str]) -> List[str]:
    """Extrae los archivos editados o creados por Antigravity en la sesión activa desde el transcript."""
    if not session_id:
        return []
    files = set()
    for root in [CLI_BRAIN_DIR, IDE_BRAIN_DIR]:
        log_p = os.path.join(root, session_id, ".system_generated", "logs", "transcript.jsonl")
        if os.path.exists(log_p):
            try:
                with open(log_p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            for tc in data.get("tool_calls", []):
                                t_name = tc.get("name", "")
                                args = tc.get("args", {})
                                if t_name in ["replace_file_content", "multi_replace_file_content", "write_to_file"]:
                                    tf = args.get("TargetFile") or args.get("Path") or ""
                                    if tf and "implementation_plan.md" not in tf and "walkthrough.md" not in tf:
                                        files.add(os.path.basename(tf))
                        except Exception:
                            continue
            except Exception:
                pass
    return sorted(list(files))

async def cmd_diff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los archivos modificados y el diff de la última iteración o cambios locales pendientes."""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    if not state.current_project:
        await safe_reply_message(msg_target, "⚠️ No has seleccionado un proyecto. Envía `/projects` primero.")
        return

    # 1. Asegurar detección de archivos nuevos no rastreados
    run_cmd("git add -N .")

    # 2. Comprobar si hay cambios pendientes en el árbol de trabajo
    code_stat, stat = run_cmd("git diff --stat")
    code_diff, full_diff = run_cmd("git diff")
    has_uncommitted = bool(full_diff.strip())

    session_files = get_session_modified_files(state.active_session_id)
    session_files_str = ""
    if session_files:
        session_files_str = "📝 *Archivos tocados en esta sesión:*\n" + "\n".join(f"• `{f}`" for f in session_files[:10]) + "\n\n"

    # CASO 1: Hay cambios locales sin commitear
    if has_uncommitted:
        keyboard = [
            [InlineKeyboardButton("✅ Commit & Push", callback_data="approve_push")],
            [InlineKeyboardButton("🗑️ Revertir Cambios", callback_data="revert_prompt")],
        ]
        stat_clean = stat.strip() if stat.strip() else "Archivos pendientes"
        header = (
            f"🔍 *Cambios Locales Pendientes (Sin Commitear)*\n"
            f"──────────────────────────────\n"
            f"{session_files_str}"
            f"📊 *Archivos Modificados:*\n`{stat_clean}`\n\n"
        )
        if len(full_diff) <= 2800:
            await safe_reply_message(
                msg_target,
                f"{header}```diff\n{full_diff}\n```",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await send_smart_message(
                context=context,
                chat_id=update.effective_chat.id,
                text=f"{header}_Descarga el archivo adjunto para ver las líneas exactas del diff._",
                reply_markup=InlineKeyboardMarkup(keyboard),
                doc_filename="changes.diff",
                caption="📄 Archivo completo de cambios Git Diff:",
            )
        return

    # CASO 2: El árbol de trabajo está limpio (cambios ya commiteados, ej. por AutoPush)
    _, commit_info = run_cmd('git log -1 --format="%h | %s (%cr)"')
    _, commit_stat = run_cmd("git show --stat --oneline -1 HEAD")
    _, commit_diff = run_cmd('git show --format="" -p HEAD')

    stat_lines = commit_stat.strip().splitlines()
    clean_stat = "\n".join(stat_lines[1:]).strip() if len(stat_lines) > 1 else (stat_lines[0] if stat_lines else "Sin detalles")

    keyboard = [
        [
            InlineKeyboardButton("🚀 CI/CD", callback_data="btn_ci"),
            InlineKeyboardButton("🌿 Ramas", callback_data="btn_branches"),
            InlineKeyboardButton("📊 Ver Estado", callback_data="btn_status"),
        ]
    ]

    header = (
        f"🌿 *Directorio Limpio (Cambios Ya Commiteados)*\n"
        f"──────────────────────────────\n"
        f"{session_files_str}"
        f"📌 *Último Commit:* `{commit_info.strip()}`\n\n"
        f"📊 *Archivos Modificados en este Commit:*\n`{clean_stat}`\n\n"
    )

    if commit_diff.strip():
        if len(commit_diff) <= 2800:
            await safe_reply_message(
                msg_target,
                f"{header}```diff\n{commit_diff}\n```",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await send_smart_message(
                context=context,
                chat_id=update.effective_chat.id,
                text=f"{header}_Descarga el archivo adjunto para ver el diff de código completo._",
                reply_markup=InlineKeyboardMarkup(keyboard),
                doc_filename="latest_commit.diff",
                caption="📄 Diff completo del último commit:",
            )
    else:
        await safe_reply_message(
            msg_target,
            f"{header}_No hay diferencias registradas en el historial reciente._",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

async def cmd_commit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    user_msg = " ".join(context.args).strip() if context.args else ""
    await do_commit_and_push(update, context, custom_msg=user_msg)

async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    keyboard = []
    text = "🤖 *Selecciona el Modelo de IA para Antigravity:*\n\n"

    for m_id, m_label in AVAILABLE_MODELS.items():
        mark = "👉 " if m_id == state.model else "▫️ "
        text += f"{mark}*{m_label}*\nID: `{m_id}`\n\n"
        keyboard.append([InlineKeyboardButton(f"{'👉 ' if m_id == state.model else ''}{m_label}", callback_data=f"model_{m_id}")])

    await safe_reply_message(msg_target, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite ver o cambiar el modo de ejecución (Directo vs Planificación)."""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    curr = getattr(state, "execution_mode", "accept-edits")
    curr_label = AVAILABLE_MODES.get(curr, curr)

    keyboard = [
        [
            InlineKeyboardButton(
                f"{'👉 ' if curr == 'accept-edits' else ''}⚡ Directo (accept-edits)",
                callback_data="set_mode:accept-edits",
            )
        ],
        [
            InlineKeyboardButton(
                f"{'👉 ' if curr == 'plan' else ''}🧠 Planificación (plan)",
                callback_data="set_mode:plan",
            )
        ],
    ]

    text = (
        f"⚙️ *Modo de Ejecución de Antigravity*\n"
        f"──────────────────────────────\n"
        f"Modo actual: *{curr_label}*\n\n"
        f"• *⚡ Directo (`accept-edits`):* Antigravity analiza, edita archivos y ejecuta de inmediato. Máxima velocidad y fluidez.\n\n"
        f"• *🧠 Planificación (`plan`):* Antigravity analiza la arquitectura, crea `implementation_plan.md` en el cerebro y espera tu aprobación antes de modificar código.\n\n"
        f"💡 *Tip Pro:* ¡No necesitas cambiar de modo permanentemente! Escribe `/plan <tu tarea>` en cualquier momento para activar el planificador al vuelo."
    )

    await safe_reply_message(msg_target, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ejecuta cualquier comando en la consola del proyecto (/cmd mvnw test, etc.)"""
    if not is_authorized(update):
        return

    msg_target = update.effective_message
    custom_cmd = " ".join(context.args).strip() if context.args else ""
    if not custom_cmd:
        await safe_reply_message(msg_target, "Uso: `/cmd <comando>` (ej: `/cmd git status` o `/cmd npm test`)")
        return

    code, output = run_cmd(custom_cmd, timeout=120)
    out_clean = output if output.strip() else "(Comando ejecutado sin salida)"
    await send_smart_message(
        context=context,
        chat_id=update.effective_chat.id,
        text=f"💻 *Salida de:* `{custom_cmd}`\n\n```text\n{out_clean[:3500]}\n```",
        doc_filename="terminal_output.txt",
        caption=f"Salida de: {custom_cmd}",
    )

async def cmd_autopush(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activa o desactiva el modo Turbo AutoPush."""
    if not is_authorized(update):
        return
    msg_target = update.effective_message
    state.autopush = not state.autopush
    state.save()
    status_str = "🟢 *ACTIVADO* (Cada cambio generado por Antigravity se commiteará y enviará a origin HEAD automáticamente)" if state.autopush else "⚪ *DESACTIVADO* (Modo manual con botones interactivos)"
    await safe_reply_message(
        msg_target,
        f"⚡ *Modo Turbo AutoPush:* {status_str}\n\n"
        f"Puedes alternar este modo en cualquier momento con `/autopush` o desde el panel `/status`."
    )

async def cmd_ci(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado en vivo del pipeline CI/CD en GitHub Actions."""
    if not is_authorized(update):
        return
    msg_target = update.effective_message
    text, markup = build_ci_view()
    await safe_reply_message(msg_target, text, reply_markup=markup)

async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comprueba disponibilidad, latencia y HTTPS de una aplicación web."""
    if not is_authorized(update):
        return
    msg_target = update.effective_message
    url = context.args[0].strip() if context.args else DEFAULT_HEALTH_URL
    if not url:
        await safe_reply_message(
            msg_target,
            "ℹ️ *Comprobación de Estado Web (`/health`)*\n\n"
            "Indica la URL que deseas monitorear:\n"
            "• `/health http://localhost:3000`\n"
            "• `/health https://mi-dominio.com`\n\n"
            "_💡 El estado de tu bot y tu laptop se verifica directamente con `/status` (si el bot te responde, tu laptop está online)._",
        )
        return

    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    await safe_reply_message(msg_target, f"🌐 _Comprobando disponibilidad de {url}..._")
    res = check_web_health(url)
    if res["ok"]:
        text = (
            f"🌐 *Web Healthcheck:* 🟢 *ONLINE*\n"
            f"──────────────────────────────\n"
            f"🔗 *URL:* `{res['url']}`\n"
            f"📡 *Respuesta:* `HTTP {res['code']} OK`\n"
            f"⚡ *Latencia:* `{res['ms']} ms`\n"
            f"🔒 *Seguridad:* HTTPS / SSL Verificado\n"
        )
    else:
        text = (
            f"🌐 *Web Healthcheck:* 🔴 *ERROR*\n"
            f"──────────────────────────────\n"
            f"🔗 *URL:* `{res['url']}`\n"
            f"⚠️ *Fallo:* `{res['error']}`\n"
            f"⏱️ *Tiempo:* `{res['ms']} ms`\n"
        )
    kb = [
        [
            InlineKeyboardButton("🔄 Probar de nuevo", callback_data=f"health_check_{url}"),
            InlineKeyboardButton("🚀 Ver CI/CD", callback_data="btn_ci"),
        ],
        [
            InlineKeyboardButton("📊 Volver a Estado", callback_data="btn_status"),
        ]
    ]
    await safe_reply_message(msg_target, text, reply_markup=InlineKeyboardMarkup(kb))

async def cmd_battery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado de la batería y alimentación AC del host remoto."""
    if not is_authorized(update):
        return
    msg_target = update.effective_message
    power = get_power_status()
    if not power:
        await safe_reply_message(msg_target, "⚠️ No se pudo obtener información de energía del equipo.")
        return

    ac = power.get("ac")
    pct = power.get("pct", -1)
    secs = power.get("secs", -1)

    if ac == 1:
        ac_label = "⚡ Enchufado a la Red (AC - Batería protegida)"
        icon = "🔌"
    elif ac == 0:
        ac_label = "🔋 Funcionando con Batería (Desconectado de AC)"
        icon = "🔋"
    else:
        ac_label = "Desconocido"
        icon = "❓"

    time_str = f"{secs // 60} minutos restantes" if secs > 0 else ("Ilimitado (Conectado a corriente)" if ac == 1 else "Calculando...")

    text = (
        f"🔋 *Monitor de Energía del Servidor (Host Remoto)*\n"

        f"──────────────────────────────\n"
        f"{icon} *Fuente:* {ac_label}\n"
        f"📊 *Nivel de Batería:* `{pct}%`\n"
        f"⏱️ *Tiempo Estimado:* `{time_str}`\n"
        f"🛡️ *Watchdog Activo:* Alerta proactiva configurada ante cortes de luz.\n"
    )
    kb = [
        [
            InlineKeyboardButton("🔄 Refrescar", callback_data="btn_battery"),
            InlineKeyboardButton("📊 Ver Estado", callback_data="btn_status"),
        ]
    ]
    await safe_reply_message(msg_target, text, reply_markup=InlineKeyboardMarkup(kb))

async def cmd_branches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista las ramas locales y permite cambiar entre ellas."""
    if not is_authorized(update):
        return
    msg_target = update.effective_message
    if not state.current_project:
        await safe_reply_message(msg_target, "⚠️ Selecciona un proyecto primero con `/projects`.")
        return
    text, markup = build_branches_view()
    await safe_reply_message(msg_target, text, reply_markup=markup)

async def cmd_branch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cambia a una rama o crea una nueva: /branch <nombre>"""
    if not is_authorized(update):
        return
    msg_target = update.effective_message
    if not context.args:
        await cmd_branches(update, context)
        return

    target_b = context.args[0].strip()
    code, out = run_cmd(f"git checkout {target_b}")
    if code != 0:
        code_b, out_b = run_cmd(f"git checkout -b {target_b}")
        if code_b == 0:
            await safe_reply_message(msg_target, f"🌱 *Nueva rama creada y activada:* `{target_b}`")
        else:
            await safe_reply_message(msg_target, f"⚠️ Error al cambiar de rama:\n`{out_b}`")
    else:
        await safe_reply_message(msg_target, f"🌿 *Cambiado exitosamente a la rama:* `{target_b}`")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja capturas de pantalla o fotos enviadas por Telegram y las pasa a Antigravity."""
    if not is_authorized(update):
        return
    if not state.current_project:
        await safe_reply_message(update.effective_message, "⚠️ No has seleccionado un proyecto. Envía `/projects` primero.")
        return

    msg = update.effective_message
    if not msg or not msg.photo:
        return

    photo = msg.photo[-1]
    temp_dir = os.path.join(BASE_DIR, "temp_media")
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, f"photo_{int(time.time())}_{photo.file_unique_id}.jpg")

    try:
        photo_file = await photo.get_file()
        await photo_file.download_to_drive(custom_path=file_path)
    except Exception as e:
        await safe_reply_message(msg, f"⚠️ Error descargando imagen: {e}")
        return

    caption = (msg.caption or "").strip()
    prompt_text = (
        f"[IMAGEN ADJUNTA EN: {file_path}]\n\n"
        f"{caption if caption else 'El usuario ha enviado esta captura de pantalla de la interfaz o del sistema. Por favor examínala con tus capacidades multimodales para resolver o diagnosticar el problema.'}"
    )

    state.last_prompt = caption or "Analizar captura de pantalla"
    await execute_antigravity_task(update, context, prompt_text)

# =============================================================================
# OPERACIÓN COMMIT & PUSH ASISTIDA POR IA
# =============================================================================
async def do_commit_and_push(update_or_query: Any, context: ContextTypes.DEFAULT_TYPE, custom_msg: str = ""):
    chat_id = update_or_query.effective_chat.id

    _, diff_stat = run_cmd("git status --short")
    if not diff_stat.strip():
        msg = "🌿 *No hay cambios para commitear.* El repositorio está limpio."
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=constants.ParseMode.MARKDOWN)
        return

    commit_msg = custom_msg.strip()
    if not commit_msg:
        await context.bot.send_message(chat_id=chat_id, text="🤖 _Generando mensaje de commit con IA..._", parse_mode=constants.ParseMode.MARKDOWN)
        
        _, quick_diff = run_cmd("git diff --stat")
        prompt_commit = (
            f"Genera un mensaje de commit convencional corto y preciso en español "
            f"(1 sola línea, máximo 60 caracteres, ej: 'feat(lpr): agregar validacion de placas'). "
            f"No agregues comillas ni explicaciones adicionales. Los cambios son:\n{quick_diff[:800]}"
        )
        code_ai, ai_msg = run_cmd(
            f'agy --model gemini-3.8-flash-high --disable-slash-commands --dangerously-skip-permissions -p "{prompt_commit}"',
            timeout=90,
        )
        
        clean_ai_msg = ai_msg.splitlines()[-1].strip().replace('"', '').replace('`', '') if ai_msg else ""
        if (
            code_ai == 0
            and clean_ai_msg
            and not clean_ai_msg.startswith("⚠️")
            and "excedió el tiempo límite" not in clean_ai_msg
            and len(clean_ai_msg) < 80
        ):
            commit_msg = clean_ai_msg
        elif state.last_prompt:
            clean_p = sanitize_telegram_markdown(state.last_prompt)[:50].strip()
            commit_msg = f"feat(mobile): {clean_p}"
        else:
            commit_msg = "feat(mobile): actualizacion desde antigravity bridge"

    run_cmd("git add -A")
    code_c, out_c = run_cmd(f'git commit -m "{commit_msg}"')
    code_p, out_p = run_cmd("git push origin HEAD", timeout=90)

    _, commit_hash = run_cmd("git rev-parse --short HEAD")
    _, current_branch = run_cmd("git rev-parse --abbrev-ref HEAD")

    result_text = (
        f"🚀 *¡Cambios Commiteados y Enviados Exitosamente!*\n\n"
        f"📌 *Commit:* `{commit_msg}`\n"
        f"🔗 *Hash:* `{commit_hash.strip()}` | 🌿 *Rama:* `{current_branch.strip()}`\n\n"
        f"🌐 *Push:* `origin HEAD`\n"
        f"```text\n{out_p[-600:] if len(out_p) > 600 else out_p}\n```"
    )

    await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode=constants.ParseMode.MARKDOWN)

    # Comprobar si GitHub Actions inicia un pipeline automáticamente
    try:
        await asyncio.sleep(2)
        latest_run = get_latest_ci_run()
        if latest_run and latest_run.get("status") != "completed":
            run_id = latest_run.get("databaseId")
            kb = [
                [
                    InlineKeyboardButton("👁️ Vigilar Despliegue", callback_data=f"ci_watch_{run_id}"),
                    InlineKeyboardButton("🚀 Ver CI/CD", callback_data="btn_ci"),
                ]
            ]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚀 *Pipeline CI/CD Disparado en GitHub Actions*\nWorkflow `{latest_run.get('name', 'Deploy')}` en ejecución...",
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(kb),
            )
    except Exception:
        pass

# =============================================================================
# MANEJADOR DE BOTONES INTERACTIVOS (CALLBACK QUERY)
# =============================================================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != MY_USER_ID:
        return

    data = query.data

    try:
        # Menús y pantallas
        if data == "btn_projects":
            state.project_cache.clear()
            git_projects = []
            for root in WORKSPACE_ROOTS:
                if not os.path.exists(root):
                    continue
                try:
                    if os.path.exists(os.path.join(root, ".git")):
                        git_projects.append((os.path.basename(os.path.normpath(root)), os.path.normpath(root)))
                        continue
                    for d in os.listdir(root):
                        full_p = os.path.normpath(os.path.join(root, d))
                        if os.path.isdir(full_p) and os.path.exists(os.path.join(full_p, ".git")):
                            git_projects.append((d, full_p))
                except Exception:
                    pass

            keyboard = []
            text = "📁 *Selecciona el Proyecto para trabajar:*\n\n"
            for idx, (name, path) in enumerate(git_projects):
                key = str(idx)
                state.project_cache[key] = path
                mark = "👉 " if path == state.current_project else "▫️ "
                parent = os.path.basename(os.path.dirname(path))
                text += f"{mark}*{name}* `({parent})`\n"
                keyboard.append([InlineKeyboardButton(f"{'👉 ' if path == state.current_project else ''}Abrir {name}", callback_data=f"proj_{key}")])
            await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data == "btn_sessions":
            text, markup = build_sessions_view(state.current_project, state.active_session_id)
            await safe_edit_message(query, text, reply_markup=markup)
            return

        elif data == "btn_models":
            keyboard = []
            text = "🤖 *Selecciona el Modelo de IA para Antigravity:*\n\n"
            for m_id, m_label in AVAILABLE_MODELS.items():
                mark = "👉 " if m_id == state.model else "▫️ "
                text += f"{mark}*{m_label}*\nID: `{m_id}`\n\n"
                keyboard.append([InlineKeyboardButton(f"{'👉 ' if m_id == state.model else ''}{m_label}", callback_data=f"model_{m_id}")])
            await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data == "btn_mode":
            curr = getattr(state, "execution_mode", "accept-edits")
            curr_label = AVAILABLE_MODES.get(curr, curr)
            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{'👉 ' if curr == 'accept-edits' else ''}⚡ Directo (accept-edits)",
                        callback_data="set_mode:accept-edits",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"{'👉 ' if curr == 'plan' else ''}🧠 Planificación (plan)",
                        callback_data="set_mode:plan",
                    )
                ],
                [
                    InlineKeyboardButton("📊 Volver a Estado", callback_data="btn_status"),
                ]
            ]
            text = (
                f"⚙️ *Modo de Ejecución de Antigravity*\n"
                f"──────────────────────────────\n"
                f"Modo actual: *{curr_label}*\n\n"
                f"• *⚡ Directo (`accept-edits`):* Antigravity analiza, edita archivos y ejecuta de inmediato. Máxima velocidad y fluidez.\n\n"
                f"• *🧠 Planificación (`plan`):* Antigravity analiza la arquitectura, crea `implementation_plan.md` en el cerebro y espera tu aprobación antes de modificar código.\n\n"
                f"💡 *Tip Pro:* ¡No necesitas cambiar de modo permanentemente! Escribe `/plan <tu tarea>` en cualquier momento para activar el planificador al vuelo."
            )
            await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        elif data == "btn_status":
            await show_status_view(query)
            return

        elif data == "btn_help":
            await cmd_help(update, context)
            return

        elif data == "toggle_autopush":
            state.autopush = not state.autopush
            state.save()
            await show_status_view(query)
            return

        elif data == "btn_ci" or data == "ci_refresh":
            text, markup = build_ci_view()
            await safe_edit_message(query, text, reply_markup=markup)
            return

        elif data.startswith("ci_watch_"):
            run_id = int(data.replace("ci_watch_", ""))
            asyncio.create_task(watch_ci_pipeline(context.application, query.message.chat_id, run_id))
            await safe_edit_message(
                query,
                f"👁️ *Vigilancia de CI/CD Activada*\n\n"
                f"Te avisaré automáticamente por Telegram en cuanto el pipeline `#{run_id}` finalice su despliegue."
            )
            return

        elif data.startswith("ci_logs_"):
            run_id = int(data.replace("ci_logs_", ""))
            _, fail_log = run_cmd(f"gh run view {run_id} --log-failed", timeout=30)
            if fail_log.strip():
                clean_fail = fail_log[-2200:].strip()
                await safe_edit_message(query, f"📋 *Logs de Fallo (`Run #{run_id}`):*\n```text\n{clean_fail}\n```")
            else:
                await safe_edit_message(query, f"📋 No se pudieron extraer logs de fallo para el Run #{run_id}.")
            return

        elif data == "btn_health":
            url = DEFAULT_HEALTH_URL
            if not url:
                await safe_edit_message(
                    query,
                    "ℹ️ *Healthcheck Web*\n\n"
                    "No hay ninguna URL configurada por defecto.\n"
                    "Usa `/health <url>` para comprobar una web específica (ej: `/health http://localhost:3000`).",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 Volver a Estado", callback_data="btn_status")]])
                )
                return
            res = check_web_health(url)
            status_line = f"🟢 ONLINE (`HTTP {res['code']} OK` en {res['ms']} ms)" if res["ok"] else f"🔴 ERROR (`{res.get('error')}`)"
            text = (
                f"🌐 *Web Healthcheck:* {status_line}\n"
                f"──────────────────────────────\n"
                f"🔗 *URL:* `{url}`\n"
                f"🔒 *Seguridad:* HTTPS / SSL Verificado\n"
            )
            kb = [
                [
                    InlineKeyboardButton("🔄 Probar de nuevo", callback_data=f"health_check_{url}"),
                    InlineKeyboardButton("🚀 Ver CI/CD", callback_data="btn_ci"),
                ],
                [
                    InlineKeyboardButton("📊 Volver a Estado", callback_data="btn_status"),
                ]
            ]
            await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb))
            return

        elif data.startswith("health_check_"):
            url = data.replace("health_check_", "")
            res = check_web_health(url)
            status_line = f"🟢 ONLINE (`HTTP {res['code']} OK` en {res['ms']} ms)" if res["ok"] else f"🔴 ERROR (`{res.get('error')}`)"
            text = (
                f"🌐 *Web Healthcheck:* {status_line}\n"
                f"──────────────────────────────\n"
                f"🔗 *URL:* `{url}`\n"
                f"🔒 *Seguridad:* HTTPS / SSL Verificado\n"
            )
            kb = [
                [
                    InlineKeyboardButton("🔄 Probar de nuevo", callback_data=f"health_check_{url}"),
                    InlineKeyboardButton("🚀 Ver CI/CD", callback_data="btn_ci"),
                ],
                [
                    InlineKeyboardButton("📊 Volver a Estado", callback_data="btn_status"),
                ]
            ]
            await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb))
            return

        elif data == "btn_battery":
            power = get_power_status()
            if not power:
                await safe_edit_message(query, "⚠️ No se pudo obtener información de energía.")
                return
            ac = power.get("ac")
            pct = power.get("pct", -1)
            secs = power.get("secs", -1)
            ac_label = "⚡ Enchufado a la Red (AC)" if ac == 1 else ("🔋 Batería (Desconectado)" if ac == 0 else "Desconocido")
            time_str = f"{secs // 60} minutos restantes" if secs > 0 else ("Ilimitado (Conectado a corriente)" if ac == 1 else "Calculando...")
            text = (
                f"🔋 *Monitor de Energía del Servidor (Host Remoto)*\n"

                f"──────────────────────────────\n"
                f"🔌 *Fuente:* {ac_label}\n"
                f"📊 *Nivel de Batería:* `{pct}%`\n"
                f"⏱️ *Tiempo Estimado:* `{time_str}`\n"
                f"🛡️ *Watchdog Activo:* Alerta proactiva configurada ante cortes de luz.\n"
            )
            kb = [
                [
                    InlineKeyboardButton("🔄 Refrescar", callback_data="btn_battery"),
                    InlineKeyboardButton("📊 Ver Estado", callback_data="btn_status"),
                ]
            ]
            await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(kb))
            return

        elif data == "btn_branches":
            text, markup = build_branches_view()
            await safe_edit_message(query, text, reply_markup=markup)
            return

        elif data.startswith("branch_co_"):
            target_b = data.replace("branch_co_", "")
            code, out = run_cmd(f"git checkout {target_b}")
            if code == 0:
                await safe_edit_message(query, f"🌿 *Cambiado a la rama:* `{target_b}`")
            else:
                await safe_edit_message(query, f"⚠️ Error al cambiar a la rama `{target_b}`:\n`{out}`")
            return

        # Selección de proyecto
        if data.startswith("proj_"):
            key = data.replace("proj_", "")
            selected_path = state.project_cache.get(key)
            if not selected_path or not os.path.exists(selected_path):
                await safe_edit_message(query, "⚠️ El proyecto ya no existe. Ejecuta `/projects` de nuevo.")
                return

            state.current_project = selected_path
            state.active_session_id = None
            state.active_session_title = None
            state.save()

            proj_name = os.path.basename(os.path.normpath(selected_path))
            await safe_edit_message(
                query,
                f"✅ *Proyecto fijado:* `{proj_name}`\n"
                f"📂 *Ruta:* `{selected_path}`\n\n"
                f"💬 Sesión reiniciada. Puedes usar `/sessions` para retomar un chat previo o escribir tu mensaje directamente.",
            )

        # Selección de sesión
        elif data.startswith("ses_"):
            target_sid = data.replace("ses_", "")
            if target_sid == "NEW":
                old_title = state.active_session_title or "Sesión"
                state.active_session_id = None
                state.active_session_title = None
                state.save()
                keyboard = [
                    [
                        InlineKeyboardButton("💬 Entrar a Sesión", callback_data="btn_sessions"),
                        InlineKeyboardButton("📁 Proyectos", callback_data="btn_projects"),
                        InlineKeyboardButton("📊 Ver Estado", callback_data="btn_status"),
                    ]
                ]
                await safe_edit_message(
                    query,
                    f"🚪 *Has salido de la sesión:*\n`{old_title}`\n\n"
                    f"✨ *Modo Hilo Limpio activado.*\n"
                    f"Tu próximo mensaje iniciará una conversación fresca e independiente.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                # Cargar sesión y presentar resumen enriquecido con última interacción
                await load_and_present_session(query, target_sid)

        # Selección de modelo
        elif data.startswith("model_"):
            selected_model = data.replace("model_", "")
            state.model = selected_model
            state.save()
            label = AVAILABLE_MODELS.get(selected_model, selected_model)
            if selected_model == "auto":
                desc = (
                    f"🤖 *Modelo de IA actualizado:*\n`{label}`\n\n"
                    f"🎯 *Auto-Router Activo:* Las órdenes se clasificarán automáticamente:\n"
                    f"• *Gemini 3.8 Flash Medium:* Para UI, CSS, fixes, consultas o git (ultrarrápido).\n"
                    f"• *Gemini 3.8 Flash High:* Para arquitectura, refactors y análisis profundo."
                )
            else:
                desc = f"🤖 *Modelo de IA fijado:*\n`{label}`\n\nTodas las siguientes órdenes se procesarán exclusivamente con este modelo."
            await safe_edit_message(query, desc)

        # Selección de Modo de Ejecución
        elif data.startswith("set_mode:"):
            selected_mode = data.replace("set_mode:", "")
            if selected_mode in AVAILABLE_MODES:
                state.execution_mode = selected_mode
                state.save()
                label = AVAILABLE_MODES.get(selected_mode, selected_mode)
                if selected_mode == "accept-edits":
                    desc = (
                        f"⚙️ *Modo de Ejecución Actualizado:*\n*{label}*\n\n"
                        f"⚡ *Flujo Inmediato:* Cada mensaje que envíes analizará, editará código y ejecutará directamente.\n"
                        f"💡 _Recuerda que siempre puedes forzar un plan con `/plan <tu petición>`._"
                    )
                else:
                    desc = (
                        f"⚙️ *Modo de Ejecución Actualizado:*\n*{label}*\n\n"
                        f"🧠 *Planificación Previa:* Cada mensaje que envíes generará primero un `implementation_plan.md` formal y esperará tu aprobación con el botón *Ejecutar Plan* antes de editar archivos."
                    )
                keyboard = [
                    [InlineKeyboardButton("📊 Volver a Estado", callback_data="btn_status")]
                ]
                await safe_edit_message(query, desc, reply_markup=InlineKeyboardMarkup(keyboard))

        # Acciones de Plan
        elif data == "view_plan":
            await cmd_plan(update, context)

        elif data == "view_walkthrough":
            await cmd_walkthrough(update, context)

        elif data == "stop_current_task":
            await query.answer("🛑 Cancelando tarea...", show_alert=False)
            stop_task_now()
            await safe_edit_message(query, "🛑 *Cancelando tarea...*\nSe ha enviado la orden de detención inmediata a todos los procesos.")

        elif data == "continue_task":
            if not state.active_session_id:
                await safe_edit_message(query, "⚠️ No hay una sesión activa para continuar. Selecciona una con `/sessions`.")
                return
            await safe_edit_message(
                query,
                "▶️ *Continuando tarea...*\n"
                "Retomando la sesión exactamente donde quedó, sin repetir trabajo..."
            )
            await execute_antigravity_task(update, context, CONTINUE_TASK_PROMPT)

        elif data == "exec_plan":
            if not state.active_session_id:
                await safe_edit_message(query, "⚠️ No hay una sesión activa para ejecutar el plan. Selecciona una sesión con `/sessions`.")
                return
            plan_file = find_brain_artifact(state.active_session_id, "implementation_plan.md")
            if not plan_file or not os.path.exists(plan_file):
                await safe_edit_message(query, "⚠️ La sesión activa no tiene un `implementation_plan.md` registrado para ejecutar.")
                return
            await safe_edit_message(query, "🚀 *Ejecutando Plan de Implementación...*\nEnviando aprobación y comenzando implementación...")
            prompt = (
                "El plan de implementación ha sido formalmente revisado y APROBADO por el usuario. "
                "Por favor procede de inmediato a ejecutar paso a paso todas las modificaciones de código, "
                "creación de componentes, pruebas y verificación según lo especificado en implementation_plan.md."
            )
            await execute_antigravity_task(update, context, prompt)

        # Acciones de Git
        elif data == "view_diff":
            await cmd_diff(update, context)

        elif data == "approve_push":
            await safe_edit_message(query, "🚀 *Iniciando commit y push...*")
            await do_commit_and_push(update, context)

        elif data == "revert_prompt":
            keyboard = [
                [
                    InlineKeyboardButton("⚠️ SÍ, Revertir Todo", callback_data="revert_do"),
                    InlineKeyboardButton("Cancelar", callback_data="revert_cancel"),
                ]
            ]
            await safe_edit_message(
                query,
                "⚠️ *¿Estás completamente seguro de revertir los cambios?*\n"
                "Se descartarán todas las modificaciones locales en los archivos (`git restore . && git clean -fd`).",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        elif data == "revert_do":
            run_cmd("git restore .")
            run_cmd("git clean -fd")
            await safe_edit_message(query, "🗑️ *Cambios locales revertidos por completo.* El directorio de trabajo está limpio.")

        elif data == "revert_cancel":
            await safe_edit_message(query, "Operación cancelada. Tus cambios siguen intactos.")

    except Exception as e:
        print(f"[Callback Error] {e}")
        try:
            await query.message.reply_text(f"⚠️ Error procesando acción: {e}")
        except Exception:
            pass

# =============================================================================
# MANEJADOR DE MENSAJES DE TEXTO (INTERACCIÓN CON ANTIGRAVITY)
# =============================================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if not state.current_project:
        await safe_reply_message(update.effective_message, "⚠️ No has seleccionado un proyecto. Envía `/projects` primero.")
        return

    user_text = update.message.text.strip() if update.message else ""
    if not user_text:
        return

    state.last_prompt = user_text
    await execute_antigravity_task(update, context, user_text)

# =============================================================================
# MANEJADOR GLOBAL DE ERRORES
# =============================================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"[Bot Error] Ocurrió una excepción: {context.error}")
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ *Aviso del Bot:* Ocurrió un error inesperado.\n`{str(context.error)[:200]}`",
            )
        except Exception:
            pass

# =============================================================================
# INICIALIZADOR DE LA APLICACIÓN
# =============================================================================
def main():
    print("==========================================================")
    print(" Iniciando Antigravity Telegram Mobile Command Bridge...  ")
    print(f" Usuario Autorizado ID: {MY_USER_ID}")
    print(f" Proyecto Actual: {state.current_project}")
    print(f" Modelo: {state.model}")
    print("==========================================================")

    if not BOT_TOKEN or BOT_TOKEN in ("PEGA_AQUI_TU_TOKEN_DE_BOTFATHER", "TU_TELEGRAM_BOT_TOKEN_AQUI"):
        print("==========================================================")
        print(" ERROR: No se ha configurado ANTIGRAVITY_BOT_TOKEN.")
        print(" Configura tu token en el archivo .env o en variables de entorno.")
        print(" Consulta .env.example para ver las instrucciones.")
        print("==========================================================")
        sys.exit(1)

    if not MY_USER_ID or MY_USER_ID == 0:
        print("==========================================================")
        print(" ERROR: No se ha configurado ANTIGRAVITY_USER_ID.")
        print(" Configura tu ID numérico de Telegram en el archivo .env.")
        print("==========================================================")
        sys.exit(1)

    async def post_init_hook(application):
        asyncio.create_task(power_watchdog_task(application))
        print("[Power Watchdog] Monitoreo de bateria y red electrica iniciado en segundo plano.")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init_hook).build()

    # Comandos de Ayuda
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ayuda", cmd_help))
    app.add_handler(MessageHandler(filters.Regex(r"^(\/\?|\?)$"), cmd_help))

    # Comandos de Navegación y Proyectos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("switch_project", cmd_projects))
    app.add_handler(CommandHandler("exit_project", cmd_exit_project))
    app.add_handler(CommandHandler("close_project", cmd_exit_project))

    # Comandos de Sesiones
    app.add_handler(CommandHandler("sessions", cmd_sessions))
    app.add_handler(CommandHandler("switch_session", cmd_sessions))
    app.add_handler(CommandHandler("session", cmd_direct_session))
    app.add_handler(CommandHandler("exit_session", cmd_exit_session))
    app.add_handler(CommandHandler("leave", cmd_exit_session))
    app.add_handler(CommandHandler("close_session", cmd_exit_session))
    app.add_handler(CommandHandler("new", cmd_new_session))
    app.add_handler(CommandHandler("continue", cmd_continue))
    app.add_handler(CommandHandler("continuar", cmd_continue))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("cancel", cmd_stop))
    app.add_handler(CommandHandler("detener", cmd_stop))
    app.add_handler(CommandHandler("cancelar", cmd_stop))

    # Cerebro, Modos y Artefactos
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("modos", cmd_mode))
    app.add_handler(CommandHandler("walkthrough", cmd_walkthrough))

    # Git y Código
    app.add_handler(CommandHandler("diff", cmd_diff))
    app.add_handler(CommandHandler("commit", cmd_commit))
    app.add_handler(CommandHandler("revert", lambda u, c: safe_reply_message(u.effective_message, "Para revertir usa el botón de confirmación en `/diff` o envía `/cmd git restore .`")))
    app.add_handler(CommandHandler("branches", cmd_branches))
    app.add_handler(CommandHandler("branch", cmd_branch))
    app.add_handler(CommandHandler("ramas", cmd_branches))
    app.add_handler(CommandHandler("rama", cmd_branch))

    # Super Dev, CI/CD y Automatización
    app.add_handler(CommandHandler("autopush", cmd_autopush))
    app.add_handler(CommandHandler("ci", cmd_ci))
    app.add_handler(CommandHandler("cicd", cmd_ci))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("ping", cmd_health))

    # Configuración, Batería y Terminal
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("battery", cmd_battery))
    app.add_handler(CommandHandler("power", cmd_battery))
    app.add_handler(CommandHandler("bateria", cmd_battery))
    app.add_handler(CommandHandler("models", cmd_models))
    app.add_handler(CommandHandler("cmd", cmd_custom_command))

    # Callbacks de botones
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Mensajes de texto libres para Antigravity
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Diagnóstico Multimodal (Fotos / Capturas de pantalla)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Manejador de errores
    app.add_error_handler(error_handler)

    print("Bot en línea y escuchando. Listo para recibir órdenes desde Telegram.")
    app.run_polling()

if __name__ == "__main__":
    main()
