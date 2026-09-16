# Guía Maestra Antigravity Mobile Remote (Telegram Bridge)
**Control Remoto Autónomo y Seguro de Antigravity IDE/CLI desde el Celular en Movilidad (Quito)**  
*Especialmente optimizado para laptops y equipos con 8 GB RAM (Windows 10/11)*

---

## 1. Introducción y Arquitectura de la Solución

Operar una laptop en el transporte público de Quito (Trolebús, Ecovía, corredores o buses urbanos) representa un alto riesgo de asalto u oportunidad si el equipo se expone a la vista. La solución más ergonómica, discreta y segura es transformar tu celular en una **consola de mando móvil** mediante **Telegram**, mientras tu laptop o equipo principal permanece en casa u oficina: conectada a la corriente, con la tapa cerrada, refrigerada y segura.

### El Reto de los 8 GB de RAM
Una laptop con 8 GB de RAM no tiene margen para levantar herramientas pesadas de escritorio remoto (como AnyDesk, TeamViewer o RustDesk) ni instancias completas de VS Code Web en el navegador, las cuales consumen entre **1.5 GB y 3 GB** exclusivamente en interfaces gráficas de Electron y túneles WebSockets.

Esta arquitectura utiliza un **puente asíncrono en Python (`python-telegram-bot` v20+)** que consume apenas **~35 a 55 MB de RAM**. Este puente se comunica por consola con el motor nativo de **Antigravity CLI (`agy`)**, el cual comparte el mismo motor cognitivo, los mismos agentes y el mismo cerebro (`brain`) que el IDE visual, pero sin consumir recursos gráficos.

```
       [ Celular en Movilidad / Quito (Telegram) ]
                            ↕
         (Mensajes, órdenes de código, botones táctiles)
                            ↕
                 [ Servidor Telegram API ]
                            ↕
         (Long Polling seguro - sin abrir puertos ni IP pública)
                            ↕
     [ Laptop / Host Remoto en Casa (8 GB RAM - Windows 11) ]
     ┌────────────────────────────────────────────────────────┐
     │  1. Windows Background Service (pythonw.exe ~40MB)    │
     │  2. Gestor Multi-Proyecto (Workspace Switcher)         │
     │  3. Motor de Sesiones Filtradas con Títulos del IDE    │
     │  4. Sincronización Bidireccional (CLI 🔄 IDE)          │
     │  5. Aislamiento Estricto de Artefactos (Brain Sandbox) │
     │  6. Antigravity CLI (`agy` + Gemini 3.8 Flash High)    │
     │  7. Git Engine (Diff, Commit asistido por IA, Push)    │
     └────────────────────────────────────────────────────────┘
                            ↕
              [ GitHub Repository (main) ]
                            ↕
         [ GitHub Actions CI/CD Pipeline (Deploy Dev/Prod) ]
```

---

## 2. Preparación del Host / Laptop Remota (Dejarla "Activa y Despierta")


Para que el servidor local responda 24/7 sin desconexiones, Windows debe configurarse para no suspenderse con la tapa cerrada:

### A. Alimentación y Energía (Windows 11)
1. **Conectar siempre a la corriente eléctrica:** No depender de la batería; Windows aplica perfiles de ahorro agresivos que desactivan el adaptador Wi-Fi.
2. **Acción al cerrar la tapa:**
   - Presiona `Win + R`, escribe `control` y presiona Enter.
   - Ve a **Opciones de energía** > **Elegir la acción del cierre de la tapa**.
   - En *Al cerrar la tapa* (Con corriente alterna): Selecciona **"No hacer nada"**.
   - En *Plan de energía*: Haz clic en **Cambiar la configuración del plan** y configura **Poner el equipo en estado de suspensión** en **"Nunca"**. (La pantalla se puede programar para apagarse a los 3 o 5 minutos).
