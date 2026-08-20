"""LLM provider abstraction.

Defines a single `LLM` protocol that both the local Ollama client and the
hosted Anthropic / OpenAI clients implement. The router picks one based on
the complexity classifier.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class LlmRequest:
    system: str
    messages: list[dict[str, str]]  # {"role": ..., "content": ...}
    max_tokens: int = 1024
    temperature: float = 0.2


@dataclass
class LlmResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLM(ABC):
    """Abstract LLM client."""

    name: str = "abstract"
    model: str = ""

    @abstractmethod
    async def complete(self, req: LlmRequest) -> LlmResponse: ...

    async def stream(self, req: LlmRequest) -> AsyncIterator[str]:
        """Default non-streaming impl. Subclasses can override."""
        resp = await self.complete(req)
        yield resp.text


class OllamaLLM(LLM):
    """Local Ollama client — assumes Ollama is running on http://localhost:11434."""

    name = "ollama"

    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    async def complete(self, req: LlmRequest) -> LlmResponse:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": req.system}] + req.messages,
                    "stream": False,
                    "options": {
                        "temperature": req.temperature,
                        "num_predict": req.max_tokens,
                    },
                },
            )
            r.raise_for_status()
            data = r.json()
            return LlmResponse(
                text=data["message"]["content"],
                provider=self.name,
                model=self.model,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            )


class AnthropicLLM(LLM):
    """Hosted Anthropic Claude client."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self.model = model
        self.api_key = api_key

    async def complete(self, req: LlmRequest) -> LlmResponse:
        import httpx

        # Convert messages: separate system from the rest.
        msgs = [m for m in req.messages if m.get("role") != "system"]
        body = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "system": req.system,
            "messages": msgs,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=body,
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return LlmResponse(
                text=text,
                provider=self.name,
                model=self.model,
                input_tokens=data.get("usage", {}).get("input_tokens", 0),
                output_tokens=data.get("usage", {}).get("output_tokens", 0),
            )


class OpenAILLM(LLM):
    """Hosted OpenAI client (GPT-4o mini / full)."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self.api_key = api_key

    async def complete(self, req: LlmRequest) -> LlmResponse:
        import httpx

        msgs = [{"role": "system", "content": req.system}] + req.messages
        body = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=body,
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            choice = data["choices"][0]
            return LlmResponse(
                text=choice["message"]["content"],
                provider=self.name,
                model=self.model,
                input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                output_tokens=data.get("usage", {}).get("completion_tokens", 0),
            )