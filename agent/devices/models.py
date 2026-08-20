"""Device config + runtime snapshot types."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeviceKind(str, Enum):
    AIR_PURIFIER = "air_purifier"
    VACUUM = "vacuum"
    UNKNOWN = "unknown"


class DeviceConfig(BaseModel):
    """One physical device entry from devices.yaml."""

    id: str = Field(..., description="Stable id used by API / LLM / HomeKit")
    name: str
    kind: DeviceKind = DeviceKind.UNKNOWN
    model: str | None = None
    ip: str | None = None
    token: str | None = Field(None, description="32-char hex miio token")
    room: str = "Default Room"
    # cloud metadata (optional)
    did: str | None = None
    mac: str | None = None
    enabled: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


class DevicesFile(BaseModel):
    """Root of ~/.homepod-agent/devices.yaml."""

    cloud: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional Xiaomi cloud prefs (country, last sync). Never store password.",
    )
    devices: list[DeviceConfig] = Field(default_factory=list)


class DeviceSnapshot(BaseModel):
    """Live state of one device."""

    id: str
    name: str
    kind: DeviceKind
    model: str | None = None
    room: str = "Default Room"
    reachable: bool = False
    error: str | None = None
    # common
    on: bool | None = None
    battery_level: int | None = None
    # air purifier
    aqi: int | None = None
    humidity: float | None = None
    temperature: float | None = None
    mode: str | None = None
    fan_level: int | None = None
    filter_life_remaining: int | None = None
    # vacuum
    status: str | None = None
    cleaning: bool | None = None
    charging: bool | None = None
    cleaning_area: float | None = None
    cleaning_time: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    updated_at: float = 0.0


class DeviceCommand(BaseModel):
    device_id: str
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class DeviceCommandResult(BaseModel):
    ok: bool
    device_id: str
    action: str
    state: DeviceSnapshot | None = None
    error: str | None = None
