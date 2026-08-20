"""Smoke test: end-to-end against a mock home.

This test exercises the full tool-call pipeline (state store → commands →
mock bridge → state store) without any real HomeKit or LLM.
"""

from __future__ import annotations

import pytest

from homekit import commands
from homekit.state import StateStore
from shared.types import AccessoryKind, AccessoryState, Command


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

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
async def test_light_on_to_off_pipeline() -> None:
    store = StateStore()
    bridge = FakeBridge()

    # Seed the store with a light.
    await store.upsert(
        AccessoryState(
            id="bedroom-light",
            name="Bedroom Light",
            kind=AccessoryKind.LIGHT,
            on=False,
            brightness=None,
            temperature=None,
            humidity=None,
            position=None,
            battery_level=None,
            updated_at=0.0,
        )
    )

    # LLM sends "turn it on"
    cmd = Command(target_id="bedroom-light", action="set_on", args={"value": True})
    res = await commands.dispatch(cmd, bridge)  # type: ignore[arg-type]
    assert res.ok
    assert bridge.calls == [("set_accessory_on", "bedroom-light", True)]

    # Simulate the HAP writeback
    await store.upsert(
        AccessoryState(
            id="bedroom-light",
            name="Bedroom Light",
            kind=AccessoryKind.LIGHT,
            on=True,
            brightness=None,
            temperature=None,
            humidity=None,
            position=None,
            battery_level=None,
            updated_at=1.0,
        )
    )
    snap = await store.snapshot()
    lamp = next(a for a in snap.accessories if a.id == "bedroom-light")
    assert lamp.on is True


@pytest.mark.asyncio
async def test_lock_then_scene() -> None:
    store = StateStore()
    bridge = FakeBridge()

    await store.bulk_upsert(
        [
            AccessoryState(
                id="front-door",
                name="Front Door",
                kind=AccessoryKind.LOCK,
                locked=True,
                brightness=None,
                temperature=None,
                humidity=None,
                position=None,
                battery_level=None,
                updated_at=0.0,
            ),
        ]
    )

    # LLM sends "lock the door and trigger bedtime"
    c1 = Command(target_id="front-door", action="set_lock", args={"value": True})
    c2 = Command(target_id="Bedtime", action="trigger_scene", args={"name": "Bedtime"})
    await commands.dispatch(c1, bridge)  # type: ignore[arg-type]
    await commands.dispatch(c2, bridge)  # type: ignore[arg-type]

    assert ("set_accessory_locked", "front-door", True) in bridge.calls
    assert ("trigger_scene", "Bedtime", None) in bridge.calls