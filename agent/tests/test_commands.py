"""Tests for the HomeKit command handlers."""

from __future__ import annotations

from typing import Any

import pytest

from homekit import commands
from shared.types import Command, CommandResult


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    async def set_accessory_on(self, aid: str, on: bool) -> None:
        self.calls.append(("set_accessory_on", aid, on))

    async def set_accessory_brightness(self, aid: str, pct: int) -> None:
        self.calls.append(("set_accessory_brightness", aid, pct))

    async def set_accessory_target_temperature(self, aid: str, celsius: float) -> None:
        self.calls.append(("set_accessory_target_temperature", aid, celsius))

    async def set_accessory_locked(self, aid: str, locked: bool) -> None:
        self.calls.append(("set_accessory_locked", aid, locked))

    async def set_accessory_position(self, aid: str, pct: int) -> None:
        self.calls.append(("set_accessory_position", aid, pct))

    async def trigger_scene(self, name: str) -> None:
        self.calls.append(("trigger_scene", name, None))

    async def refresh_from_hap(self) -> None:
        self.calls.append(("refresh_from_hap", "", None))


@pytest.mark.asyncio
async def test_set_on() -> None:
    bridge = FakeBridge()
    cmd = Command(target_id="1", action="set_on", args={"value": True})
    res: CommandResult = await commands.dispatch(cmd, bridge)  # type: ignore[arg-type]
    assert res.ok
    assert bridge.calls == [("set_accessory_on", "1", True)]


@pytest.mark.asyncio
async def test_set_brightness_bounds() -> None:
    bridge = FakeBridge()
    cmd = Command(target_id="1", action="set_brightness", args={"value": 150})
    res = await commands.dispatch(cmd, bridge)  # type: ignore[arg-type]
    assert not res.ok
    assert "0..100" in (res.error or "")


@pytest.mark.asyncio
async def test_unknown_action() -> None:
    bridge = FakeBridge()
    cmd = Command(target_id="1", action="fly_to_mars", args={})
    res = await commands.dispatch(cmd, bridge)  # type: ignore[arg-type]
    assert not res.ok
    assert "unknown" in (res.error or "")