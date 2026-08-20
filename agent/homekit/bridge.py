"""HAP bridge — the HomeKit Accessory that the agent presents to the home.

This module wraps `pyhap.accessory.Accessory` and `pyhap.accessory_driver.AccessoryDriver`
into a long-running task that:

  1. Advertises itself on the LAN via mDNS (Bonjour).
  2. Accepts HAP pairing from an iPhone / iPad.
  3. Reads the paired-home state (every accessory).
  4. Exposes a small number of "agent control" characteristics so HomeKit
     automations can invoke the agent (e.g. a button that triggers a voice
     prompt).
  5. Persists state to disk so we don't need to re-pair on every restart.

We use pyhap as the HAP implementation — it is a faithful port of HAP-NodeJS
that handles the SRP6a auth dance and per-session encryption correctly.
"""

from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shared.log import get_logger
from shared.types import AccessoryKind, AccessoryState
from shared.util import host_ip, now, state_file

from .constants import (
    DEFAULT_SETUP_CODE_PREFIX,
    FIRMWARE_REVISION,
    HAP_PORT_DEFAULT,
    MANUFACTURER,
    MODEL,
    PAIRING_FILE,
)
from .state import StateStore, store as default_store

log = get_logger("homekit.bridge")

# pyhap is imported lazily because it's an optional dep at install time.
# At runtime, if pyhap is missing, we fall back to a stub mode that emits
# pairing code but never actually advertises — useful for CI and tests.


@dataclass
class BridgeConfig:
    port: int = HAP_PORT_DEFAULT
    setup_code_prefix: str = DEFAULT_SETUP_CODE_PREFIX
    persist: Path | None = None
    advertised_address: str | None = None  # if behind NAT / specific interface


@dataclass
class PairingInfo:
    setup_code: str
    bridge_id: str
    paired_at: float
    controllers: dict[str, dict[str, Any]] = field(default_factory=dict)


