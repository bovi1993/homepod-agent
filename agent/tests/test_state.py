"""Tests for the state store."""

from __future__ import annotations

import pytest

from homekit.state import StateStore, kind_from_hap
from shared.types import AccessoryKind, AccessoryState


@pytest.mark.asyncio
async def test_upsert_and_snapshot() -> None:
    s = StateStore()
    s1 = AccessoryState(
        id="1",
        name="Lamp",
        kind=AccessoryKind.LIGHT,
        on=True,
        brightness=None,
        temperature=None,
        humidity=None,
        position=None,
        battery_level=None,
        updated_at=1.0,
    )
    s2 = AccessoryState(
        id="2",
        name="Door",
        kind=AccessoryKind.LOCK,
        locked=True,
        brightness=None,
        temperature=None,
        humidity=None,
        position=None,
        battery_level=None,
        updated_at=2.0,
    )
    await s.bulk_upsert([s1, s2])
    snap = await s.snapshot()
    assert snap.home_id == "pending"
    assert len(snap.accessories) == 2
    lamps = [a for a in snap.accessories if a.id == "1"]
    assert lamps[0].on is True


@pytest.mark.asyncio
async def test_history_caps() -> None:
    s = StateStore()
    for i in range(15_000):
        await s.upsert(
            AccessoryState(
                id="1",
                name="Lamp",
                kind=AccessoryKind.LIGHT,
                on=(i % 2 == 0),
                brightness=None,
                temperature=None,
                humidity=None,
                position=None,
                battery_level=None,
                updated_at=float(i),
            )
        )
    history = await s.history(accessory_id="1", limit=200)
    assert len(history) == 200
    assert history[0]["at"] == 14_900  # most recent 200


def test_kind_from_hap_light() -> None:
    assert kind_from_hap("00000040-0000-1000-8000-0026BB765291") == AccessoryKind.LIGHT


def test_kind_from_hap_unknown() -> None:
    assert kind_from_hap(None) == AccessoryKind.UNKNOWN
    assert kind_from_hap("not-a-uuid") == AccessoryKind.UNKNOWN