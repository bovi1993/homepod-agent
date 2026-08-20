"""FastAPI app for the LLM agent.

Endpoints:
  POST /chat              — single-turn chat (returns assistant text + tool calls)
  WS   /ws/chat           — streaming chat (server-sent events)
  WS   /ws/voice          — voice input WebSocket (iPad mic client)
  POST /memory            — add a fact to long-term memory
  GET  /memory            — list recent facts and preferences
  POST /memory/preferences — set a preference (key/value)
  GET  /health            — liveness check
  GET  /tools             — list tool schemas

Run with: `uvicorn llm.main:app --host 0.0.0.0 --port 8000`
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.log import configure_logging, get_logger
from shared.types import ApiResponse, ChatMessage, Role, ToolCall
from shared.util import request_id

from . import prompts, tools
from .memory import memory
from .providers import LlmRequest
from .router import Router, RoutingConfig, looks_complex

log = get_logger("llm.main")


@dataclass
class AgentState:
    router: Router
    memory: Any  # Memory instance


def build_router() -> Router:
    cfg = RoutingConfig(
        prefer_local=os.environ.get("PREFER_LOCAL", "1") == "1",
        local_model=os.environ.get("LOCAL_MODEL", "qwen2.5:7b"),
        ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        hosted_provider=os.environ.get("HOSTED_PROVIDER", "anthropic"),
        hosted_model=os.environ.get("HOSTED_MODEL", "claude-sonnet-4-20250514"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
    )
    return Router(cfg)


state = AgentState(router=build_router(), memory=memory)


def create_app() -> FastAPI:
    app = FastAPI(
        title="homepod-agent llm",
        version="0.1.0",
        description="LLM agent that controls HomeKit and talks through HomePod",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "llm-agent",
            "router": state.router.model_summary(),
            "memory_facts": len(memory.facts()),
        }

    @app.get("/tools", response_model=ApiResponse)
    async def tool_list() -> ApiResponse:
        return ApiResponse(ok=True, data=tools.TOOL_SCHEMAS)

    # ---- chat ----------------------------------------------------------

    class ChatTurn(BaseModel):
        user: str
        room: str | None = None  # for HomePod routing
        force_provider: str | None = None  # "local" | "hosted" override

    @app.post("/chat", response_model=ApiResponse)
    async def chat(turn: ChatTurn) -> ApiResponse:
        rid = request_id()
        log.info("chat.start", rid=rid, user=turn.user[:80])

        # Persist user message
        memory.append(ChatMessage(role=Role.USER, content=turn.user))

        # Build LLM request
        req = LlmRequest(
            system=prompts.system_prompt(),
            messages=memory.as_messages(limit=20),
            max_tokens=512,
            temperature=0.2,
        )

        # Optional provider override
        if turn.force_provider == "local":
            state.router.config.prefer_local = True
        elif turn.force_provider == "hosted":
            state.router.config.prefer_local = False

        try:
            resp, route = await state.router.route(req)
        except Exception as e:
            log.error("chat.llm_failed", rid=rid, error=str(e))
            raise HTTPException(502, f"LLM error: {e}") from e

        # Persist assistant reply
        memory.append(ChatMessage(role=Role.ASSISTANT, content=resp.text))

        log.info(
            "chat.done",
            rid=rid,
            route=route,
            in_tokens=resp.input_tokens,
            out_tokens=resp.output_tokens,
        )

        return ApiResponse(
            ok=True,
            request_id=rid,
            data={
                "reply": resp.text,
                "route": route,
                "provider": resp.provider,
                "model": resp.model,
                "tokens": {
                    "input": resp.input_tokens,
                    "output": resp.output_tokens,
                },
                "complex": looks_complex(turn.user),
            },
        )

    @app.websocket("/ws/chat")
    async def ws_chat(ws: WebSocket) -> None:
        await ws.accept()
        log.info("ws.chat.opened")
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "error": "bad json"})
                    continue
                user = payload.get("user", "").strip()
                if not user:
                    continue
                # Process like the HTTP endpoint
                memory.append(ChatMessage(role=Role.USER, content=user))
                req = LlmRequest(
                    system=prompts.system_prompt(),
                    messages=memory.as_messages(limit=20),
                    max_tokens=512,
                )
                resp, route = await state.router.route(req)
                memory.append(ChatMessage(role=Role.ASSISTANT, content=resp.text))
                await ws.send_json(
                    {
                        "type": "reply",
                        "payload": {
                            "reply": resp.text,
                            "route": route,
                        },
                    }
                )
        except WebSocketDisconnect:
            pass

    # ---- voice input (iPad mic client) ---------------------------------

    @app.websocket("/ws/voice")
    async def ws_voice(ws: WebSocket) -> None:
        """Receive audio chunks + transcripts from the iPad listen client.

        Protocol: JSON-line framed. Each message is one of:
          {"type": "transcript", "text": "...", "is_final": true|false}
          {"type": "audio", "data": "<base64>", "format": "pcm16le-16khz-mono"}
          {"type": "command", "name": "start"|"stop"|"mute"|"unmute"}
          {"type": "config", "ws_url": "...", "asr_model": "..."}
        """
        await ws.accept()
        log.info("ws.voice.opened")
        muted = False
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("type")
                if kind == "transcript":
                    if muted:
                        continue
                    text = (msg.get("text") or "").strip()
                    is_final = msg.get("is_final", False)
                    if not text or not is_final:
                        continue
                    log.info("voice.transcript", text=text[:80])
                    # Run through the chat pipeline
                    memory.append(ChatMessage(role=Role.USER, content=text))
                    req = LlmRequest(
                        system=prompts.system_prompt(),
                        messages=memory.as_messages(limit=20),
                        max_tokens=512,
                    )
                    resp, route = await state.router.route(req)
                    memory.append(ChatMessage(role=Role.ASSISTANT, content=resp.text))
                    await ws.send_json(
                        {
                            "type": "reply",
                            "payload": {
                                "reply": resp.text,
                                "route": route,
                            },
                        }
                    )
                elif kind == "command":
                    name = msg.get("name")
                    if name == "mute":
                        muted = True
                    elif name == "unmute":
                        muted = False
                    await ws.send_json({"type": "ack", "command": name})
                elif kind == "audio":
                    # Stub: a real implementation would buffer audio and
                    # run Whisper on it. For v0.1 the iPad app handles ASR
                    # locally and sends transcripts. We just no-op.
                    pass
        except WebSocketDisconnect:
            log.info("ws.voice.closed")

    # ---- memory --------------------------------------------------------

    class FactRequest(BaseModel):
        fact: str
        source: str | None = None

    @app.post("/memory", response_model=ApiResponse)
    async def memory_add(req: FactRequest) -> ApiResponse:
        memory.add_fact(req.fact, source=req.source)
        return ApiResponse(ok=True)

    @app.get("/memory", response_model=ApiResponse)
    async def memory_list() -> ApiResponse:
        return ApiResponse(
            ok=True,
            data={"facts": memory.facts(), "preferences": memory.all_prefs()},
        )

    class PrefRequest(BaseModel):
        key: str
        value: Any

    @app.post("/memory/preferences", response_model=ApiResponse)
    async def memory_pref(req: PrefRequest) -> ApiResponse:
        memory.set_pref(req.key, req.value)
        return ApiResponse(ok=True)

    @app.exception_handler(Exception)
    async def unhandled(_: Any, exc: Exception) -> JSONResponse:
        log.error("llm.unhandled", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ApiResponse(ok=False, error=str(exc)).model_dump(),
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    configure_logging("llm-agent")
    port = int(os.environ.get("LLM_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()