3. **Desactivar el ahorro de energía en la tarjeta Wi-Fi:**
   - Clic derecho en el botón de Inicio > **Administrador de dispositivos**.
   - Despliega **Adaptadores de red**, clic derecho en tu tarjeta Wi-Fi > **Propiedades**.
   - Pestaña **Administración de energía** > Desmarca: *"Permitir que el equipo apague este dispositivo para ahorrar energía"*.

### B. Keep-Alive Recomendado
- **PowerToys Awake** (herramienta oficial de Microsoft): activa el modo "Mantener despierto indefinidamente" desde la bandeja del sistema.

---

## 3. Instalación como Servicio Automático en Windows (Sin Requerir Administrador)

A diferencia de los servicios tradicionales de Windows (`services.msc`) o tareas programadas complejas que exigen elevación de privilegios de Administrador (UAC), el bot se instala en el registro de usuario (`HKCU:\Software\Microsoft\Windows\CurrentVersion\Run`) ejecutándose con `pythonw.exe`.

### Ventajas de este método:
- **100% Silencioso:** No abre ninguna ventana de consola negra ni terminal en pantalla.
- **Sin permisos de Administrador:** Se instala y desinstala limpiamente en tu cuenta de usuario.
- **Autoinicio Garantizado:** Cada vez que la laptop se reinicia o inicias sesión en Windows, el bot arranca solo.
- **Protección de Procesos:** El instalador verifica si hay tareas de código activas antes de reiniciar para evitar interrumpir compilaciones.

### Scripts de Gestión:
- **Instalar / Iniciar servicio:**
  ```powershell
  pwsh -File ".\install_bot_service.ps1"
  ```
- **Desinstalar / Detener servicio:**
  ```powershell
  pwsh -File ".\uninstall_bot_service.ps1"
  ```


---

## 4. Arquitectura de Sincronización Bidireccional (`IDE 🔄 Telegram`)

Uno de los mayores avances del sistema es que **el IDE y el Bot de Telegram comparten el mismo contexto**:

### A. Del IDE hacia Telegram (`IDE ➡️ Telegram`)
1. **Títulos Oficiales del IDE:** El bot escanea `state.vscdb` (`workspaceStorage` y `globalStorage`) para extraer los títulos oficiales asignados por el IDE (ej. *Advanced Telegram Bot Development*, *Scalability Assessment*, etc.).
2. **Filtrado Estricto por Proyecto:** El bot inspecciona el blob de metadatos de la sesión (`extract_workspace_from_db`). Si estás en un proyecto determinado (ej. `MiProyecto`), únicamente verás chats pertenecientes a ese repositorio, ocultando los de otros proyectos.
3. **Continuidad Total:** Puedes iniciar un chat en el IDE, salir de casa y retomarlo en el autobús con `/sessions`.


### B. De Telegram hacia el IDE (`Telegram ➡️ IDE`)
1. **Sincronización Inmediata (`sync_cli_to_ide`):** Cada respuesta generada desde Telegram actualiza automáticamente el archivo SQLite (`.db`) y el registro (`transcript.jsonl`) en `~/.gemini/antigravity-ide/conversations/` y `~/.gemini/antigravity-ide/brain/`.
2. **Inyección Nativa en la UI del IDE (`trajectorySummaries`):** Las sesiones nuevas creadas desde el bot se codifican e inyectan automáticamente en el buffer binario Protocol Buffers (`antigravityUnifiedStateSync.trajectorySummaries`) de `state.vscdb`. Gracias a esto, la nueva sesión aparece de inmediato en la barra lateral del IDE vinculada a su respectivo workspace.
3. **Reflejo en Código:** Todos los archivos creados o modificados por el agente se reflejan al instante en el Explorador del IDE y en el panel de Source Control (Git).
4. **Continuidad Fluida:** Al hacer clic en cualquier sesión desde el panel de chats del IDE, carga todo el historial y contexto exactamente donde lo dejaste en Telegram.

---

## 5. Aislamiento Estricto de Sesiones y Artefactos (`Brain Sandbox`)

Para evitar confusiones operativas entre tareas distintas, el sistema cuenta con reglas estrictas de encapsulamiento:

