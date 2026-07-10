import io
import posixpath

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse

from . import service
from .sftp_client import NASError

router = APIRouter(prefix="/nas", tags=["nas"])


@router.get("/status")
def status():
    return JSONResponse(service.probar_conexion())


@router.get("/listar")
def listar(path: str = "."):
    try:
        return JSONResponse({"path": path, "entradas": service.listar(path)})
    except NASError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/descargar")
def descargar(path: str):
    """Trae un archivo del NAS como descarga."""
    try:
        contenido = service.leer(path)
    except NASError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre = posixpath.basename(path) or "archivo"
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post("/subir")
async def subir(archivo: UploadFile = File(...), destino: str = Form(...)):
    """Sube un archivo al NAS en la ruta `destino` (relativa a la base)."""
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    try:
        service.escribir(destino, contenido)
    except NASError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse({"ok": True, "destino": destino, "bytes": len(contenido)})
