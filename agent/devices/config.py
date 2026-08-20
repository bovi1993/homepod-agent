"""Load / save ~/.homepod-agent/devices.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.log import get_logger
from shared.util import safe_dump_yaml, safe_load_yaml, state_file

from .models import DeviceConfig, DeviceKind, DevicesFile

log = get_logger("devices.config")

DEFAULT_DEVICES_PATH = "devices.yaml"


def devices_path() -> Path:
    return state_file(DEFAULT_DEVICES_PATH)


def load_devices_file(path: Path | None = None) -> DevicesFile:
    p = path or devices_path()
    raw = safe_load_yaml(p)
    if not raw:
        return DevicesFile()
    try:
        return DevicesFile.model_validate(raw)
    except Exception as e:
        log.error("devices.config_invalid", path=str(p), error=str(e))
        # best-effort parse of devices list
        devices = []
        for d in raw.get("devices") or []:
            try:
                devices.append(DeviceConfig.model_validate(d))
            except Exception:
                continue
        return DevicesFile(cloud=raw.get("cloud") or {}, devices=devices)


def save_devices_file(cfg: DevicesFile, path: Path | None = None) -> Path:
    p = path or devices_path()
    data = cfg.model_dump(mode="json", exclude_none=True)
    safe_dump_yaml(p, data)
    # tokens are secrets — keep file owner-only
    try:
        p.chmod(0o600)
    except OSError:
        pass
    log.info("devices.saved", path=str(p), count=len(cfg.devices))
    return p


def upsert_device(cfg: DevicesFile, device: DeviceConfig) -> DevicesFile:
    out: list[DeviceConfig] = []
    found = False
    for d in cfg.devices:
        if d.id == device.id or (device.did and d.did == device.did) or (
            device.mac and d.mac and d.mac.lower() == device.mac.lower()
        ):
            # merge: keep user name/room/enabled if already set
            merged = device.model_copy(
                update={
                    "name": d.name or device.name,
                    "room": d.room if d.room != "Default Room" else device.room,
                    "enabled": d.enabled,
                    "id": d.id,  # keep stable id
                }
            )
            out.append(merged)
            found = True
        else:
            out.append(d)
    if not found:
        out.append(device)
    return cfg.model_copy(update={"devices": out})


def infer_kind(model: str | None, name: str = "") -> DeviceKind:
    m = (model or "").lower()
    n = name.lower()
    if "vacuum" in m or "vacuum" in n or m.startswith("dreame.vacuum") or "roborock" in m:
        return DeviceKind.VACUUM
    if "airpurifier" in m or "air-purifier" in m or "purifier" in n or "airp" in m:
        return DeviceKind.AIR_PURIFIER
    if "zhimi.air" in m or "zhimi.airp" in m:
        return DeviceKind.AIR_PURIFIER
    return DeviceKind.UNKNOWN


def stable_id_from_cloud(did: Any, model: str | None) -> str:
    kind = infer_kind(model)
    prefix = {
        DeviceKind.AIR_PURIFIER: "ap",
        DeviceKind.VACUUM: "vac",
        DeviceKind.UNKNOWN: "dev",
    }[kind]
    return f"{prefix}-{did}"


def example_devices_yaml() -> str:
    return """# homepod-agent devices
#
# Prefer:  homepod-agent devices cloud-sync --username YOU --password '…'
# Or fill IP + token manually (token = 32 hex chars from the Xiaomi/Dreame app).
#
# cloud:
#   country: de          # cn | de | us | ru | tw | sg | in | i2
#   username: you@example.com
#   last_sync: 0
#
devices: []
# Example manual entry:
# devices:
#   - id: ap-living
#     name: Living Room Purifier
#     kind: air_purifier
#     model: zhimi.airpurifier.mb4
#     ip: 192.168.178.40
#     token: "0123456789abcdef0123456789abcdef"
#     room: Living Room
#   - id: vac-main
#     name: Dreame
#     kind: vacuum
#     model: dreame.vacuum.p2028
#     ip: 192.168.178.41
#     token: "0123456789abcdef0123456789abcdef"
#     room: Hallway
"""
