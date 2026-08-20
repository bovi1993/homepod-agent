"""FastAPI service that exposes the camera list + proxies HLS.

For v0.1 we don't actually re-encode RTSP; we point the dashboard at a
go2rtc instance (recommended) or a public HLS URL configured per camera.

Endpoints:
  GET  /cameras           — list configured cameras
  POST /discover          — run ONVIF discovery and persist
  GET  /health            — liveness check
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.log import configure_logging, get_logger
from shared.types import ApiResponse

from .discovery import discover_and_persist, list_cameras

log = get_logger("cameras.proxy")


def create_app() -> FastAPI:
    app = FastAPI(
        title="homepod-agent cameras",
        version="0.1.0",
        description="ONVIF discovery + RTSP/HLS proxy",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "cameras"}

    @app.get("/cameras", response_model=ApiResponse)
    async def cameras() -> ApiResponse:
        cams = await list_cameras()
        return ApiResponse(ok=True, data=[c.model_dump() for c in cams])

    @app.post("/discover", response_model=ApiResponse)
    async def discover() -> ApiResponse:
        try:
            cams = await discover_and_persist()
            return ApiResponse(ok=True, data=[c.model_dump() for c in cams])
        except Exception as e:
            log.error("cameras.discover_failed", error=str(e))
            raise HTTPException(500, str(e)) from e

    @app.exception_handler(Exception)
    async def unhandled(_: Any, exc: Exception) -> JSONResponse:
        log.error("cameras.unhandled", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ApiResponse(ok=False, error=str(exc)).model_dump(),
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    configure_logging("cameras")
    port = int(os.environ.get("CAMERAS_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()