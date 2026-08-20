"""In-memory state store with optional SQLite persistence.

The store keeps the latest snapshot of the entire home (every accessory) plus
a rolling history of changes for the agent's long-term memory. The store is
the single source of truth for what the dashboard, the LLM agent, and the
voice bridge all read from.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from shared.types import AccessoryKind, AccessoryState, HomeSnapshot
from shared.util import now, state_file


@dataclass
class _ChangeRecord:
    at: float
    accessory_id: str
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass
class StateStore:
    """Snapshot store + change journal.

    Designed to be safe to call from multiple async tasks concurrently — all
    mutations are guarded by a single asyncio lock.
    """

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _accessories: dict[str, AccessoryState] = field(default_factory=dict)
    _home_id: str = "pending"
    _home_name: str = "Pending"
    _scenes: list[str] = field(default_factory=list)
    _history: list[_ChangeRecord] = field(default_factory=list)
    _subscribers: list[Callable[[HomeSnapshot], None]] = field(default_factory=list)

    @property
    def home_id(self) -> str:
        return self._home_id

    @property
    def home_name(self) -> str:
        return self._home_name

    async def upsert(self, state: AccessoryState) -> None:
        async with self._lock:
            existing = self._accessories.get(state.id)
            before = existing.model_dump() if existing else {}
            self._accessories[state.id] = state
            after = state.model_dump()
            self._history.append(
                _ChangeRecord(
                    at=state.updated_at,
                    accessory_id=state.id,
                    before=before,
                    after=after,
                )
            )
            # cap history at 10k entries
            if len(self._history) > 10_000:
                self._history = self._history[-10_000:]
            await self._broadcast()

    async def bulk_upsert(self, states: list[AccessoryState]) -> None:
        async with self._lock:
            for s in states:
                existing = self._accessories.get(s.id)
                if existing:
                    self._history.append(
                        _ChangeRecord(
                            at=s.updated_at,
                            accessory_id=s.id,
                            before=existing.model_dump(),
                            after=s.model_dump(),
                        )
                    )
                self._accessories[s.id] = s
            if len(self._history) > 10_000:
                self._history = self._history[-10_000:]
            await self._broadcast()

    async def set_home(self, home_id: str, name: str, scenes: list[str] | None = None) -> None:
        async with self._lock:
            self._home_id = home_id
            self._home_name = name
            if scenes is not None:
                self._scenes = scenes
            await self._broadcast()

    async def snapshot(self) -> HomeSnapshot:
        async with self._lock:
            return HomeSnapshot(
                home_id=self._home_id,
                name=self._home_name,
                accessories=list(self._accessories.values()),
                scenes=list(self._scenes),
                captured_at=now(),
            )

    async def get(self, accessory_id: str) -> AccessoryState | None:
        async with self._lock:
            return self._accessories.get(accessory_id)

    async def list_accessories(self) -> list[AccessoryState]:
        async with self._lock:
            return list(self._accessories.values())

    async def history(
        self, accessory_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        async with self._lock:
            items = self._history
            if accessory_id:
                items = [h for h in items if h.accessory_id == accessory_id]
            items = items[-limit:]
            return [
                {
                    "at": h.at,
                    "accessory_id": h.accessory_id,
                    "before": h.before,
                    "after": h.after,
                }
                for h in items
            ]

    def subscribe(self, cb: Callable[[HomeSnapshot], None]) -> None:
        """Register a callback invoked on every change."""
        self._subscribers.append(cb)

    async def _broadcast(self) -> None:
        snap = HomeSnapshot(
            home_id=self._home_id,
            name=self._home_name,
            accessories=list(self._accessories.values()),
            scenes=list(self._scenes),
            captured_at=now(),
        )
        for cb in list(self._subscribers):
            try:
                cb(snap)
            except Exception:
                # Don't let one broken subscriber block the rest.
                pass

    # ---- persistence ------------------------------------------------------

    async def save(self, path: Path | None = None) -> None:
        snap = await self.snapshot()
        target = path or state_file("snapshot.json")
        target.write_text(json.dumps(snap.model_dump(), indent=2))

    async def load(self, path: Path | None = None) -> None:
        target = path or state_file("snapshot.json")
        if not target.exists():
            return
        data = json.loads(target.read_text())
        await self.set_home(data["home_id"], data["name"], data.get("scenes", []))
        states = [AccessoryState(**a) for a in data.get("accessories", [])]
        await self.bulk_upsert(states)


# Convenience: a single shared instance for the daemon and tests.
store = StateStore()


def kind_from_hap(type_id: int | str | None) -> AccessoryKind:
    """Best-effort mapping from HAP service UUID / type int to AccessoryKind.

    HAP service type UUIDs are stable; we look up only the ones we care about.
    """
    if isinstance(type_id, str):
        type_id = type_id.upper()
    # HAP service UUIDs (always strings, regardless of input form).
    uuid_str = str(type_id).upper() if type_id is not None else ""
    table = {
        # Public HAP service UUIDs we care about (Apple-defined).
        "00000040-0000-1000-8000-0026BB765291": AccessoryKind.LIGHT,
        "00000041-0000-1000-8000-0026BB765291": AccessoryKind.OUTLET,
        "00000043-0000-1000-8000-0026BB765291": AccessoryKind.FAN,
        "00000044-0000-1000-8000-0026BB765291": AccessoryKind.THERMOSTAT,
        "00000045-0000-1000-8000-0026BB765291": AccessoryKind.THERMOSTAT,
        "0000004A-0000-1000-8000-0026BB765291": AccessoryKind.LOCK,
        "0000007E-0000-1000-8000-0026BB765291": AccessoryKind.SENSOR_MOTION,
        "00000080-0000-1000-8000-0026BB765291": AccessoryKind.SENSOR_CONTACT,
        "0000008A-0000-1000-8000-0026BB765291": AccessoryKind.THERMOSTAT,
        "00000096-0000-1000-8000-0026BB765291": AccessoryKind.WINDOW_COVERING,
        "000000A2-0000-1000-8000-0026BB765291": AccessoryKind.SPEAKER,
        "000000B7-0000-1000-8000-0026BB765291": AccessoryKind.SWITCH,
        # AirPlay / speakers
        "000000F0-0000-1000-8000-0026BB765291": AccessoryKind.SPEAKER,
    }
    return table.get(uuid_str, AccessoryKind.UNKNOWN)