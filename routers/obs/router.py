from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from routers.obs import service

router = APIRouter(prefix="/obs", tags=["obs"])
templates = Jinja2Templates(directory="templates")


def _ssh_error(e: Exception):
    raise HTTPException(status_code=503, detail=str(e))


def _guard(fn):
    """Traduce los errores del service a códigos HTTP con mensaje mostrable.

    ValueError    → 400  (dato mal cargado por el usuario, o rechazo de OBS)
    LookupError   → 404  (id de programa inexistente)
    SourceInUse   → 409  (la radio está programada; el panel ofrece forzar)
    lo que quede  → 503  (no se pudo llegar a la PC de OBS)
    """
    try:
        return fn()
    except service.SourceInUse as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        _ssh_error(e)


@router.get("/panel", response_class=HTMLResponse)
def panel(request: Request):
    return templates.TemplateResponse(request=request, name="obs.html")


@router.get("/screenshot")
def screenshot():
    """Pantalla real de la PC (ffmpeg x11grab). Sirve aunque OBS esté trabado."""
    try:
        png = service.get_screenshot()
        return Response(content=png, media_type="image/png")
    except Exception as e:
        _ssh_error(e)


@router.get("/screenshot/program")
def screenshot_program():
    """Programa al aire (OBS WebSocket). Rápido y limpio; requiere OBS/WS vivo."""
    try:
        jpg = service.get_screenshot_program()
        return Response(content=jpg, media_type="image/jpeg")
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        _ssh_error(e)


@router.get("/status")
def status():
    try:
        return service.get_status()
    except Exception as e:
        _ssh_error(e)


@router.get("/diagnostico")
def diagnostico():
    try:
        return service.run_diagnostics()
    except Exception as e:
        _ssh_error(e)


@router.get("/sources")
def sources():
    try:
        return service.get_sources()
    except Exception as e:
        _ssh_error(e)


@router.post("/sources/{name}/enable")
def enable_source(name: str):
    try:
        service.set_source_enabled(name, True)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _ssh_error(e)


@router.post("/sources/{name}/disable")
def disable_source(name: str):
    try:
        service.set_source_enabled(name, False)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _ssh_error(e)


# ── Radios (fuentes de audio administrables) ───────────────────

class AudioSourceCreate(BaseModel):
    name: str
    url: str
    buffering_mb: int | None = None
    reconnect_delay_sec: int | None = None


class AudioSourceUpdate(BaseModel):
    name: str | None = None          # nuevo nombre (renombra el input en OBS)
    url: str | None = None
    buffering_mb: int | None = None
    reconnect_delay_sec: int | None = None


class StreamUrlPayload(BaseModel):
    url: str


@router.get("/sources/audio")
def audio_sources():
    """Solo las radios: los ffmpeg_source de la escena que apuntan a una URL."""
    return _guard(service.list_audio_sources)


@router.post("/sources/audio")
def create_audio_source(payload: AudioSourceCreate):
    kwargs = {k: v for k, v in
              {"buffering_mb": payload.buffering_mb,
               "reconnect_delay_sec": payload.reconnect_delay_sec}.items() if v is not None}
    return _guard(lambda: service.create_audio_source(payload.name, payload.url, **kwargs))


@router.post("/sources/audio/test")
def test_audio_source(payload: StreamUrlPayload):
    """Prueba la URL con ffprobe desde la PC de OBS, antes de dar de alta la radio."""
    return _guard(lambda: service.probe_stream_url(payload.url))


@router.put("/sources/audio/{name}")
def update_audio_source(name: str, payload: AudioSourceUpdate):
    return _guard(lambda: service.update_audio_source(
        name,
        url=payload.url,
        new_name=payload.name,
        buffering_mb=payload.buffering_mb,
        reconnect_delay_sec=payload.reconnect_delay_sec,
    ))


@router.delete("/sources/audio/{name}")
def delete_audio_source(name: str, force: bool = False):
    """`force=true` borra además los programas que usaban esa radio."""
    return _guard(lambda: service.delete_audio_source(name, force=force))


@router.post("/stream/start")
def start_stream():
    try:
        service.start_stream()
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)


@router.post("/stream/stop")
def stop_stream():
    try:
        service.stop_stream()
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)


@router.post("/stream/restart")
def restart_stream():
    try:
        service.restart_obs()
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)


@router.post("/camera/restart")
def restart_camera():
    try:
        service.restart_camera()
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)


@router.post("/video/heal")
def video_heal():
    """Recupera el video tras un arranque headless: fuerza el modo de pantalla si la PC
    quedó sin resolución real y mapea la ventana de la cámara si quedó sin desplegar."""
    try:
        return service.heal_video()
    except Exception as e:
        _ssh_error(e)


@router.get("/logs/{service_name}")
def get_logs(service_name: str, lines: int = 100):
    try:
        return {"logs": service.get_logs(service_name, lines)}
    except Exception as e:
        _ssh_error(e)


@router.get("/watchdog/status")
def watchdog_status():
    try:
        return service.get_watchdog_status()
    except Exception as e:
        _ssh_error(e)


@router.post("/watchdog/restart")
def watchdog_restart():
    try:
        service.restart_watchdog()
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)


@router.post("/watchdog/enable")
def watchdog_enable():
    try:
        service.enable_watchdog()
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)


@router.post("/watchdog/disable")
def watchdog_disable():
    try:
        service.disable_watchdog()
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)


@router.post("/system/reboot")
def system_reboot():
    try:
        service.reboot_pc()
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)


@router.post("/system/display_fix")
def system_display_fix():
    """Fija el modo de pantalla de forma permanente en el GRUB (fix del arranque
    headless). Toma efecto en el próximo reinicio. Requiere sudo (clave del .env)."""
    try:
        return service.apply_display_grub_fix()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _ssh_error(e)


# ── Programación / agenda ──────────────────────────────────────

class ProgramsPayload(BaseModel):
    programs: list


class ProgramPayload(BaseModel):
    name: str
    source: str
    start: str                       # "HH:MM"
    end: str                         # "HH:MM"; menor que start = cruza la medianoche
    days: list[str]                  # lu ma mi ju vi sa do


@router.get("/programs")
def get_programs():
    return _guard(service.get_programs)


@router.put("/programs")
def set_programs(payload: ProgramsPayload):
    """Reemplaza la agenda completa (la usa el guardado masivo)."""
    return _guard(lambda: {"ok": True, "programs": service.set_programs(payload.programs)})


@router.post("/programs")
def add_program(payload: ProgramPayload):
    return _guard(lambda: service.add_program(payload.model_dump()))


@router.put("/programs/{program_id}")
def update_program(program_id: str, payload: ProgramPayload):
    return _guard(lambda: service.update_program(program_id, payload.model_dump()))


@router.delete("/programs/{program_id}")
def delete_program(program_id: str):
    return _guard(lambda: service.delete_program(program_id))
