"""Local miio drivers for Xiaomi air purifiers and Dreame vacuums."""

from __future__ import annotations

import time
from typing import Any, Protocol

from shared.log import get_logger

from .models import DeviceConfig, DeviceKind, DeviceSnapshot

log = get_logger("devices.drivers")


class DeviceDriver(Protocol):
    def snapshot(self) -> DeviceSnapshot: ...
    def command(self, action: str, args: dict[str, Any]) -> DeviceSnapshot: ...


def _base_snap(cfg: DeviceConfig, **kwargs: Any) -> DeviceSnapshot:
    return DeviceSnapshot(
        id=cfg.id,
        name=cfg.name,
        kind=cfg.kind,
        model=cfg.model,
        room=cfg.room,
        updated_at=time.time(),
        **kwargs,
    )


def _require_local(cfg: DeviceConfig) -> tuple[str, str]:
    if not cfg.ip or not cfg.token:
        raise RuntimeError(
            f"{cfg.id}: missing ip/token — run cloud-sync or edit devices.yaml"
        )
    if len(cfg.token) != 32:
        raise RuntimeError(f"{cfg.id}: token must be 32 hex chars, got len={len(cfg.token)}")
    return cfg.ip, cfg.token


class AirPurifierDriver:
    """Xiaomi / Zhimi air purifier via python-miio (MIoT preferred)."""

    def __init__(self, cfg: DeviceConfig) -> None:
        self.cfg = cfg
        self._dev: Any = None

    def _client(self) -> Any:
        if self._dev is not None:
            return self._dev
        ip, token = _require_local(self.cfg)
        model = (self.cfg.model or "").lower()
        # Classic (non-miot) models use AirPurifier; most modern use AirPurifierMiot
        classic_prefixes = (
            "zhimi.airpurifier.v",
            "zhimi.airpurifier.m1",
            "zhimi.airpurifier.m2",
            "zhimi.airpurifier.ma",
            "zhimi.airpurifier.sa",
            "zhimi.airpurifier.mc1",
        )
        try:
            if model.startswith(classic_prefixes) or model in {
                "zhimi.airpurifier.v6",
                "zhimi.airpurifier.v7",
            }:
                from miio import AirPurifier

                self._dev = AirPurifier(ip, token, model=self.cfg.model)
            else:
                from miio import AirPurifierMiot

                self._dev = AirPurifierMiot(ip, token, model=self.cfg.model)
        except Exception:
            from miio import AirPurifierMiot

            self._dev = AirPurifierMiot(ip, token)
        return self._dev

    def snapshot(self) -> DeviceSnapshot:
        try:
            st = self._client().status()
            on = bool(getattr(st, "is_on", getattr(st, "power", False)))
            mode = getattr(st, "mode", None)
            mode_s = mode.name if hasattr(mode, "name") else (str(mode) if mode is not None else None)
            return _base_snap(
                self.cfg,
                reachable=True,
                on=on,
                aqi=_as_int(getattr(st, "aqi", None)),
                humidity=_as_float(getattr(st, "humidity", None)),
                temperature=_as_float(getattr(st, "temperature", None)),
                mode=mode_s,
                fan_level=_as_int(getattr(st, "fan_level", None)),
                filter_life_remaining=_as_int(
                    getattr(st, "filter_life_remaining", None)
                    or getattr(st, "filter_life", None)
                ),
                extra={
                    "buzzer": getattr(st, "buzzer", None),
                    "child_lock": getattr(st, "child_lock", None),
                    "favorite_level": getattr(st, "favorite_level", None),
                    "motor_speed": getattr(st, "motor_speed", None),
                },
            )
        except Exception as e:
            log.warning("devices.purifier_status_fail", id=self.cfg.id, error=str(e))
            return _base_snap(self.cfg, reachable=False, error=str(e))

    def command(self, action: str, args: dict[str, Any]) -> DeviceSnapshot:
        dev = self._client()
        action = action.lower().strip()
        # Normalize common aliases from dashboard / LLM
        if action in ("turn_on", "power_on", "enable"):
            action = "on"
        elif action in ("turn_off", "power_off", "disable"):
            action = "off"
        try:
            if action == "on":
                dev.on()
            elif action == "off":
                dev.off()
            elif action == "set_on":
                if args.get("value"):
                    dev.on()
                else:
                    dev.off()
            elif action == "set_mode":
                mode = args.get("mode") or args.get("value")
                # Enum handling differs per class — pass through string upper
                if hasattr(dev, "set_mode"):
                    try:
                        from miio.integrations.airpurifier.zhimi.airpurifier_miot import (
                            OperationMode,
                        )

                        dev.set_mode(OperationMode[str(mode).upper()])
                    except Exception:
                        dev.set_mode(mode)
            elif action == "set_fan_level":
                level = int(args.get("level", args.get("value", 1)))
                if hasattr(dev, "set_fan_level"):
                    dev.set_fan_level(level)
                elif hasattr(dev, "set_favorite_level"):
                    dev.set_favorite_level(level)
                else:
                    raise RuntimeError("device has no set_fan_level")
            elif action == "set_favorite_level":
                dev.set_favorite_level(int(args.get("level", args.get("value", 1))))
            else:
                raise RuntimeError(f"unsupported air purifier action: {action}")
            return self.snapshot()
        except Exception as e:
            log.error("devices.purifier_cmd_fail", id=self.cfg.id, action=action, error=str(e))
            snap = self.snapshot()
            snap.error = str(e)
            return snap


