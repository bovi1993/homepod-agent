"""Voice bridge — FastAPI service that exposes /tts for the LLM agent.

Run with: `uvicorn voice.main:app --host 0.0.0.0 --port 8765`

Endpoints:
  POST /tts        — synthesize speech and stream to a HomePod
  GET  /pods       — list discovered HomePods on the LAN
  GET  /health     — liveness check
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.log import configure_logging, get_logger
from shared.types import ApiResponse

from .discover import HomePodInfo, find_homepod, list_homepods
from .stream import say as stream_say
from .tts import synthesize

log = get_logger("voice.main")


class TtsRequest(BaseModel):
    text: str
    home_pod_room: str | None = None
    voice: str | None = None


class TtsResponse(BaseModel):
    ok: bool
    text: str
    audio_path: str | None = None
    pod: str | None = None
    error: str | None = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="homepod-agent voice",
        version="0.1.0",
        description="Voice bridge for the agent — TTS + HomePod streaming",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "voice-bridge"}

    @app.get("/pods", response_model=ApiResponse)
    async def pods() -> ApiResponse:
        pods = await list_homepods(timeout_s=3.0)
        return ApiResponse(
            ok=True,
            data=[
                {
                    "name": p.name,
                    "address": p.address,
                    "port": p.port,
                    "model": p.model,
                    "room": p.room,
                }
                for p in pods
            ],
        )

    @app.post("/tts", response_model=TtsResponse)
    async def tts(req: TtsRequest) -> TtsResponse:
        if not req.text.strip():
            raise HTTPException(400, "empty text")

        # Find target HomePod
        pod: HomePodInfo | None = None
        if req.home_pod_room:
            pod = await find_homepod(req.home_pod_room)
        if not pod:
            pod = await find_homepod()

        if not pod:
            return TtsResponse(ok=False, text=req.text, error="no HomePod found on LAN")

        # Synthesize
        wav = await synthesize(req.text, voice=req.voice)
        from .stream import stream_wav

        try:
            await stream_wav(pod, wav.audio)
        except Exception as e:
            log.error("tts.stream_failed", error=str(e))
            return TtsResponse(ok=False, text=req.text, error=str(e))

        return TtsResponse(
            ok=True,
            text=req.text,
            audio_path="/tmp/homepod-agent-voice.wav",
            pod=pod.name,
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Any, exc: Exception) -> JSONResponse:
        log.error("voice.unhandled", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ApiResponse(ok=False, error=str(exc)).model_dump(),
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    configure_logging("voice-bridge")
    port = int(os.environ.get("VOICE_PORT", "8765"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()