1. **Aislamiento de Planes y Walkthroughs (`find_brain_artifact`):**
   - La búsqueda de `implementation_plan.md` y `walkthrough.md` está estrictamente delimitada al ID de la sesión activa.
   - Si una sesión no tiene plan, o si te encuentras en *Modo Hilo Limpio*, el bot **jamás mostrará artefactos de sesiones anteriores**.
2. **Modo Hilo Limpio (`/exit_session` o `➕ Iniciar Hilo Limpio`):**
   - Desacopla la sesión activa.
   - Tu próximo mensaje creará una conversación totalmente nueva e independiente sin arrastrar contexto anterior.
   - La sesión que abandonaste permanece intacta en el historial de SQLite.

---

## 6. Paradigma DX: Antigravity IDE vs. `agy` CLI Autónomo (Tiempos, Autonomía y Gobernanza)

Uno de los aspectos más importantes a comprender en este entorno es la diferencia de dinámica entre el IDE de escritorio y el agente remoto:

### A. La Gran Paradoja del Tiempo (1000s vs 2 minutos)
* En el **IDE visual**, el modelo es un copiloto de *micro-turnos*: realiza 1 o 2 llamadas a herramientas, muestra el diff y se detiene a esperar tu clic.
* En el **Bot de Telegram**, `agy` corre desatendido como un *agente de misión por lote*. Al no tener un humano sentado al lado aprobando cada línea, el agente asume la responsabilidad de resolver la meta completa de punta a punta. Si al modificar código algo no compila, el agente no se detiene a quejarse: **entra en su bucle de auto-reparación**, investigando el error, modificando otros archivos y probando hasta dejar la solución operativa. Por ello, acumula 100, 300 o más de 500 pasos y toma entre 500 y 1200 segundos. Una interacción en el bot equivale a 20 o 30 turnos del IDE ejecutados sin supervisión mientras estás en movimiento.

### B. El Factor Permisos y la Proactividad del Agente
Para evitar que el bot se quede congelado esperando respuestas `[y/N]` en una terminal invisible en Windows, se ejecuta con `--dangerously-skip-permissions`. Esto le otorga al agente libertad de acción para compilar, probar e inspeccionar código de manera fluida.

### C. Gobernanza sin Castrar al Agente
Para gobernar esta autonomía sin recortar su inteligencia:
1. **Reglas de Constitución:** Define prohibiciones estrictas en el `.ai/rules/constitution.md` de tu proyecto (ej. prohibido emitir comprobantes a producción o levantar localhost).
2. **Modo Planificación (`/mode plan` o `/plan`):** Para tareas de gran envergadura, obliga al agente a diseñar la arquitectura y detenerse antes de escribir código.
3. **Prompting Acotado (*Scope-Bounded Prompting*):** Estructura tus requerimientos móviles con objetivos claros, delimitación de archivos y directivas negativas explícitas (ej. *"No intentes compilar ni levantar servidores locales"*), reduciendo misiones de 1000s a menos de 90s.
4. **Cancelación Inmediata:** Si ves que el agente se desvía, utiliza el botón `[ 🛑 Detener Tarea ]` o envía `/stop`.

> 📘 **Lecturas recomendadas:**  
> - 👉 [Guía de Paradigmas y DX: Antigravity IDE vs. agy CLI Autónomo](Guia_DX_IDE_vs_CLI_Autonomia.md)  
> - 👉 [Guía Maestra de Prompting Acotado para Agentes Autónomos (`agy`)](Guia_Prompts_Acotados_Agentes_Autonomos.md)

---

## 7. Catálogo Completo de Comandos y Teclado Táctil

El bot está diseñado para operarse al 95% mediante botones en pantalla, minimizando la necesidad de escribir en el teclado móvil:

| Comando | Acción | Teclado Interactivo / Botones |
|---|---|---|
| `/start` | Mensaje de bienvenida y comprobación de whitelist. | Botones de inicio rápido. |
| `/?` o `/help` | Ayuda contextual según el estado (proyecto, sesión o hilo limpio). | Menú completo de comandos. |
| `/projects` | Lista los repositorios Git encontrados en el equipo y permite seleccionarlos. | Botones táctiles `[ Abrir <Proyecto> ]`. |
| `/exit_project` | Desvincula el proyecto activo para cambiar de repositorio. | Lista de proyectos disponibles. |
| `/sessions` | Lista las sesiones guardadas pertenecientes al proyecto actual. | Botones táctiles `[ 📌 <Título> ]` + `[ ➕ Hilo Limpio ]`. |
| `/session <id>` | Salto directo a una sesión por su identificador único. | Carga la ficha de la sesión. |
| `/exit_session` | Sale de la sesión activa y entra en *Modo Hilo Limpio*. | `[ 💬 Entrar a Sesión ]`, `[ 📁 Proyectos ]`. |
| `/status` | Ficha en vivo de RAM libre, batería/AC, AutoPush, proyecto, sesión activa, git y botones. | `[ 🧠 Ver Plan ]`, `[ ⚡ AutoPush ]`, `[ 🚀 CI/CD ]`, `[ 🌐 Health ]`, `[ 🌿 Ramas ]`, `[ 🔋 Batería ]`. |
| `/plan [tarea]` | **Atajo Rápido:** Genera un plan de arquitectura formal para la tarea o muestra el `implementation_plan.md` activo. | `[ ▶️ Ejecutar Plan ]`, `[ 🔍 Ver Diff ]`. |
| `/mode` o `/modos` | Alterna modo de ejecución: ⚡ Directo (`accept-edits`) vs 🧠 Planificación (`plan`). | `[ ⚡ Directo ]`, `[ 🧠 Plan ]`. |
| `/walkthrough` | Muestra el informe de tareas finalizadas (`walkthrough.md`). | Documento descargable si es extenso. |
| `/diff` | Muestra los cambios de código no commiteados con formato de color diff. | `[ ✅ Commit & Push ]`, `[ 🗑️ Revertir Cambios ]`. |
| `/commit [msg]` | Realiza commit y push. Si omites el mensaje, la IA genera uno convencional. | Notificación con hash, rama remota y botón para vigilar CI/CD. |
| `/autopush` | Alterna modo Turbo AutoPush (commit & push automático tras cada orden con cambios). | `[ ⚡ AutoPush: ON/OFF ]` en `/status`. |
| `/ci` o `/cicd` | Estado en tiempo real del pipeline de GitHub Actions del proyecto. | `[ 🔄 Refrescar ]`, `[ 👁️ Vigilar Fin de Deploy ]`, `[ 📋 Ver Log de Error ]`. |
| `/health [url]` | Comprueba código HTTP (200 OK), latencia de red (ms) y SSL de la web en vivo. | `[ 🔄 Probar de nuevo ]`, `[ 🚀 Ver CI/CD ]`. |
| `/battery` | Nivel de batería, fuente (AC/Batería) y estimación de autonomía restante. | `[ 🔄 Refrescar ]`, `[ 📊 Ver Estado ]`. |
| `/branches` | Muestra las ramas Git locales recientes con botones táctiles para alternar. | Botones `[ 🔀 Cambiar a <Rama> ]`. |
| `/branch <nombre>` | Cambia a la rama indicada o la crea si no existe (`git checkout -b`). | Confirmación inmediata de rama activa. |
| `/revert` | Descarta modificaciones locales (`git restore . && git clean -fd`). | Diálogo de confirmación de seguridad. |
| `/models` | Alterna entre modelos de IA (Auto-Router, Gemini 3.8 Flash, Claude 3.7 Sonnet, etc.). | Botones de selección de modelo. |
| `/cmd <comando>` | Terminal remota para ejecutar cualquier orden (`mvnw test`, `npm run build`). | Envío inteligente con salida capturada. |
| 📸 *(Foto / Captura)* | Envía una captura de pantalla de un bug o diseño con texto explicativo. | Análisis multimodal inmediato de Antigravity. |