class DreameVacuumDriver:
    """Dreame robot vacuum via python-miio DreameVacuum (MIoT)."""

    def __init__(self, cfg: DeviceConfig) -> None:
        self.cfg = cfg
        self._dev: Any = None

    def _client(self) -> Any:
        if self._dev is not None:
            return self._dev
        ip, token = _require_local(self.cfg)
        from miio import DreameVacuum

        kwargs: dict[str, Any] = {}
        if self.cfg.model:
            kwargs["model"] = self.cfg.model
        self._dev = DreameVacuum(ip, token, **kwargs)
        return self._dev

    def snapshot(self) -> DeviceSnapshot:
        try:
            st = self._client().status()
            status = getattr(st, "device_status", None) or getattr(st, "status", None)
            status_s = (
                status.name if hasattr(status, "name") else (str(status) if status is not None else None)
            )
            charging_state = getattr(st, "charging_state", None)
            charging = None
            if charging_state is not None:
                name = charging_state.name if hasattr(charging_state, "name") else str(charging_state)
                charging = "charg" in name.lower() or str(charging_state) in ("1", "Charging")

            # device_status enums often include Sweeping / Idle / Charging etc.
            cleaning = False
            if status_s:
                cleaning = any(
                    k in status_s.lower()
                    for k in ("sweep", "clean", "mop", "run", "pause")
                ) and "idle" not in status_s.lower() and "charg" not in status_s.lower()

            batt = _as_int(getattr(st, "battery_level", getattr(st, "battery", None)))
            return _base_snap(
                self.cfg,
                reachable=True,
                battery_level=batt,
                status=status_s,
                cleaning=cleaning,
                charging=charging,
                cleaning_area=_as_float(getattr(st, "cleaning_area", None)),
                cleaning_time=_as_int(getattr(st, "cleaning_time", None)),
                mode=str(getattr(st, "cleaning_mode", None) or getattr(st, "operating_mode", None)),
                extra={
                    "filter_life_level": getattr(st, "filter_life_level", None),
                    "brush_life_level": getattr(st, "brush_life_level", None),
                    "water_flow": str(getattr(st, "water_flow", None)),
                },
            )
        except Exception as e:
            log.warning("devices.vacuum_status_fail", id=self.cfg.id, error=str(e))
            return _base_snap(self.cfg, reachable=False, error=str(e))

    def command(self, action: str, args: dict[str, Any]) -> DeviceSnapshot:
        dev = self._client()
        action = action.lower()
        try:
            if action in ("start", "start_clean", "clean"):
                dev.start()
            elif action in ("stop", "stop_clean"):
                dev.stop()
            elif action in ("home", "dock", "return_to_base", "charge"):
                dev.home()
            elif action == "locate":
                if hasattr(dev, "find"):
                    dev.find()
                elif hasattr(dev, "locate"):
                    dev.locate()
                else:
                    raise RuntimeError("locate not supported on this model mapping")
            elif action == "set_fan_speed" or action == "set_cleaning_mode":
                # best-effort
                if hasattr(dev, "set_cleaning_mode"):
                    dev.set_cleaning_mode(args.get("mode", args.get("value")))
                else:
                    raise RuntimeError("set_cleaning_mode not available")
            else:
                raise RuntimeError(f"unsupported vacuum action: {action}")
            return self.snapshot()
        except Exception as e:
            log.error("devices.vacuum_cmd_fail", id=self.cfg.id, action=action, error=str(e))
            snap = self.snapshot()
            snap.error = str(e)
            return snap


def build_driver(cfg: DeviceConfig) -> DeviceDriver:
    if cfg.kind == DeviceKind.AIR_PURIFIER:
        return AirPurifierDriver(cfg)
    if cfg.kind == DeviceKind.VACUUM:
        return DreameVacuumDriver(cfg)
    # try infer from model
    from .config import infer_kind

    k = infer_kind(cfg.model, cfg.name)
    if k == DeviceKind.AIR_PURIFIER:
        return AirPurifierDriver(cfg.model_copy(update={"kind": k}))
    if k == DeviceKind.VACUUM:
        return DreameVacuumDriver(cfg.model_copy(update={"kind": k}))
    raise RuntimeError(f"no driver for kind={cfg.kind} model={cfg.model}")


def _as_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
