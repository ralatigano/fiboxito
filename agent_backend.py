# Punto de entrada legacy — el servidor arranca con: uvicorn agent_backend:app
# La lógica vive en main.py y los módulos bajo agent/, clients/, telegram/.
from main import app  # noqa: F401
