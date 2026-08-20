"""Test fixtures: a tiny in-memory HomeKit mock for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockAccessory:
    aid: str
    name: str
    kind: str = "light"
    room: str = "Default Room"
    reachable: bool = True
    on: bool = False
    brightness: int = 0
    temperature: float = 20.0
    target_temperature: float = 21.0
    locked: bool = True
    open_pct: int = 0


@dataclass
class MockHome:
    accessories: dict[str, MockAccessory] = field(default_factory=dict)

    @classmethod
    def small(cls) -> "MockHome":
        h = cls()
        h.accessories["1"] = MockAccessory(aid="1", name="Bedroom Light", kind="light", room="Bedroom")
        h.accessories["2"] = MockAccessory(aid="2", name="Front Door", kind="lock", room="Hallway")
        h.accessories["3"] = MockAccessory(
            aid="3", name="Bedroom HomePod", kind="speaker", room="Bedroom"
        )
        return h