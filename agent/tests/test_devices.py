"""Unit tests for devices config + kind inference (no LAN required)."""

from __future__ import annotations

from pathlib import Path

from devices.cloud import cloud_device_to_config
from devices.config import infer_kind, load_devices_file, save_devices_file, upsert_device
from devices.models import DeviceConfig, DeviceKind, DevicesFile


def test_infer_kind() -> None:
    assert infer_kind("zhimi.airpurifier.mb4") == DeviceKind.AIR_PURIFIER
    assert infer_kind("dreame.vacuum.p2028") == DeviceKind.VACUUM
    assert infer_kind(None, "Living Purifier") == DeviceKind.AIR_PURIFIER
    assert infer_kind("unknown.thing") == DeviceKind.UNKNOWN


def test_cloud_device_to_config_purifier() -> None:
    raw = {
        "did": "12345",
        "name": "Bedroom AP",
        "model": "zhimi.airpurifier.mb4",
        "localip": "192.168.178.40",
        "token": "a" * 32,
        "mac": "AA:BB:CC:DD:EE:FF",
        "isOnline": True,
    }
    cfg = cloud_device_to_config(raw)
    assert cfg is not None
    assert cfg.kind == DeviceKind.AIR_PURIFIER
    assert cfg.ip == "192.168.178.40"
    assert cfg.token == "a" * 32
    assert cfg.id.startswith("ap-")


def test_cloud_device_to_config_dreame() -> None:
    raw = {
        "did": "999",
        "model": "dreame.vacuum.p2009",
        "localip": "192.168.178.41",
        "token": "b" * 32,
        "extra": {"name": "Dreame D9"},
    }
    cfg = cloud_device_to_config(raw)
    assert cfg is not None
    assert cfg.kind == DeviceKind.VACUUM
    assert cfg.name == "Dreame D9"
    assert cfg.id.startswith("vac-")


def test_upsert_and_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "devices.yaml"
    cfg = DevicesFile(devices=[])
    d1 = DeviceConfig(
        id="ap-1",
        name="Purifier",
        kind=DeviceKind.AIR_PURIFIER,
        ip="1.2.3.4",
        token="c" * 32,
    )
    cfg = upsert_device(cfg, d1)
    save_devices_file(cfg, path)
    loaded = load_devices_file(path)
    assert len(loaded.devices) == 1
    assert loaded.devices[0].token == "c" * 32

    # upsert same did keeps stable id / user name
    d2 = d1.model_copy(update={"name": "New Name From Cloud", "did": "1"})
    cfg2 = upsert_device(loaded, d2)
    # same id match
    assert len(cfg2.devices) == 1
