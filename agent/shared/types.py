"""Shared types used across all homepod-agent services.

These types are deliberately framework-light — they live in `shared/` so that
homekit, llm, voice, and cameras can all import them without circular deps.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Accessory types
# ---------------------------------------------------------------------------


class AccessoryKind(str, Enum):
    LIGHT = "light"
    SWITCH = "switch"
    OUTLET = "outlet"
    THERMOSTAT = "thermostat"
    LOCK = "lock"
    DOOR = "door"
    WINDOW = "window"
    WINDOW_COVERING = "window_covering"
    FAN = "fan"
    SPEAKER = "speaker"
    TV = "tv"
    CAMERA = "camera"
    SENSOR_MOTION = "sensor_motion"
    SENSOR_CONTACT = "sensor_contact"
    SENSOR_TEMPERATURE = "sensor_temperature"
    SENSOR_HUMIDITY = "sensor_humidity"
    SENSOR_LIGHT = "sensor_light"
    UNKNOWN = "unknown"


class AccessoryState(BaseModel):
    """A snapshot of an accessory's state at a point in time."""

    id: str = Field(..., description="Stable accessory UUID from HomeKit")
    name: str
    kind: AccessoryKind = AccessoryKind.UNKNOWN
    room: str = "Default Room"
    reachable: bool = True
    on: bool | None = None
    brightness: int | None = Field(None, ge=0, le=100, description="Light brightness %")
    temperature: float | None = Field(None, description="Current temperature in °C")
    target_temperature: float | None = None
    humidity: float | None = Field(None, ge=0, le=100)
    locked: bool | None = None
    open: bool | None = None
    position: int | None = Field(None, ge=0, le=100, description="Window covering %")
    battery_level: int | None = Field(None, ge=0, le=100)
    extra: dict[str, Any] = Field(default_factory=dict)
    updated_at: float = Field(..., description="Unix epoch seconds")


class HomeSnapshot(BaseModel):
    """Full state of a home at a point in time."""

    home_id: str
    name: str
    accessories: list[AccessoryState]
    scenes: list[str] = Field(default_factory=list)
    captured_at: float = Field(..., description="Unix epoch seconds")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


class Command(BaseModel):
    """A command sent from the LLM agent to a HomeKit accessory."""

    target_id: str = Field(..., description="Accessory UUID")
    action: str = Field(..., description="e.g. set_on, set_brightness, set_target_temperature")
    args: dict[str, Any] = Field(default_factory=dict)


class CommandResult(BaseModel):
    ok: bool
    target_id: str
    action: str
    new_state: AccessoryState | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Agent messages
# ---------------------------------------------------------------------------


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessage(BaseModel):
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    timestamp: float = 0.0


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any]
    id: str | None = None


class ToolResult(BaseModel):
    ok: bool
    data: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------


class TtsRequest(BaseModel):
    text: str
    home_pod_room: str | None = Field(None, description="Room name to route to, e.g. 'Bedroom'")
    voice: str | None = None
    priority: int = 0  # higher wins when multiple are queued


# ---------------------------------------------------------------------------
# Cameras
# ---------------------------------------------------------------------------


class CameraInfo(BaseModel):
    id: str
    name: str
    rtsp_url: str
    hls_url: str | None = None
    online: bool = True
    has_motion: bool = False
    last_motion_at: float | None = None


# ---------------------------------------------------------------------------
# API envelope
# ---------------------------------------------------------------------------


class ApiResponse(BaseModel):
    """Standard envelope for all HTTP responses."""

    ok: bool = True
    data: Any = None
    error: str | None = None
    request_id: str | None = None