# ============================================================================
#  start_fiboxito.ps1  —  Arranque automático de Fiboxito en el HOST (Windows)
# ----------------------------------------------------------------------------
#  Lo ejecuta la Tarea Programada "Fiboxito Autostart" al iniciar sesión.
#  1) Asegura que Ollama esté sirviendo en :11434 (lo levanta si hace falta).
#  2) Lanza el backend (uvicorn) en primer plano; mientras uvicorn viva, la
#     tarea queda "en ejecución". Si uvicorn cae, la tarea la reinicia.
#  El mensaje de "Fiboxito volvió a estar activo" lo manda el propio backend
#  desde su lifespan (main.py), no este script.
# ============================================================================

$ErrorActionPreference = 'Continue'

# La raíz del repo es el directorio padre de este script (deploy\..).
$proj    = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $proj 'logs'
if (!(Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }
$log     = Join-Path $logsDir 'autostart.log'

function Log($m) {
    "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m |
        Out-File -FilePath $log -Append -Encoding utf8
}

function Test-Ollama {
    try {
        Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch { return $false }
}

Log '=== Arranque automático de Fiboxito ==='

# --- 1) Ollama ------------------------------------------------------------
if (Test-Ollama) {
    Log 'Ollama ya estaba activo en :11434.'
} else {
    Log "Ollama no responde. Lanzando 'ollama serve'..."
    $ollamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $ollamaExe) {
        Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden
    } else {
        # Fallback: confiar en que 'ollama' esté en el PATH.
        Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden
    }
    $up = $false
    for ($i = 0; $i -lt 20; $i++) {   # esperar hasta ~40s
        Start-Sleep -Seconds 2
        if (Test-Ollama) { $up = $true; break }
    }
    Log ("Ollama activo = {0}" -f $up)
}

# --- 2) Backend (uvicorn) -------------------------------------------------
# Evitar doble instancia: si algo ya escucha en :8000, no relanzar.
$backendUp = $false
try {
    $tcp = Test-NetConnection -ComputerName localhost -Port 8000 -WarningAction SilentlyContinue
    $backendUp = $tcp.TcpTestSucceeded
} catch {}
if ($backendUp) {
    Log 'El backend ya escuchaba en :8000. No se relanza.'
    return
}

$venvPy = Join-Path $proj 'env\Scripts\python.exe'
if (!(Test-Path $venvPy)) {
    Log "ERROR: no existe el venv en $venvPy. Abortando."
    exit 1
}

Set-Location $proj
Log 'Lanzando uvicorn agent_backend:app --host 0.0.0.0 --port 8000 ...'
# En primer plano: la tarea vive mientras viva uvicorn. La salida va al log.
& $venvPy -m uvicorn agent_backend:app --host 0.0.0.0 --port 8000 *>> (Join-Path $logsDir 'backend.log')
Log ("uvicorn terminó (exit code {0})." -f $LASTEXITCODE)
