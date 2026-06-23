from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from routers.obs import service

router = APIRouter(prefix="/obs", tags=["obs"])


def _ssh_error(e: Exception):
    raise HTTPException(status_code=503, detail=str(e))


@router.get("/status")
def status():
    try:
        return service.get_status()
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