---

## 8. Módulos Avanzados de Automatización y Telemetría

### 🧠 Modos de Ejecución y Atajo de Planificación (`/mode` y `/plan <tarea>`)
Antigravity soporta dos modos de ejecución:
1. **⚡ Directo (`accept-edits` - Predeterminado):**
   - El agente investiga, edita archivos, ejecuta comandos y aplica los cambios inmediatamente.
   - **Consumo de tokens:** Mínimo para tareas puntuales (arreglar un bug, cambiar estilos CSS, un commit, etc.). Ideal para el trabajo diario rápido.
2. **🧠 Planificación (`plan`):**
   - El agente investiga el código a fondo, mapea dependencias, genera un `implementation_plan.md` formal en el cerebro (`~/.gemini/antigravity-ide/brain/`) y se detiene a la espera de tu aprobación sin tocar ningún archivo de código.
   - Al terminar, Telegram te presenta el resumen con el botón interactivo **[ ▶️ Ejecutar Plan ]**.
   - **Consumo de tokens y eficiencia:** Aunque la primera iteración genera un documento estructurado, en tareas complejas, refactorizaciones o migraciones **AHORRA tokens y tiempo a nivel global**. Evita el costoso ciclo de "ensayo y error" (donde un modelo sin plan edita archivos incorrectos, rompe tests y quema contexto tratando de autocorregirse).
   - **Atajo Rápido al Vuelo:** No hace falta cambiar el modo global. Simplemente escribe `/plan <tu petición>` y el bot ejecutará esa tarea específica en modo plan de inmediato.

### ⚡ Turbo AutoPush Mode (`/autopush`)
Permite un flujo de trabajo 100% manos libres en movilidad. Cuando está activado:
- Cada orden que genere modificaciones de código ejecuta automáticamente un commit con mensaje convencional generado por IA (`gemini-3.8-flash-high`) y lo envía a `origin HEAD`.
- Si el repositorio está configurado con CI/CD (GitHub Actions), los cambios entran de inmediato al pipeline de pruebas y despliegue a la nube.
- Puedes activarlo o desactivarlo en cualquier momento con `/autopush` o tocando el botón `[ ⚡ AutoPush: ON/OFF ]` en `/status`.

### 🔍 Inspección Inteligente de Código y Diff Móvil (`/diff` y `[ 🔍 Ver Diff ]`)
El comando y botón de diff cuentan con un motor dual que resuelve el problema de "árbol limpio" cuando se usan automatizaciones:
- **Detección de Archivos Nuevos:** Utiliza internamente `git add -N .` para que cualquier archivo nuevo creado por la IA aparezca en el diff y no sea ignorado como archivo no rastreado (*untracked*).
- **Soporte Transparente para Turbo AutoPush:** Cuando AutoPush está activo y commitea los cambios un segundo después de la respuesta, el árbol de trabajo queda limpio. En vez de devolver un mensaje en blanco o *"no hay cambios"*, el botón detecta este estado y extrae automáticamente los archivos y el diff exacto del **último commit** (`git show --stat HEAD` y `git show -p HEAD`).
- **Rastreo de Archivos por Sesión:** Extrae directamente de `transcript.jsonl` la lista de archivos que Antigravity ha manipulado con herramientas de edición en la sesión activa.
- **Envío Inteligente:**
  - Cambios compactos: se muestran directamente en Telegram con bloque `diff` formateado.
  - Cambios extensos: se envían como archivo adjunto `.diff` para inspeccionar con comodidad en tu lector móvil.

### 🌐 Monitoreo de URL Web (`/health`)
- Comprueba la disponibilidad en vivo de tu aplicación web (configurable mediante `ANTIGRAVITY_DEFAULT_HEALTH_URL` en `.env` o pasando cualquier URL como argumento `/health <url>`).
- Mide tiempo de respuesta en milisegundos, código HTTP y estado del servicio en tiempo real.

