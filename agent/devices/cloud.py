"""Xiaomi cloud helpers — list devices + extract local tokens.

Dreamehome app accounts are Xiaomi-cloud based for most Dreame vacuums sold
in EU/US; country server is usually ``de`` for NL/EU.
"""

from __future__ import annotations

import time
from typing import Any

from shared.log import get_logger

from .config import (
    infer_kind,
    load_devices_file,
    save_devices_file,
    stable_id_from_cloud,
    upsert_device,
)
from .models import DeviceConfig, DevicesFile

log = get_logger("devices.cloud")

# micloud country codes → host prefix
COUNTRY_CHOICES = ("cn", "de", "us", "ru", "tw", "sg", "in", "i2")


def cloud_login_and_list(
    username: str,
    password: str,
    country: str = "de",
) -> list[dict[str, Any]]:
    """Login to Xiaomi cloud and return raw device dicts (incl. localip + token)."""
    try:
        from micloud import MiCloud
    except ImportError as e:
        raise RuntimeError("micloud not installed — pip install micloud") from e

    if country not in COUNTRY_CHOICES:
        raise ValueError(f"country must be one of {COUNTRY_CHOICES}, got {country!r}")

    mc = MiCloud(username, password)
    mc.default_server = country
    ok = mc.login()
    if not ok:
        raise RuntimeError(
            "Xiaomi cloud login failed. Check email/password and country "
            f"(tried server={country}). Dreamehome may need the same Xiaomi account."
        )

    # micloud get_devices(country=...) returns list of device dicts
    devices = mc.get_devices(country=country) or []
    if isinstance(devices, dict):
        # some versions wrap
        devices = devices.get("result", {}).get("list") or devices.get("list") or []
    log.info("devices.cloud_listed", count=len(devices), country=country)
    return list(devices)


def _pick(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def cloud_device_to_config(raw: dict[str, Any]) -> DeviceConfig | None:
    """Map a Xiaomi cloud device row into our DeviceConfig."""
    did = _pick(raw, "did", "deviceID", "device_id")
    if did is None:
        return None
    model = _pick(raw, "model", "model_name")
    name = _pick(raw, "name", "extra.name", default=str(model or did))
    # nested extra
    if isinstance(raw.get("extra"), dict):
        name = raw["extra"].get("name") or name
    ip = _pick(raw, "localip", "local_ip", "ip")
    token = _pick(raw, "token")
    mac = _pick(raw, "mac")
    kind = infer_kind(str(model) if model else None, str(name))
    # Skip pure cloud-remotes / phones / gateways without token if unknown
    if kind.value == "unknown" and not token:
        return None
    return DeviceConfig(
        id=stable_id_from_cloud(did, str(model) if model else None),
        name=str(name),
        kind=kind,
        model=str(model) if model else None,
        ip=str(ip) if ip else None,
        token=str(token) if token else None,
        did=str(did),
        mac=str(mac) if mac else None,
        extra={
            "uid": _pick(raw, "uid"),
            "isOnline": _pick(raw, "isOnline", "is_online"),
            "ssid": _pick(raw, "ssid"),
        },
    )


def sync_from_cloud(
    username: str,
    password: str,
    country: str = "de",
    kinds_only: set[str] | None = None,
) -> DevicesFile:
    """Pull cloud device list and merge into devices.yaml (never stores password)."""
    raw_list = cloud_login_and_list(username, password, country=country)
    cfg = load_devices_file()
    kinds_only = kinds_only or {"air_purifier", "vacuum"}

    imported = 0
    skipped = 0
    for raw in raw_list:
        dev = cloud_device_to_config(raw)
        if not dev:
            skipped += 1
            continue
        if dev.kind.value not in kinds_only and "all" not in kinds_only:
            skipped += 1
            continue
        cfg = upsert_device(cfg, dev)
        imported += 1

    cfg.cloud = {
        **(cfg.cloud or {}),
        "country": country,
        "username": username,
        "last_sync": time.time(),
        "last_import_count": imported,
    }
    save_devices_file(cfg)
    log.info("devices.cloud_synced", imported=imported, skipped=skipped)
    return cfg
