"""FastAPI server for Xiaomi / Dreame devices.

Endpoints:
  GET  /health
  GET  /devices
  GET  /devices/{id}
  POST /devices/{id}/command
  POST /reload
  GET  /discover
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.log import get_logger
from shared.types import ApiResponse

from .manager import DeviceManager
from .models import DeviceCommand

log = get_logger("devices.server")

DEFAULT_PORT = 8002


class CommandBody(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class DevicesServer:
    def __init__(self, manager: DeviceManager, port: int = DEFAULT_PORT) -> None:
        self.manager = manager
        self.port = port
        self.app = self._build_app()

    def _build_app(self) -> FastAPI:
        app = FastAPI(
            title="homepod-agent devices",
            version="0.1.0",
            description="Xiaomi air purifier + Dreame vacuum control",
        )

        @app.get("/health")
        async def health() -> dict[str, Any]:
            snaps = self.manager.list_snapshots()
            return {
                "ok": True,
                "service": "devices",
                "device_count": len(snaps),
                "reachable": sum(1 for s in snaps if s.reachable),
            }

        @app.get("/devices", response_model=ApiResponse)
        async def list_devices() -> ApiResponse:
            snaps = self.manager.list_snapshots()
            return ApiResponse(ok=True, data=[s.model_dump() for s in snaps])

        @app.get("/devices/{device_id}", response_model=ApiResponse)
        async def get_device(device_id: str) -> ApiResponse:
            s = self.manager.get(device_id)
            if not s:
                raise HTTPException(404, f"device not found: {device_id}")
            return ApiResponse(ok=True, data=s.model_dump())

        @app.post("/devices/{device_id}/command", response_model=ApiResponse)
        async def command(device_id: str, body: CommandBody) -> ApiResponse:
            result = await self.manager.run_command(
                DeviceCommand(device_id=device_id, action=body.action, args=body.args)
            )
            if not result.ok:
                return ApiResponse(ok=False, error=result.error, data=result.model_dump())
            return ApiResponse(ok=True, data=result.model_dump())

        @app.post("/reload", response_model=ApiResponse)
        async def reload() -> ApiResponse:
            self.manager.reload()
            snaps = await self.manager.refresh_all()
            return ApiResponse(ok=True, data=[s.model_dump() for s in snaps])

        @app.get("/discover", response_model=ApiResponse)
        async def discover(timeout: float = 4.0) -> ApiResponse:
            import asyncio

            from .discover import discover_miio, discover_miio_mdns

            lan = await asyncio.to_thread(discover_miio, timeout_s=timeout)
            mdns = await asyncio.to_thread(discover_miio_mdns, timeout)
            return ApiResponse(
                ok=True,
                data={
                    "miio_udp": [
                        {
                            "ip": d.ip,
                            "device_id": d.device_id,
                            "token_hint": d.token_hint,
                        }
                        for d in lan
                    ],
                    "mdns": mdns,
                },
            )

        return app


def create_app(manager: DeviceManager | None = None) -> FastAPI:
    mgr = manager or DeviceManager()
    return DevicesServer(mgr).app