### 🚀 Vigilancia de Despliegue CI/CD (`/watchdeploy`)
- Tras enviar cambios con commit/push, puedes pulsar `[ 👁️ Vigilar Fin de Deploy ]`. El bot consultará periódicamente la API de GitHub Actions (`gh run list`) e informará al instante si el despliegue pasó con éxito (`success`) o si falló (`failure`).

### 🔋 Monitor de Cortes de Luz y Batería (Watchdog en Segundo Plano)
- Mediante llamadas de bajo nivel a la API Win32 de Windows (`GetSystemPowerStatus`), el bot vigila continuamente el estado de alimentación del equipo:
  - **Alerta de Corte Eléctrico:** Si la laptop se desconecta del cargador o hay un corte de luz en el domicilio, el bot te envía de inmediato una alerta de emergencia a Telegram indicando que el equipo pasó a batería y el % restante.
  - **Alerta de Energía Restaurada:** Cuando la electricidad regresa o el cargador se conecta, te notifica que la red eléctrica fue restaurada.
  - Consulta manual de autonomía con `/battery` o desde el botón `[ 🔋 Batería ]`.


### 📸 Diagnóstico Multimodal por Imagen
- Puedes enviar directamente fotos o capturas de pantalla de la interfaz o de errores visuales a Telegram acompañadas de un pie de foto (ej: *"Corrige este botón desalineado"* o *"¿Por qué sale este error en pantalla?"*).
- El bot descarga la imagen en alta resolución en la carpeta temporal local `./temp_media/` y alimenta la imagen al modelo de IA multimodal de Antigravity para su resolución.

---

## 9. Flujo de Trabajo Típico en Movilidad (Paso a Paso)

```
[ En casa antes de salir ]
 1. Asegurar laptop conectada al cargador.
 2. Verificar que el servicio esté corriendo (autostart ya activo).
 3. Cerrar la tapa de la laptop. Guardarla en lugar seguro y ventilado.

[ En el Trole / Ecovía / Bus ]
 1. Abrir Telegram desde el teléfono.
 2. Enviar `/status` para verificar RAM, batería y proyecto activo.
 3. Si quieres trabajar en otra cosa: `/projects` > Pulsar el proyecto deseado.
 4. Si quieres retomar un chat: `/sessions` > Pulsar la sesión con su título.
 5. Escribir instrucción de código o enviar captura de pantalla de un bug.
 6. El bot responde con el progreso en vivo y los archivos tocados.
 7. Si el agente generó un plan: Pulsar `[ 🧠 Ver Plan ]` > Revisar > Pulsar `[ ▶️ Ejecutar Plan ]`.
 8. Pulsar `[ 🔍 Ver Diff ]` para verificar las líneas modificadas.
 9. Si tienes AutoPush activado: Se commitea y envía automáticamente.
    Si está en modo manual: Pulsar `[ ✅ Commit ]` (la IA redacta el mensaje formal).
10. Pulsar `[ 👁️ Vigilar Fin de Deploy ]` para recibir la notificación de éxito cuando la web esté actualizada.
```

---

## 10. Robustez Técnica y Manejo de Errores

- **Motor Guiado por Pasos Activos (Zero Timeouts Arbitrarios):**  
  Eliminación de cortes fijos (como el antiguo timeout de 300s). El puente implementa un *Idle Watchdog* (`STEP_IDLE_TIMEOUT = 600s`) que monitorea `transcript.jsonl` y resetea continuamente el contador a cero cada vez que el agente cambia de paso o edita un archivo. Ofrece hasta 10 minutos completos de inactividad por paso para dar máxima holgura a compilaciones pesadas y reintentos de red.
- **Detección Proactiva de Respuesta Final del Modelo:**  
  Cuando el modelo concluye su respuesta final (`PLANNER_RESPONSE` sin llamadas a herramientas en `transcript.jsonl`) pero subprocesos hijos en segundo plano mantienen las tuberías de salida abiertas, el puente detecta la inactividad, extrae la respuesta directamente del transcript y libera el subproceso sin hacer esperar al usuario.
