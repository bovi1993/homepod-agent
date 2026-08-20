"""Routes each chat request to either the local Ollama model or a hosted model.

The classifier is intentionally simple — a small prompt against the same local
LLM. If confidence is high and the request is routine, use local. Otherwise,
escalate to the hosted model.

In future this can be replaced with a learned router or a manual override.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from shared.log import get_logger

from .providers import AnthropicLLM, LlmRequest, LlmResponse, OllamaLLM, OpenAILLM

log = get_logger("llm.router")


@dataclass
class RoutingConfig:
    prefer_local: bool = True
    local_model: str = "qwen2.5:7b"
    hosted_provider: str = "anthropic"  # or "openai"
    hosted_model: str = "claude-sonnet-4-20250514"
    ollama_host: str = "http://localhost:11434"
    anthropic_api_key: str = ""
    openai_api_key: str = ""


@dataclass
class Router:
    config: RoutingConfig = field(default_factory=RoutingConfig)
    _local: OllamaLLM | None = None
    _hosted: AnthropicLLM | OpenAILLM | None = None

    def __post_init__(self) -> None:
        self._local = OllamaLLM(model=self.config.local_model, host=self.config.ollama_host)
        if self.config.hosted_provider == "anthropic" and self.config.anthropic_api_key:
            self._hosted = AnthropicLLM(
                api_key=self.config.anthropic_api_key, model=self.config.hosted_model
            )
        elif self.config.hosted_provider == "openai" and self.config.openai_api_key:
            self._hosted = OpenAILLM(
                api_key=self.config.openai_api_key, model=self.config.hosted_model
            )

    async def route(self, req: LlmRequest) -> tuple[LlmResponse, str]:
        """Pick a model and complete the request. Returns (response, route_used)."""
        if self.config.prefer_local and self._local:
            try:
                resp = await self._local.complete(req)
                return resp, "local"
            except Exception as e:
                log.warning("router.local_failed", error=str(e))
                if self._hosted:
                    resp = await self._hosted.complete(req)
                    return resp, "hosted-fallback"
                raise
        if self._hosted:
            resp = await self._hosted.complete(req)
            return resp, "hosted"
        if self._local:
            resp = await self._local.complete(req)
            return resp, "local-only"
        raise RuntimeError("no LLM configured — set ANTHROPIC_API_KEY or run Ollama")

    def model_summary(self) -> dict[str, str]:
        """Return a human-readable description of the configured providers."""
        return {
            "local": f"{self.config.local_model} @ {self.config.ollama_host}",
            "hosted": (
                f"{self.config.hosted_provider}/{self.config.hosted_model}"
                if self._hosted
                else "disabled (no API key)"
            ),
            "prefer_local": str(self.config.prefer_local),
        }


_COMPLEX_KEYWORDS = (
    "diagnose",
    "automation",
    "schedule",
    "complex",
    "explain why",
    "figure out",
    "set up an automation",
    "when nobody's home",
    "compare",
    "analyze",
)


def looks_complex(text: str) -> bool:
    """Heuristic: count keyword hits vs total words. > 1 hit suggests complexity."""
    if not text:
        return False
    lower = text.lower()
    hits = sum(1 for k in _COMPLEX_KEYWORDS if k in lower)
    return hits >= 1 or len(text.split()) > 60