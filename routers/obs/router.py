from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from routers.obs import service

router = APIRouter(prefix="/obs", tags=["obs"])
templates = Jinja2Templates(directory="templates")


def _ssh_error(e: Exception):
    raise HTTPException(status_code=503, detail=str(e))


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


@router.get("/programs")
def get_programs():
    try:
        return service.get_programs()
    except Exception as e:
        _ssh_error(e)


class ProgramsPayload(BaseModel):
    programs: list


@router.put("/programs")
def set_programs(payload: ProgramsPayload):
    try:
        service.set_programs(payload.programs)
        return {"ok": True}
    except Exception as e:
        _ssh_error(e)
