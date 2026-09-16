# Guía de Resolución de Problemas, Diagnóstico y Rescate Operativo

> **Manual de contingencia técnica, resolución de incidencias comunes, inspección de procesos y auditoría de logs para Antigravity Telegram Mobile Bridge.**

---

## 1. Mapa Rápido de Diagnóstico (Triage en 60 Segundos)

Si algo no responde como esperas, sigue este árbol de decisión rápido:

```mermaid
flowchart TD
    A[¿El Bot de Telegram responde a /status?] -->|Sí| B[El servicio está vivo y conectado]
    A -->|No| C[Verificar proceso en Windows: pythonw.exe]
    
    B --> D[¿La tarea de código no termina o demora mucho?]
    D -->|Sí| E[Pulsar '🛑 Detener Tarea' o enviar /stop]
    E --> F[Inspeccionar transcript.jsonl de la sesión]
    
    C --> G{¿Está corriendo pythonw.exe?}
    G -->|No| H[Iniciar con install_bot_service.ps1]
    G -->|Sí| I[Revisar conexión a Internet o conflicto de token]
```

---

## 2. Escenarios Comunes y Soluciones Paso a Paso

---

### Escenario A: El Bot no responde a los comandos en Telegram

#### 1. Causa: El proceso de segundo plano se cerró
* **Diagnóstico:** Abre PowerShell en tu laptop y ejecuta:
  ```powershell
  Get-Process pythonw -ErrorAction SilentlyContinue
  ```
* **Solución:** Si no devuelve nada, el servicio no está corriendo. Inícialo con:
  ```powershell
  pwsh -File .\install_bot_service.ps1
  ```

#### 2. Causa: Conflicto de Polling de Telegram (Error 409 Conflict)
* **Diagnóstico:** Ocurre si dejaste una ventana de consola corriendo manualmente `python antigravity_bridge.py` mientras el servicio en segundo plano `pythonw.exe` también estaba activo. Dos instancias no pueden consultar el mismo bot de Telegram a la vez.
* **Solución:** Mata todas las instancias huérfanas y reinicia el servicio limpio:
  ```powershell
  Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue
  Stop-Process -Name python -Force -ErrorAction SilentlyContinue
  pwsh -File .\install_bot_service.ps1
  ```

#### 3. Causa: El ID de Telegram no está en la Whitelist
* **Diagnóstico:** Si le escribes al bot desde otra cuenta de Telegram, el bot ignora los mensajes silenciosamente por seguridad.
* **Solución:** Verifica que `ANTIGRAVITY_USER_ID` en tu archivo `.env` coincida exactamente con tu ID numérico de Telegram (puedes obtenerlo escribiendo a `@userinfobot` en Telegram).

---

### Escenario B: Una tarea de código parece congelada o demora demasiado

#### 1. Diagnóstico en Vivo desde el Celular
Mira el mensaje de progreso en tiempo real de Telegram:
* Si el texto cambia (*"📝 Editando: Service.ts"*, *"💻 Terminal: git status"*), **el agente está trabajando activamente**, no está congelado.
* Si el texto no cambia y el contador de segundos sigue subiendo, el agente podría estar esperando una red externa o ejecutando un comando de consola pesado.

#### 2. Acción Inmediata: Detención Forzada Instantánea
Pulsa el botón táctil en Telegram:
`[ 🛑 Detener / Cancelar Tarea ]`
O envía por texto:
```text
/stop
```
El bot activará el protocolo `stop_task_now()`:
1. **Terminación del Árbol de Procesos (`kill_process_tree`):** Invoca `taskkill /F /T /PID <pid>` para fulminar el proceso raíz registrado.
2. **Barrido de Procesos Huérfanos:** Ejecuta un barrido forzoso con `taskkill /F /IM agy.exe /T` para asegurar que ningún subproceso hijo o worker de Node/CLI quede colgado en segundo plano.
3. **Bloqueo Inviolable de Auto-Reintentos y AutoPush:** Marca la bandera `was_cancelled = True`, anulando de forma inmediata cualquier reintento automático por error 503 y cancelando cualquier acción de AutoPush hacia Git.

