"""HomeKit accessories that mirror Xiaomi/Dreame devices on the HAP bridge."""

from __future__ import annotations

from typing import Any, Callable

from shared.log import get_logger

log = get_logger("devices.homekit")


def add_device_accessories(
    bridge: Any,
    driver: Any,
    get_snapshots: Callable[[], list[Any]],
    run_command: Callable[[str, str, dict[str, Any]], Any],
) -> dict[str, Any]:
    """Attach Air Purifier + Vacuum accessories to an existing pyhap Bridge.

    Returns map device_id → accessory for later characteristic updates.
    """
    from pyhap.accessory import Accessory
    from pyhap.const import CATEGORY_AIR_PURIFIER, CATEGORY_FAN

    from devices.config import load_devices_file
    from devices.models import DeviceKind, DeviceSnapshot

    accessories: dict[str, Any] = {}

    class MiAirPurifier(Accessory):
        category = CATEGORY_AIR_PURIFIER

        def __init__(self, drv: Any, display_name: str, device_id: str) -> None:
            super().__init__(drv, display_name)
            self.device_id = device_id
            svc = self.add_preload_service("AirPurifier")
            self.char_active = svc.configure_char(
                "Active", setter_callback=self._set_active
            )
            self.char_current = svc.configure_char("CurrentAirPurifierState")
            self.char_target = svc.configure_char(
                "TargetAirPurifierState", setter_callback=self._set_target
            )
            try:
                aqi = self.add_preload_service("AirQualitySensor")
                self.char_aqi = aqi.configure_char("AirQuality")
                svc.add_linked_service(aqi)
            except Exception:
                self.char_aqi = None
            try:
                filt = self.add_preload_service("FilterMaintenance")
                self.char_filter = filt.configure_char("FilterChangeIndication")
            except Exception:
                self.char_filter = None

        def _set_active(self, value: int) -> None:
            action = "on" if value else "off"
            log.info("hk.purifier_set", id=self.device_id, action=action)
            run_command(self.device_id, action, {})

        def _set_target(self, value: int) -> None:
            mode = "Auto" if value == 1 else "Favorite"
            run_command(self.device_id, "set_mode", {"mode": mode})

        def apply_snapshot(self, snap: Any) -> None:
            on = bool(getattr(snap, "on", False))
            self.char_active.set_value(1 if on else 0)
            self.char_current.set_value(2 if on else 0)
            mode = (getattr(snap, "mode", None) or "").lower()
            self.char_target.set_value(1 if "auto" in mode else 0)
            if self.char_aqi is not None:
                self.char_aqi.set_value(_aqi_to_hk(getattr(snap, "aqi", None)))
            if self.char_filter is not None:
                life = getattr(snap, "filter_life_remaining", None)
                self.char_filter.set_value(1 if (life is not None and life < 5) else 0)

    class DreameVacuumAcc(Accessory):
        """Vacuum as Fanv2 Active + battery (HomeKit has no vacuum category)."""

        category = CATEGORY_FAN

        def __init__(self, drv: Any, display_name: str, device_id: str) -> None:
            super().__init__(drv, display_name)
            self.device_id = device_id
            svc = self.add_preload_service("Fanv2")
            self.char_active = svc.configure_char(
                "Active", setter_callback=self._set_active
            )
            try:
                bat = self.add_preload_service("BatteryService")
                self.char_battery = bat.configure_char("BatteryLevel")
                self.char_charging = bat.configure_char("ChargingState")
                self.char_low = bat.configure_char("StatusLowBattery")
            except Exception:
                self.char_battery = None
                self.char_charging = None
                self.char_low = None

        def _set_active(self, value: int) -> None:
            if value:
                log.info("hk.vacuum_start", id=self.device_id)
                run_command(self.device_id, "start", {})
            else:
                log.info("hk.vacuum_home", id=self.device_id)
                run_command(self.device_id, "home", {})

        def apply_snapshot(self, snap: Any) -> None:
            cleaning = bool(getattr(snap, "cleaning", False))
            self.char_active.set_value(1 if cleaning else 0)
            if self.char_battery is not None:
                batt = getattr(snap, "battery_level", None)
                if batt is not None:
                    self.char_battery.set_value(int(batt))
                    if self.char_low is not None:
                        self.char_low.set_value(1 if batt < 20 else 0)
                charging = getattr(snap, "charging", None)
                if charging is not None and self.char_charging is not None:
                    self.char_charging.set_value(1 if charging else 0)

    snaps = list(get_snapshots() or [])
    by_id: dict[str, Any] = {getattr(s, "id", None): s for s in snaps if getattr(s, "id", None)}

    try:
        for cfg in load_devices_file().devices:
            if not cfg.enabled or cfg.id in by_id:
                continue
            if cfg.kind not in (DeviceKind.AIR_PURIFIER, DeviceKind.VACUUM):
                continue
            by_id[cfg.id] = DeviceSnapshot(
                id=cfg.id,
                name=cfg.name,
                kind=cfg.kind,
                model=cfg.model,
                room=cfg.room,
                reachable=False,
            )
    except Exception as e:
        log.warning("devices.hk_config_fallback", error=str(e))

    for snap in by_id.values():
        kind = getattr(snap, "kind", None)
        kind_v = kind.value if hasattr(kind, "value") else str(kind)
        name = getattr(snap, "name", snap.id)
        if kind_v == "air_purifier":
            acc = MiAirPurifier(driver, name, snap.id)
            bridge.add_accessory(acc)
            accessories[snap.id] = acc
            try:
                acc.apply_snapshot(snap)
            except Exception:
                pass
        elif kind_v == "vacuum":
            acc = DreameVacuumAcc(driver, name, snap.id)
            bridge.add_accessory(acc)
            accessories[snap.id] = acc
            try:
                acc.apply_snapshot(snap)
            except Exception:
                pass

    log.info(
        "devices.homekit_attached",
        count=len(accessories),
        ids=list(accessories.keys()),
    )
    return accessories


def _aqi_to_hk(aqi: int | None) -> int:
    """Map numeric AQI to HomeKit AirQuality 1..5 (1=excellent … 5=poor)."""
    if aqi is None:
        return 0
    if aqi <= 50:
        return 1
    if aqi <= 100:
        return 2
    if aqi <= 150:
        return 3
    if aqi <= 200:
        return 4
    return 5


def push_snapshots_to_accessories(
    accessories: dict[str, Any], snapshots: list[Any]
) -> None:
    by_id = {getattr(s, "id", None): s for s in snapshots}
    for did, acc in accessories.items():
        snap = by_id.get(did)
        if snap is None:
            continue
        try:
            acc.apply_snapshot(snap)
        except Exception as e:
            log.warning("devices.hk_push_fail", id=did, error=str(e))
