# Fiboxito — guía del proyecto

Agente interno de Fibox: un bot de Telegram (FastAPI + Ollama/Claude) que
consulta Wispro, evalúa comprobantes de pago, corta/reactiva servicio, navega
el NAS y controla el streaming de OBS.

> ⚠️ Este repositorio es **público**. Nunca commitear secretos: tokens,
> contraseñas, claves ni el `.env` (está en `.gitignore`, junto con `keys/`,
> `env/`, `logs/` y `fibox.db`). Los datos de infraestructura (equipos, IPs,
> accesos) se documentan fuera del repo.

## Arquitectura

Punto de entrada: `main.py` (app FastAPI + `lifespan` que arranca los pollers).
`agent_backend.py` es un re-export legacy (`from main import app`); el server se
levanta con `uvicorn agent_backend:app` o `uvicorn main:app`.

- `config.py` — carga `.env` (`load_dotenv`) y expone la config. Debe importarse
  antes que cualquier módulo que lea `os.getenv()`.
- `logger.py` — logging (`log_debug`, `log_error`).
- `db.py` — SQLite local (`fibox.db`, no versionado).
- `telegram/` — `polling.py` (loop de updates y comandos `/…`), `helpers.py`
  (`send_message`/`send_document`/`send_photo`), `whitelist.py`.
- `agent/` — `handler.py` (orquestación), `history.py`, `intent.py`, `prompts.py`.
- `clients/` — `wispro.py`, `ollama.py`.
- `routers/` — módulos FastAPI montados en `main.py`:
  - `obs/` — panel y control de OBS por SSH (`/obs/*`, panel en `/obs/panel`).
  - `nas/` — acceso al NAS por SFTP (`/nas`, navegación conversacional).
  - `comprobantes`, `mapa`, `opa_poller`.
- `deploy/` — arranque automático en el equipo de producción (ver su `README.md`).

## Correr en desarrollo

```bash
python -m venv env && env\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # completar valores
uvicorn agent_backend:app --host 0.0.0.0 --port 8000
```

Requiere [Ollama](https://ollama.com) corriendo (`ollama serve`) con el modelo de
`MODEL`. `DEBUG=True` desactiva el poller de comprobantes (útil en dev).

## Producción / despliegue

Dev y producción se sincronizan por **git** (push en dev → `git pull` en el
equipo de producción). El arranque automático (levantar Ollama + backend al
iniciar sesión y avisar por Telegram "volvió a estar activo") está en `deploy/`;
ver [`deploy/README.md`](deploy/README.md).

## Convenciones

- Al agregar features o fixes, actualizar `CHANGELOG.md` (en lenguaje no técnico,
  sin detalle explotable) y `manual_fiboxito.txt` (manual de uso del bot).
- Alertas/avisos a administradores: leer `TELEGRAM_ADMIN_CHAT_ID` (lista separada
  por comas) y usar `telegram.helpers.send_message`.
