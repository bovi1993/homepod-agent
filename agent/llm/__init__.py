"""llm — the LLM agent service.

Public surface:
  - main: FastAPI app + ASGI entrypoint
  - router: decides local vs hosted LLM
  - tools: HomeKit tool schema exposed to the LLM
  - memory: SQLite-backed long-term memory
  - voice_input: WebSocket endpoint for iPad mic client

Run with: `uvicorn llm.main:app --host 0.0.0.0 --port 8000`
"""

from .main import app

__all__ = ["app"]