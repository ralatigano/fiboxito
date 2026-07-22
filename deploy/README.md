# deploy/ — Arranque automático de Fiboxito en el HOST

Estos scripts hacen que Fiboxito **vuelva a operar solo** cuando el HOST
(el desktop Windows de producción) se reinicia o se inicia sesión de Windows.

## Qué hace

- **`start_fiboxito.ps1`** — Launcher. Asegura que Ollama esté sirviendo en
  `:11434` (lo levanta si hace falta), y luego lanza el backend
  (`uvicorn agent_backend:app --host 0.0.0.0 --port 8000`) desde el venv `env\`.
  Corre uvicorn en primer plano: mientras el backend viva, la tarea programada
  queda "en ejecución". Logs en `logs\autostart.log` y `logs\backend.log`.
- **`setup_autostart.ps1`** — Configuración única (correr **como Administrador**).
  Registra la Tarea Programada **"Fiboxito Autostart"** (dispara al iniciar
  sesión del usuario; reinicia el backend si se cae) y ajusta la energía para
  que el equipo **no se suspenda** estando enchufado. Es idempotente.

El mensaje de Telegram **"Fiboxito volvió a estar activo"** lo envía el propio
backend desde su `lifespan` (`main.py`) en cada arranque exitoso; se puede
silenciar con `STARTUP_NOTIFY=false` en el `.env`.

## Instalación en el HOST (una sola vez)

```powershell
cd C:\Users\User\Documents\Proyectos\Fiboxito
git pull
# PowerShell COMO ADMINISTRADOR:
powershell -ExecutionPolicy Bypass -File .\deploy\setup_autostart.ps1
```

Para probar sin reiniciar: `Start-ScheduledTask -TaskName 'Fiboxito Autostart'`.

## Encendido tras corte de luz

El arranque automático cubre el reinicio del sistema operativo. Para que el
equipo **se encienda solo cuando vuelve la corriente** tras un corte, hay que
activar en la **BIOS/UEFI** la opción *"Restore on AC Power Loss"* (o
*"AC Power Recovery" / "After Power Failure"*) y ponerla en **Power On /
Last State**. Es una opción de firmware: no se puede configurar por software.
