# ============================================================================
#  setup_autostart.ps1  —  Configuración única en el HOST (correr como Admin)
# ----------------------------------------------------------------------------
#  - Registra la Tarea Programada "Fiboxito Autostart" (dispara al iniciar
#    sesión del usuario y relanza start_fiboxito.ps1 si el backend se cae).
#  - Ajusta la energía para que el equipo NO se suspenda estando enchufado
#    (clave para que funcione como servidor 24/7).
#  Idempotente: se puede correr varias veces sin duplicar nada.
# ============================================================================

param([string]$TaskUser = $env:USERNAME)

$ErrorActionPreference = 'Stop'
$taskName = 'Fiboxito Autostart'
$proj     = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $proj 'deploy\start_fiboxito.ps1'

if (!(Test-Path $launcher)) { throw "No se encontró el launcher en $launcher" }

Write-Host "Registrando tarea '$taskName' para el usuario '$TaskUser'..."

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`""
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User $TaskUser
$principal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description 'Levanta Ollama + backend de Fiboxito al iniciar sesión de Windows.' | Out-Null

Write-Host "Tarea registrada."

# --- Energía: nunca suspender ni hibernar estando enchufado ----------------
Write-Host "Ajustando plan de energía (sin suspensión en corriente)..."
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /hibernate off

Write-Host "Listo. Estado de la tarea:"
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
