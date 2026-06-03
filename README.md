# Fiboxito

Agente interno de Fibox que responde mensajes de Telegram consultando Wispro.

## Requisitos

- Python 3.11+
- [Ollama](https://ollama.com) corriendo localmente con el modelo `llama3.2:3b`

## Instalación

```bash
git clone https://github.com/tu-usuario/fiboxito.git
cd fiboxito
python -m venv env
env\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Configuración

Copiá `.env.example` como `.env` y completá los valores:

```bash
copy .env.example .env
```

## Arrancar

```bash
uvicorn agent_backend:app
```

## Primer uso

Antes de arrancar, creá `whitelist.json` con tu chat_id:

```json
[TU_CHAT_ID]
```
