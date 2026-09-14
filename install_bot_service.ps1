# =============================================================================
# INSTALADOR DE ANTIGRAVITY TELEGRAM BRIDGE (AUTOSTART WINDOWS SIN REQUERIR ADMIN)
# =============================================================================
$AppName = "AntigravityTelegramBridge"

# Determinar carpeta base de forma dinamica
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir -or -not (Test-Path (Join-Path $ScriptDir "antigravity_bridge.py"))) {
    $ScriptDir = (Get-Location).Path
}
$ScriptPath = Join-Path $ScriptDir "antigravity_bridge.py"
$WorkingDir = $ScriptDir

# Ubicar pythonw.exe (primero en PATH, luego en rutas estandar de Windows)
$PythonwCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if ($PythonwCmd) {
    $PythonwPath = $PythonwCmd.Source
} else {
    $Candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe",
        "C:\Python313\pythonw.exe",
        "C:\Python312\pythonw.exe",
        "C:\Python311\pythonw.exe"
    )
    $PythonwPath = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}


$CommandValue = "`"$PythonwPath`" `"$ScriptPath`""

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Configurando Inicio Automático de Antigravity Bridge...  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Validar rutas
if (-not (Test-Path $PythonwPath)) {
    Write-Error "No se encontró pythonw.exe en $PythonwPath"
    exit 1
}

if (-not (Test-Path $ScriptPath)) {
    Write-Error "No se encontró el script en $ScriptPath"
    exit 1
}

# 2. Registrar en el inicio de sesión de Windows (HKCU Run - No requiere permisos de Administrador)
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name $AppName -Value $CommandValue
Write-Host "✅ Inicio automático registrado en Windows para tu usuario." -ForegroundColor Green

# 3. Detener instancias previas si existen (protegiendo si tiene una tarea activa)
$BridgeProcs = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe' OR Name LIKE 'py%.exe'" | `
    Where-Object { $_.CommandLine -like "*antigravity_bridge.py*" }

foreach ($p in $BridgeProcs) {
    $Children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $p.ProcessId }
    $HasAgyChild = $Children | Where-Object { $_.CommandLine -like "*agy*" -or $_.Name -like "*agy*" }
    if (-not $HasAgyChild) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "⏳ Instancia PID $($p.ProcessId) tiene una tarea agy activa. No se detendrá forzosamente." -ForegroundColor Yellow
    }
}

# 4. Iniciar el bot en segundo plano con pythonw.exe (completamente invisible)
Start-Process -FilePath $PythonwPath -ArgumentList "`"$ScriptPath`"" -WorkingDirectory $WorkingDir -WindowStyle Hidden
Start-Sleep -Seconds 2

# 5. Verificar proceso activo
$Running = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe' OR Name LIKE 'py%.exe'" | `
    Where-Object { $_.CommandLine -like "*antigravity_bridge.py*" }

if ($Running) {
    Write-Host "🚀 ¡El bot ya está corriendo en segundo plano! (PID: $($Running.ProcessId))" -ForegroundColor Green
    Write-Host "Arrancará automáticamente cada vez que inicies sesión en Windows." -ForegroundColor Cyan
} else {
    Write-Host "⚠️ No se detectó el proceso activo tras iniciar. Revisa si hay otra terminal escuchando." -ForegroundColor Yellow
}