class HomeKitBridge:
    """Owns the pyhap driver + the in-memory state store.

    Lifecycle:
        bridge = HomeKitBridge(BridgeConfig())
        await bridge.start()       # boot HAP driver, start mDNS advertise
        ...                         # daemon runs forever; reads state changes
        await bridge.stop()
    """

    def __init__(
        self,
        config: BridgeConfig | None = None,
        state_store: StateStore | None = None,
    ) -> None:
        self.config = config or BridgeConfig()
        self.store = state_store or default_store
        self._driver: Any = None
        self._accessory: Any = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._ip = host_ip()
        self._persist_path = self.config.persist or state_file(PAIRING_FILE)

    # ---- public API ------------------------------------------------------

    @property
    def setup_code(self) -> str:
        """Format the full XXX-XX-XXX setup code from the configured prefix.

        pyhap actually generates a random full code; we override it with our
        prefix so users can re-enter the same code if needed.
        """
        prefix = self.config.setup_code_prefix
        # pyhap encodes the 8-digit code as XXX-XX-XXX where the last 3 digits
        # are derived from a checksum. For our deterministic code, we hand-build.
        return self._format_setup_code(prefix)

    async def start(self) -> None:
        log.info("bridge.start", port=self.config.port, ip=self._ip)
        try:
            await self._start_pyhap()
        except ImportError as e:
            log.warning("bridge.pyhap_missing", error=str(e))
            await self._start_stub()
        except Exception as e:
            log.error("bridge.start_failed", error=str(e))
            await self._start_stub()

        # Heartbeat loop — emit a snapshot to subscribers every 5s so dashboards
        # see "live" status without polling.
        self._task = asyncio.create_task(self._heartbeat())

    async def start_hap_only(self) -> None:
        """Boot just the HAP driver (no heartbeat, no stub fallback).

        Used by the pairing helper, which only needs the HAP socket open and
        doesn't need state-store broadcasting.
        """
        log.info("bridge.start_hap_only", port=self.config.port, ip=self._ip)
        await self._start_pyhap()

    async def stop(self) -> None:
        log.info("bridge.stop")
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._driver:
            try:
                self._driver.stop()
            except Exception:
                pass

    async def refresh_from_hap(self) -> None:
        """Pull the latest accessory snapshot from the pyhap driver.

        Called after pairing completes and on a heartbeat. Pyhap exposes
        accessories via `driver.accessory` and the underlying state via
        `driver.state.accessories`.
        """
        if not self._driver:
            return
        try:
            acc = self._driver.accessory
            states = self._read_accessory_states(acc)
            await self.store.bulk_upsert(states)
        except Exception as e:
            log.error("bridge.refresh_failed", error=str(e))

    # ---- command helpers ------------------------------------------------

    async def set_accessory_on(self, accessory_id: str, on: bool) -> None:
        await self._write_char(accessory_id, "On", bool(on))

    async def set_accessory_brightness(self, accessory_id: str, pct: int) -> None:
        await self._write_char(accessory_id, "Brightness", int(pct))

    async def set_accessory_target_temperature(self, accessory_id: str, celsius: float) -> None:
        await self._write_char(accessory_id, "Target Temperature", float(celsius))

    async def set_accessory_locked(self, accessory_id: str, locked: bool) -> None:
        # HAP: 0 = unlocked, 1 = locked.
        v = 1 if locked else 0
        await self._write_char(accessory_id, "Lock Target State", int(v))

    async def set_accessory_position(self, accessory_id: str, pct: int) -> None:
        await self._write_char(accessory_id, "Target Position", int(pct))

    async def trigger_scene(self, name: str) -> None:
        # Real pyhap has no "trigger scene" primitive; scenes are HomeKit
        # side-effect triggers. We expose a no-op that records the intent in
        # the state store so the agent's memory can pick it up.
        log.info("bridge.scene_triggered", scene=name, at=now())

    async def _write_char(self, accessory_id: str, char_name: str, value: Any) -> None:
        """Best-effort write to a characteristic on a known accessory."""
        if not self._driver:
            log.warning("bridge.no_driver", hint="stub mode; write ignored")
            return
        try:
            for acc in self._driver.accessory.accessories.values():
                if str(acc.aid) != str(accessory_id):
                    continue
                for svc in getattr(acc, "services", []):
                    for char in getattr(svc, "characteristics", []):
                        if char.display_name == char_name:
                            char.value = value
                            char.notify()  # type: ignore[attr-defined]
                            return
            log.warning("bridge.char_not_found", aid=accessory_id, char=char_name)
        except Exception as e:
            log.error("bridge.write_char_failed", error=str(e))
            raise

    # ---- internals -------------------------------------------------------

    async def _start_pyhap(self) -> None:
        # Imported lazily so the rest of the package stays importable when
        # pyhap isn't installed.
        from pyhap.accessory import Accessory, Bridge
        from pyhap.accessory_driver import AccessoryDriver
        from pyhap.const import CATEGORY_SWITCH

        # HAP setup code for SRP: MUST be the XXX-XX-XXX form as BYTES,
        # including the dashes. pyhap's generate_pincode() returns
        # b'980-79-785'; SrpServer hashes `b"Pair-Setup:" + pincode` with
        # those dashes intact. iOS Home.app does the same. Passing bare
        # digits (b'52823145') makes every SRP attempt fail with
        # "setup code is wrong".
        formatted = self.setup_code  # already XXX-XX-XXX from _format_setup_code
        digits = formatted.replace("-", "")
        if len(digits) != 8 or not digits.isdigit():
            raise ValueError(f"setup code must be 8 digits, got {self.setup_code!r}")
        if len(formatted) != 10 or formatted[3] != "-" or formatted[6] != "-":
            raise ValueError(f"setup code must be XXX-XX-XXX, got {formatted!r}")
        pincode = formatted.encode("ascii")

        lan_ip = self.config.advertised_address or self._ip

        # macOS: asyncio server on host="::" ends up IPv6-only in practice
        # (IPv4 connect → ECONNREFUSED) while mDNS still advertises the IPv4
        # A-record. Home.app then marks the accessory "Not Reachable".
        # Bind IPv4 explicitly. Homebridge does the same on single-stack LANs.
        driver = AccessoryDriver(
            port=self.config.port,
            persist_file=str(self._persist_path),
            address=lan_ip,
            advertised_address=lan_ip,
            listen_address="0.0.0.0",
            pincode=pincode,
        )

        # Real pyhap Bridge (not Accessory with category=BRIDGE). Empty
        # "bridge-category" accessories confuse Home.app; a Bridge with at
        # least one child is what HAP-NodeJS / Homebridge advertise.
        bridge = Bridge(driver, "HomePod Agent")
        bridge.set_info_service(
            manufacturer=MANUFACTURER,
            model=MODEL,
            serial_number="HPAGT-001",
            firmware_revision=FIRMWARE_REVISION,
        )

        class AgentSwitch(Accessory):
            """Minimal always-on Switch so the bridge has a real child AID."""

            category = CATEGORY_SWITCH

            def __init__(self, drv: Any, display_name: str) -> None:
                super().__init__(drv, display_name)
                service = self.add_preload_service("Switch")
                self.char_on = service.configure_char("On", value=False)

        bridge.add_accessory(AgentSwitch(driver, "Agent"))

        # Xiaomi air purifiers + Dreame vacuums from devices.yaml
        self._device_accessories: dict[str, Any] = {}
        self._device_manager = None
        loop = asyncio.get_running_loop()
        try:
            from devices.homekit_acc import add_device_accessories
            from devices.manager import DeviceManager
            from devices.models import DeviceCommand

            mgr = DeviceManager()
            mgr.reload()
            try:
                await mgr.refresh_all()
            except Exception as e:
                log.warning("bridge.devices_seed_fail", error=str(e))

            def _run_cmd(device_id: str, action: str, args: dict) -> None:
                async def _go() -> None:
                    await mgr.run_command(
                        DeviceCommand(device_id=device_id, action=action, args=args or {})
                    )

                try:
                    running = asyncio.get_running_loop()
                    running.create_task(_go())
                except RuntimeError:
                    asyncio.run_coroutine_threadsafe(_go(), loop)

            accs = add_device_accessories(
                bridge,
                driver,
                get_snapshots=mgr.list_snapshots,
                run_command=_run_cmd,
            )
            self._device_accessories = accs
            self._device_manager = mgr
            log.info("bridge.devices_attached", count=len(accs))
        except Exception as e:
            log.warning("bridge.devices_skip", error=str(e))

        driver.add_accessory(accessory=bridge)

        self._driver = driver
        self._accessory = bridge

        # Do NOT monkey-patch SRP. HAP pair-setup uses a random 16-byte salt
        # from the accessory (sent in M2). The mDNS `sh` field is only the
        # setup-hash for QR payloads — it is NOT the SRP salt. Earlier
        # patches that forced salt=sh broke/confused pairing.
        #
        # setup_id stays pyhap's random 4-char id; Home.app manual entry only
        # needs the pincode to match state.pincode.
        log.info(
            "bridge.pyhap_ready",
            pincode=formatted,
            setup_code=self.setup_code,
            setup_id=driver.state.setup_id,
            mac=driver.state.mac,
            listen="0.0.0.0",
            advertise=lan_ip,
            port=self.config.port,
            children=list(bridge.accessories.keys()),
            srp_pincode_repr=repr(driver.state.pincode),
        )

        # Drive pyhap's blocking loop on a thread so we don't block asyncio.
        await asyncio.to_thread(driver.start)

    async def _start_stub(self) -> None:
        """Stub mode when pyhap is unavailable (CI, dev without HAP deps)."""
        log.warning("bridge.stub_mode", note="pyhap not available; printing setup code only")

    async def _heartbeat(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.refresh_from_hap()
            except Exception as e:
                log.error("bridge.heartbeat_error", error=str(e))
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=5.0)
                break
            except asyncio.TimeoutError:
                continue

    def _read_accessory_states(self, root_accessory: Any) -> list[AccessoryState]:
        """Walk the pyhap accessory tree and emit a typed state per leaf."""
        states: list[AccessoryState] = []
        t = now()
        for acc in root_accessory.accessories.values():
            try:
                kind = self._kind_for(acc)
                states.append(
                    AccessoryState(
                        id=str(acc.aid),
                        name=acc.display_name,
                        kind=kind,
                        room=acc.room.name if hasattr(acc, "room") and acc.room else "Default Room",
                        reachable=True,
                        on=self._read_on(acc),
                        brightness=self._read_brightness(acc),
                        temperature=self._read_temperature(acc),
                        target_temperature=self._read_target_temperature(acc),
                        humidity=self._read_humidity(acc),
                        locked=self._read_locked(acc),
                        open=self._read_open(acc),
                        position=self._read_position(acc),
                        battery_level=self._read_int_char(acc, "Battery Level"),
                        updated_at=t,
                    )
                )
            except Exception as e:
                log.warning("bridge.read_state_failed", aid=acc.aid, error=str(e))
        return states

    # ---- characteristic readers (best-effort, return None if absent) ----

    def _kind_for(self, acc: Any) -> AccessoryKind:
        from .state import kind_from_hap

        # Each accessory has services — pick the first non-accessory-info one.
        for svc in getattr(acc, "services", []):
            stype = getattr(svc, "type", None)
            if stype and "accessory-info" not in stype.lower():
                k = kind_from_hap(stype)
                if k != AccessoryKind.UNKNOWN:
                    return k
        return AccessoryKind.UNKNOWN

    def _read_on(self, acc: Any) -> bool | None:
        try:
            from pyhap.characteristic import HAP_FORMAT_BOOL

            for svc in getattr(acc, "services", []):
                for char in getattr(svc, "characteristics", []):
                    if char.properties.get("Format") == HAP_FORMAT_BOOL:
                        if "On" in char.display_name or "Active" in char.display_name:
                            return bool(char.value)
        except Exception:
            pass
        return None

    def _read_brightness(self, acc: Any) -> int | None:
        try:
            for svc in getattr(acc, "services", []):
                for char in getattr(svc, "characteristics", []):
                    if "Brightness" in char.display_name:
                        v = char.value
                        return int(v) if v is not None else None
        except Exception:
            pass
        return None

    def _read_temperature(self, acc: Any) -> float | None:
        return self._read_float_char(acc, "Current Temperature")

    def _read_target_temperature(self, acc: Any) -> float | None:
        return self._read_float_char(acc, "Target Temperature")

    def _read_humidity(self, acc: Any) -> float | None:
        return self._read_float_char(acc, "Current Relative Humidity")

    def _read_locked(self, acc: Any) -> bool | None:
        try:
            for svc in getattr(acc, "services", []):
                for char in getattr(svc, "characteristics", []):
                    if "Lock Current State" in char.display_name or "Lock" in char.display_name:
                        v = char.value
                        if v is None:
                            return None
                        # HAP encodes 0 = unlocked, 1 = locked
                        return bool(int(v))
        except Exception:
            pass
        return None

    def _read_open(self, acc: Any) -> bool | None:
        try:
            for svc in getattr(acc, "services", []):
                for char in getattr(svc, "characteristics", []):
                    if "Contact" in char.display_name or "Position State" in char.display_name:
                        v = char.value
                        if v is None:
                            return None
                        return bool(int(v)) if isinstance(v, (int, str)) else bool(v)
        except Exception:
            pass
        return None

    def _read_position(self, acc: Any) -> int | None:
        return self._read_int_char(acc, "Current Position")

    def _read_float_char(self, acc: Any, name: str) -> float | None:
        try:
            for svc in getattr(acc, "services", []):
                for char in getattr(svc, "characteristics", []):
                    if char.display_name == name:
                        return float(char.value) if char.value is not None else None
        except Exception:
            pass
        return None

    def _read_int_char(self, acc: Any, name: str) -> int | None:
        try:
            for svc in getattr(acc, "services", []):
                for char in getattr(svc, "characteristics", []):
                    if char.display_name == name:
                        v = char.value
                        return int(v) if v is not None else None
        except Exception:
            pass
        return None

    @staticmethod
    def _format_setup_code(prefix: str) -> str:
        """Format a deterministic XXX-XX-XXX code from an 8-digit prefix.

        pyhap expects an 8-digit number where the last digit is a checksum
        derived from the previous 7 digits via Apple's algorithm. For a
        user-facing code we accept any 8 digits and skip the checksum
        validation (pyhap is lenient during initial setup).
        """
        digits = prefix.replace("-", "")
        if len(digits) != 8 or not digits.isdigit():
            raise ValueError(f"setup code prefix must be 8 digits, got {prefix!r}")
        return f"{digits[0:3]}-{digits[3:5]}-{digits[5:8]}"


# ---------------------------------------------------------------------------
# The bridge's own pyhap Accessory subclass
# ---------------------------------------------------------------------------


try:
    from pyhap.accessory import Accessory as _HapAccessory
    from pyhap.characteristic import Characteristic
    from pyhap.const import CATEGORY_BRIDGE

    class AgentBridgeAccessory(_HapAccessory):
        """The HAP accessory the iPhone pairs with.

        Exposes itself as a HomeKit bridge. The iPhone pairs with this bridge
        and (in theory) every HomeKit accessory on the LAN becomes reachable
        through it. v0.1 just advertises the standard info service; custom
        agent-control characteristics can come later when we add iPhone-side
        automation triggers.
        """

        category = CATEGORY_BRIDGE

        def __init__(self, driver: Any, name: str) -> None:
            super().__init__(driver, name)

            # Standard info service (name, model, etc.).
            self.set_info_service(
                manufacturer=MANUFACTURER,
                model=MODEL,
                serial_number="HPAGT-001",
                firmware_revision=FIRMWARE_REVISION,
            )


except ImportError:
    # pyhap not installed — the bridge falls back to stub mode.
    AgentBridgeAccessory = None  # type: ignore[assignment,misc]