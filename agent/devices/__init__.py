"""Xiaomi / Dreame device control for homepod-agent.

Local-first via python-miio (MIoT). Tokens and IPs come from
``~/.homepod-agent/devices.yaml``, optionally filled by
``homepod-agent devices cloud-sync`` (Xiaomi cloud / Dreamehome account).
"""

from .manager import DeviceManager
from .models import DeviceConfig, DeviceKind, DeviceSnapshot

__all__ = [
    "DeviceManager",
    "DeviceConfig",
    "DeviceKind",
    "DeviceSnapshot",
]
