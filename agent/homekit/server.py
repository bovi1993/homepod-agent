"""FastAPI server exposing HomeKit state and commands.

Endpoints:
  GET  /state                 — full home snapshot
  GET  /accessories           — list of accessories
  GET  /accessories/{id}      — single accessory state
  GET  /history               — recent change history
  POST /command               — execute a HomeKit command
  POST /scene                 — trigger a scene by name
  WS   /ws/state              — push home snapshots on every change
  GET  /health                — liveness check

Run via `uvicorn homekit.server:app --host 0.0.0.0 --port 51827`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.log import get_logger
from shared.types import ApiResponse, Command, HomeSnapshot

from . import commands as hk_commands
from .bridge import HomeKitBridge
from .state import StateStore

log = get_logger("homekit.server")

DEFAULT_PORT = 51827


class SceneRequest(BaseModel):
    name: str


class HomeKitServer:
    """Wraps FastAPI app + state store + bridge with shared lifecycle."""

    def __init__(
        self,
        bridge: HomeKitBridge,
        store: StateStore,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.bridge = bridge
        self.store = store
        self.port = port
        self.app = self._build_app()
        self._subscribers: set[WebSocket] = set()

    # ---- FastAPI wiring -------------------------------------------------

    def _build_app(self) -> FastAPI:
        app = FastAPI(
            title="homepod-agent homekit",
            version="0.1.0",
            description="HomeKit control layer for the agent",
        )

        @app.get("/health")
        async def health() -> dict[str, Any]:
            snap = await self.store.snapshot()
            return {
                "ok": True,
                "service": "homekit",
                "home_id": snap.home_id,
                "accessory_count": len(snap.accessories),
            }

        @app.get("/state", response_model=ApiResponse)
        async def state() -> ApiResponse:
            snap = await self.store.snapshot()
            return ApiResponse(ok=True, data=snap.model_dump())

        @app.get("/accessories", response_model=ApiResponse)
        async def accessories() -> ApiResponse:
            items = await self.store.list_accessories()
            return ApiResponse(ok=True, data=[a.model_dump() for a in items])

        @app.get("/accessories/{accessory_id}", response_model=ApiResponse)
        async def accessory(accessory_id: str) -> ApiResponse:
            item = await self.store.get(accessory_id)
            if not item:
                raise HTTPException(404, "accessory not found")
            return ApiResponse(ok=True, data=item.model_dump())

        @app.get("/history", response_model=ApiResponse)
        async def history(accessory_id: str | None = None, limit: int = 100) -> ApiResponse:
            items = await self.store.history(accessory_id=accessory_id, limit=limit)
            return ApiResponse(ok=True, data=items)

        @app.post("/command", response_model=ApiResponse)
        async def command(cmd: Command) -> ApiResponse:
            result = await hk_commands.dispatch(cmd, self.bridge)
            if not result.ok:
                raise HTTPException(400, result.error or "command failed")
            return ApiResponse(ok=True, data=result.model_dump())

        @app.post("/scene", response_model=ApiResponse)
        async def scene(req: SceneRequest) -> ApiResponse:
            cmd = Command(target_id=req.name, action="trigger_scene", args={"name": req.name})
            result = await hk_commands.dispatch(cmd, self.bridge)
            if not result.ok:
                raise HTTPException(400, result.error or "scene trigger failed")
            return ApiResponse(ok=True, data=result.model_dump())

        @app.websocket("/ws/state")
        async def ws_state(ws: WebSocket) -> None:
            await ws.accept()
            self._subscribers.add(ws)
            log.info("ws.connected", n=len(self._subscribers))
            # Send current snapshot immediately.
            snap = await self.store.snapshot()
            await ws.send_json({"type": "snapshot", "payload": snap.model_dump()})
            try:
                # The store's `subscribe` API expects a sync callable,
                # but WebSocket sends are coroutines. We poll instead.
                while True:
                    await asyncio.sleep(1.0)
                    # The store will broadcast via subscribe; we use that path.
                    await ws.send_json({"type": "heartbeat"})
            except WebSocketDisconnect:
                pass
            finally:
                self._subscribers.discard(ws)
                log.info("ws.disconnected", n=len(self._subscribers))

        # ---- internal: push to subscribers when state changes ----

        async def on_change(snap: HomeSnapshot) -> None:
            for ws in list(self._subscribers):
                try:
                    await ws.send_json({"type": "snapshot", "payload": snap.model_dump()})
                except Exception:
                    self._subscribers.discard(ws)

        # Bridge the store's sync callback into our async broadcast.
        def sync_change(snap: HomeSnapshot) -> None:
            asyncio.create_task(on_change(snap))

        self.store.subscribe(sync_change)

        @app.exception_handler(Exception)
        async def unhandled(_: Any, exc: Exception) -> JSONResponse:
            log.error("server.unhandled", error=str(exc))
            return JSONResponse(
                status_code=500,
                content=ApiResponse(ok=False, error=str(exc)).model_dump(),
            )

        return app

    async def start(self) -> None:
        """Run uvicorn programmatically."""
        import uvicorn

        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.port, log_level="info")
        server = uvicorn.Server(config)
        log.info("server.starting", port=self.port)
        await server.serve()