- **Control en Vivo y Cancelación Inmediata (`/stop`, `/cancel` y botón `[ 🛑 Detener Tarea ]`):**  
  Durante la ejecución de cualquier tarea, el mensaje de estado en vivo emitido a Telegram incluye el botón interactivo `[ 🛑 Detener / Cancelar Tarea ]`. Al presionarlo, o al enviar los comandos `/stop`, `/cancel` o `/detener`, el puente activa `TASK_CANCEL_REQUESTED` y ejecuta `kill_process_tree()` inmediatamente, cancelando el proceso de `agy` y todos sus subprocesos hijos en milisegundos sin dejar procesos fantasma ni puertos colgados en Windows.
- **Aislamiento Multi-Proyecto y Orquestación Agnóstica:**  
  El puente no asume ni hardcodea directrices de negocio específicas de ninguna aplicación. Cada proyecto conectado administra sus propias reglas de dominio, directrices de arquitectura y políticas operativas en sus archivos locales (`.ai/rules/`, `constitution.md`, `AGENTS.md`). Antigravity CLI hereda y respeta automáticamente las reglas del workspace activo al momento de la invocación remota.
- **Modo Plan Estricto con Bloqueo de Auto-Aprobación del Stop Hook:**  
  Al activar `/mode plan` o usar `/plan <tarea>`, el puente neutraliza el gancho interno de Antigravity CLI (`Stop hook blocked termination: The user has automatically approved the artifact`) que se disparaba automáticamente con `--dangerously-skip-permissions`. El agente tiene la orden tajante de detenerse obligatoriamente tras entregar `implementation_plan.md`, esperando la aprobación humana mediante el botón `[ ▶️ Ejecutar Plan ]`.
- **UX Libre de Ambigüedades en Reanudación (`code == 0` vs `code != 0`):**  
  Para erradicar la confusión sobre si una tarea terminó o sigue pendiente:
  - Si la tarea concluye con éxito (`code == 0`): Muestra `✅ Tarea Concluida con Éxito`, el estado `🏁 Completado` y el botón `[ ▶️ Continuar Tarea ]` **se oculta automáticamente**, evitando clics accidentales.
  - Si ocurre un timeout, interrupción o caída (`code != 0`): Muestra `⚠️ Tarea Interrumpida` y activa el botón **`[ ▶️ Continuar Tarea ]`** con un prompt determinístico que obliga a la IA a revisar los archivos modificados y el cerebro (`brain/`), prohibiéndole rehacer tareas ya completadas y avanzando directamente al siguiente paso pendiente.
- **Git Diff Inteligente con Fallback a HEAD:**  
  Si Turbo AutoPush o un commit previo ya enviaron los cambios al árbol de Git, el botón `[ 🔍 Ver Diff ]` no queda en blanco; realiza una inspección inmediata de `HEAD` (`git show --stat` y `git diff HEAD~1..HEAD`), permitiendo ver con precisión las líneas tocadas en esa iteración.
- **Supresión Total de Consolas en Windows (`CREATE_NO_WINDOW`):**  
  Tanto `agy` como los servidores MCP hijos (`chrome-devtools-mcp`, `antigravity-mem`) se ejecutan con banderas de supresión de ventana (`CREATE_NO_WINDOW` y `SW_HIDE`), impidiendo que aparezcan consolas de comandos vacías o parpadeantes en el escritorio.
- **Liquidación en Cascada (`kill_process_tree`):**  
  En caso de cancelación o detención por inactividad, se ejecuta `taskkill /F /T /PID` para asegurar que el proceso padre y todos sus subprocesos hijos de Node y PowerShell se cierren limpiamente sin dejar procesos huérfanos en memoria.
- **Auto-Commit Asistido por IA Blindado:**  
  La generación automática de mensajes de commit utiliza `--disable-slash-commands`, un timeout de 90s y validación estricta contra mensajes de error, haciendo un *fallback* inmediato al prompt original si la IA demora, protegiendo el historial de Git.
