# =============================================================================
# DESINSTALADOR DE ANTIGRAVITY TELEGRAM BRIDGE
# =============================================================================
$AppName = "AntigravityTelegramBridge"

Write-Host "Deteniendo y eliminando inicio automático de '$AppName'..." -ForegroundColor Yellow

# 1. Detener procesos activos
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe' OR Name LIKE 'py%.exe'" | `
    Where-Object { $_.CommandLine -like "*antigravity_bridge.py*" } | `
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 2. Eliminar entrada del registro Run
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name $AppName -ErrorAction SilentlyContinue

Write-Host "✅ Inicio automático eliminado y proceso detenido correctamente." -ForegroundColor Green