#### 3. ¿Cómo sé qué estaba haciendo el agente?
El historial completo de razonamiento y herramientas de cada sesión se guarda en:
📁 `~/.gemini/antigravity-cli/brain/<ID_SESION>/transcript.jsonl` (o `antigravity-ide/brain/`)

Puedes inspeccionar los últimos pasos ejecutados en PowerShell con:
```powershell
Get-Content "$env:USERPROFILE\.gemini\antigravity-cli\brain\<ID_SESION>\transcript.jsonl" -Tail 15
```

---

### Escenario C: Tarea Interrumpida por Inactividad (Timeout de Paso)

El puente no utiliza límites fijos arbitrarios de tiempo total, sino un **Idle Watchdog** inteligente:
* Si durante **600 segundos (10 minutos)** el agente no cambia de paso ni escribe en su registro de actividad, el vigilante asume que un proceso hijo quedó colgado y corta la tarea de forma segura.
* En Telegram recibirás:
  > ⚠️ *Tarea interrumpida por inactividad prolongada.*  
  > `[ ▶️ Continuar Tarea ]`

#### ¿Cómo reanudar sin que empiece de cero?
Simplemente pulsa el botón **`[ ▶️ Continuar Tarea ]`** (o envía `/continue`).
El bot enviará una orden determinística que instruye a la IA a:
1. Inspeccionar los archivos ya editados y los artefactos del cerebro (`brain/`).
2. Descartar las tareas que ya quedaron completas.
3. Continuar directamente con el siguiente paso pendiente.

---

### Escenario D: Error de Formato en Telegram (`Can't parse entities`)