- **Prevención de Errores de Entidades (`Can't parse entities`):**  
  Implementación de `sanitize_telegram_markdown()` y `safe_edit_message()` / `safe_reply_message()`. Todo texto arbitrario o fragmento de código de la IA se depura para evitar fallos de parseo de Markdown. Si Telegram rechaza el formato, el bot realiza un *fallback* automático a texto plano transparente.
- **Unificación de Perfil de Almacenamiento (`--app_data_dir antigravity-ide`):**  
  Por defecto, `agy.exe` opera en el perfil `antigravity-cli`. El puente ahora inyecta `--app_data_dir antigravity-ide` en todas las ejecuciones remotas. De este modo, las conversaciones, artefactos del cerebro (`brain/`) y bases de datos SQLite (`conversations/*.db`) se escriben directamente en el mismo entorno del Antigravity IDE (`~/.gemini/antigravity-ide/`), garantizando consistencia absoluta de estado entre el bot y el entorno de escritorio.
- **Resolución de Títulos de Sesión en 4 Capas y Consulta Dual SQLite:**  
  El motor de sesiones consulta concurrentemente `antigravity-ide/conversation_summaries.db` y `antigravity-cli/conversation_summaries.db`, fusionando y deduplicando por fecha. Dado que Antigravity frecuentemente almacena el título sintético de la IA en la columna `preview` dejando `title` en blanco, el nuevo resolver `get_session_title()` evalúa en cascada: (1) `title` explícito en SQLite, (2) `preview` generado por Cascade, (3) títulos registrados en `state.vscdb` (`history.entries`), y (4) el primer requerimiento de usuario en `transcript.jsonl`. Esto erradica que `/status` o `/sessions` muestren UUIDs crudos o etiquetas genéricas, presentando siempre el nombre descriptivo del trabajo.
- **División Inteligente de Salidas Extensas (`send_smart_message`):**  
  Telegram limita los mensajes a 4096 caracteres. Respuestas largas de código o diffs extensos se dividen automáticamente: el bot envía un resumen visual en el chat y adjunta el archivo completo (`.md`, `.diff`, `.txt`) como documento descargable.
- **Permisos Desatendidos:**  
  Ejecución con `--dangerously-skip-permissions` para que las herramientas de archivo y consola de Antigravity operen de forma fluida y autónoma sin bloquearse esperando interacción humana en la laptop.

---

## 11. Estructura de Archivos del Repositorio

```text
antigravity-telegram-bridge/
├── antigravity_bridge.py               # Núcleo del puente Telegram <-> Antigravity CLI
├── install_bot_service.ps1             # Instalador de inicio automático en Windows (HKCU Run)
├── uninstall_bot_service.ps1           # Desinstalador del servicio de inicio automático
├── .env.example                        # Plantilla de variables de entorno seguras
├── .gitignore                          # Exclusión de tokens, entornos virtuales y logs
├── LICENSE                             # Licencia de código abierto MIT
├── README.md                           # Documentación principal para usuarios y desarrolladores
├── Guia_Maestra_Antigravity_Mobile_Remote.md # Manual técnico integral de arquitectura
├── Guia_DX_IDE_vs_CLI_Autonomia.md     # Guía técnica de DX, tiempos y gobernanza de autonomía
└── Guia_Prompts_Acotados_Agentes_Autonomos.md # Manual práctico de prompting acotado y directivas
```

---

## 👨‍💻 Autor y Créditos

**Gerson Javier Castellanos Niño**

- 🐙 **GitHub:** [@gersonja](https://github.com/gersonja)
- 💼 **LinkedIn:** [gersonjavier](https://www.linkedin.com/in/gersonjavier/)

---

## 📄 Licencia

Este proyecto y su documentación están protegidos bajo la [Licencia MIT](LICENSE).  
Copyright (c) 2026 Gerson Javier Castellanos Niño.

