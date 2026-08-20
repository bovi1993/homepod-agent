"""DeviceManager — config reload, polling, commands."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from shared.log import get_logger

from .config import load_devices_file
from .drivers import DeviceDriver, build_driver
from .models import (
    DeviceCommand,
    DeviceCommandResult,
    DeviceConfig,
    DeviceSnapshot,
)

log = get_logger("devices.manager")


class DeviceManager:
    def __init__(self, poll_interval_s: float = 30.0) -> None:
        self.poll_interval_s = poll_interval_s
        self._configs: dict[str, DeviceConfig] = {}
        self._drivers: dict[str, DeviceDriver] = {}
        self._cache: dict[str, DeviceSnapshot] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._listeners: list[Callable[[list[DeviceSnapshot]], Any]] = []

    def reload(self) -> None:
        cfg = load_devices_file()
        enabled = [d for d in cfg.devices if d.enabled]
        self._configs = {d.id: d for d in enabled}
        # drop drivers for removed devices
        for did in list(self._drivers):
            if did not in self._configs:
                self._drivers.pop(did, None)
                self._cache.pop(did, None)
        for d in enabled:
            if d.id not in self._drivers:
                try:
                    self._drivers[d.id] = build_driver(d)
                except Exception as e:
                    log.error("devices.driver_build_fail", id=d.id, error=str(e))
                    self._cache[d.id] = DeviceSnapshot(
                        id=d.id,
                        name=d.name,
                        kind=d.kind,
                        model=d.model,
                        room=d.room,
                        reachable=False,
                        error=str(e),
                        updated_at=time.time(),
                    )
        log.info("devices.reloaded", count=len(self._configs))

    def on_change(self, cb: Callable[[list[DeviceSnapshot]], Any]) -> None:
        self._listeners.append(cb)

    async def start(self) -> None:
        self.reload()
        await self.refresh_all()
        self._task = asyncio.create_task(self._poll_loop(), name="devices-poll")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.poll_interval_s)
                await self.refresh_all()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("devices.poll_error", error=str(e))

    async def refresh_all(self) -> list[DeviceSnapshot]:
        async with self._lock:
            snaps: list[DeviceSnapshot] = []
            for did, driver in list(self._drivers.items()):
                snap = await asyncio.to_thread(driver.snapshot)
                self._cache[did] = snap
                snaps.append(snap)
            # include config-only failures
            for did, cfg in self._configs.items():
                if did not in self._cache:
                    self._cache[did] = DeviceSnapshot(
                        id=cfg.id,
                        name=cfg.name,
                        kind=cfg.kind,
                        model=cfg.model,
                        room=cfg.room,
                        reachable=False,
                        error="no driver",
                        updated_at=time.time(),
                    )
                    snaps.append(self._cache[did])
            out = list(self._cache.values())
        for cb in self._listeners:
            try:
                res = cb(out)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                log.warning("devices.listener_error", error=str(e))
        return out

    def list_snapshots(self) -> list[DeviceSnapshot]:
        return list(self._cache.values())

    def get(self, device_id: str) -> DeviceSnapshot | None:
        if device_id in self._cache:
            return self._cache[device_id]
        # name match
        target = device_id.lower()
        for s in self._cache.values():
            if s.name.lower() == target or target in s.name.lower():
                return s
        return None

    async def run_command(self, cmd: DeviceCommand) -> DeviceCommandResult:
        snap = self.get(cmd.device_id)
        # resolve id from name
        device_id = cmd.device_id
        if snap:
            device_id = snap.id
        driver = self._drivers.get(device_id)
        if not driver:
            # try reload once
            self.reload()
            driver = self._drivers.get(device_id)
        if not driver:
            return DeviceCommandResult(
                ok=False,
                device_id=device_id,
                action=cmd.action,
                error=f"device not found or no driver: {cmd.device_id}",
            )
        try:
            new_state = await asyncio.to_thread(driver.command, cmd.action, cmd.args)
            self._cache[device_id] = new_state
            return DeviceCommandResult(
                ok=new_state.error is None,
                device_id=device_id,
                action=cmd.action,
                state=new_state,
                error=new_state.error,
            )
        except Exception as e:
            return DeviceCommandResult(
                ok=False, device_id=device_id, action=cmd.action, error=str(e)
            )