* **Causa:** Antigravity devuelve código con caracteres especiales (`_`, `*`, `[`, `` ` ``) que a veces rompen el parser de Markdown de Telegram.
* **Solución Automática Integrada:** El puente implementa `safe_reply_message()` y `safe_edit_message()`. Si Telegram rechaza el formato Markdown, el bot realiza un **fallback automático instantáneo a texto plano**, garantizando que nunca te quedes sin recibir la respuesta.

---

### Escenario E: Desconexión de Red o Corte de Energía en el Host

* **Si la laptop se desconecta del cargador o hay un corte de luz:**  
  El Watchdog de Batería (`ANTIGRAVITY_WATCHDOG_ENABLED=true`) detecta el cambio de estado en la API Win32 y te envía de inmediato una alerta de emergencia:
  > ⚠️ *Alerta: La laptop se desconectó de la corriente eléctrica. Batería al 85% (~3h 20m restantes).*
* **Si se restablece la energía:**  
  > 🔌 *Energía restaurada: La laptop vuelve a estar conectada a la corriente eléctrica.*
---

### Escenario F: Error 503 UNAVAILABLE (Saturación de Capacidad en Google)

* **Síntoma:** El modelo devuelve `Error: UNAVAILABLE (code 503): No capacity available for model gemini-3.8-flash-high on the server` (o `gemini-3.8-flash-medium` entra en bucle de reintento infinito).
* **Causa:** Los servidores de Google para la familia Gemini 3.8 pueden experimentar saturación global de capacidad en horas pico.
* **Mecanismo de Resiliencia del Puente:**  
  1. **Auto-Fallback a Gemini 3.7 Flash High:** Si una tarea falla con código 503 en 3.8, el puente conmuta automáticamente a **`gemini-3.7-flash-high`** (probado, ultrarrápido y con 100% de disponibilidad continua).
  2. **Selección Manual Inmediata:** Desde Telegram, puedes ejecutar `/models` y elegir directamente:
     * `💡 Gemini 3.7 Flash High` (velocidad instantánea, sin colas).
     * `🧠 Claude Sonnet 4.6 (Thinking)` (máxima profundidad para arquitectura y refactors).
  3. **Auto-Router Actualizado:** En modo `auto`, el bot prioriza `gemini-3.7-flash-high` para peticiones generales y `claude-sonnet-4-6` para análisis de arquitectura pesados.

---

### Escenario G: Blindaje Anti-Commits Huérfanos en AutoPush

* **Problema:** Si tienes archivos sin guardar o modificaciones locales en el IDE visual y una tarea remota de Telegram falla o entra en timeout, ¿podría AutoPush commitear accidentalmente tu trabajo del IDE?
* **Solución de Blindaje Estricto:**  
  El puente implementa una **doble compuerta de validación** antes de cualquier commit:
  1. **Validación de Éxito (`code == 0`):** Si la tarea terminó en timeout, error 503 o fue cancelada por el usuario con `/stop`, AutoPush **se desactiva automáticamente** y notifica que los cambios locales no fueron enviados.
  2. **Validación de Archivos Propios (`get_session_modified_files`):** Si la tarea concluyó pero el agente no tocó ningún archivo de código (por ejemplo, solo analizó o diseñó un plan), AutoPush **no tocará Git**, protegiendo cualquier archivo que tú estuvieras editando manualmente en tu computadora.

---

### Escenario H: Seguimiento Dinámico de Sesiones (IDE vs CLI)

* **Problema:** Si seleccionas una sesión creada en el IDE (`~/.gemini/antigravity-ide/brain/`), `agy` CLI podría no encontrarla en su almacén local (`antigravity-cli/brain/`) y generar silenciosamente un nuevo UUID de sesión.
* **Solución de Detección Dinámica:**  
  Durante la ejecución, el puente vigila la creación de sesiones en tiempo real. Si a los 3 segundos la sesión asignada no registra actividad, el puente **detecta automáticamente la nueva sesión recién nacida en el CLI y reasigna el tracker en caliente**. De este modo, la telemetría nunca se queda congelada en *"Iniciando análisis..."* ni acumula falsos tiempos de inactividad.

---

## 3. Comandos de Mantenimiento y Auditoría en Windows

Ejecuta estos comandos en tu laptop para verificar la salud del puente:

### 1. Ver si el proceso está corriendo y cuánta memoria RAM consume
```powershell
Get-Process pythonw | Select-Object Id, ProcessName, @{Name="RAM (MB)"; Expression={[math]::round($_.WS/1MB, 2)}}
```
*(El consumo normal debe situarse entre **35 MB y 55 MB**).*

### 2. Verificar el registro de autoinicio en Windows
```powershell
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "AntigravityTelegramBridge"
```

### 3. Matar procesos huérfanos de compilación (Node / Antigravity)
Si notas la laptop lenta por pruebas antiguas:
```powershell
taskkill /F /IM agy.exe /T 2>$null
taskkill /F /IM node.exe /T 2>$null
```

---

## 4. Auditoría de Sesiones y Diagnóstico de Bases de Datos SQLite

Si alguna sesión no carga sus títulos o deseas inspeccionar el estado:

1. **Rutas oficiales de bases de datos:**
   * `~/.gemini/antigravity-ide/conversation_summaries.db` (Resúmenes e historial del IDE).
   * `~/.gemini/antigravity-ide/conversations/<ID>.db` (Mensajes detallados de cada conversación).
   * `~/.gemini/antigravity-ide/brain/<ID>/transcript.jsonl` (Traza de herramientas y pasos).

2. **Consulta rápida de últimas sesiones en SQLite (desde PowerShell con Python):**
   ```powershell
   python -c "import sqlite3, os; p = os.path.expanduser('~/.gemini/antigravity-ide/conversation_summaries.db'); c = sqlite3.connect(p).cursor(); print('\n'.join([f'{r[0]} | {r[1]}' for r in c.execute('SELECT conversation_id, title FROM conversation_summaries ORDER BY updated_at DESC LIMIT 5').fetchall()]))"
   ```

---

*Documento desarrollado como parte de la infraestructura de ingeniería de **Antigravity Telegram Mobile Bridge**.*  
*Copyright (c) 2026 Gerson Javier Castellanos Niño. Licencia MIT.*
