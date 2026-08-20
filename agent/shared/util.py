"""Shared utilities and helpers."""

from __future__ import annotations

import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any


def state_dir() -> Path:
    """Return the per-user state directory, creating it if missing."""
    base = os.environ.get("HOME_POD_AGENT_STATE_DIR") or os.path.expanduser(
        "~/.homepod-agent"
    )
    p = Path(base).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_file(name: str) -> Path:
    return state_dir() / name


def request_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


def host_ip() -> str:
    """Best-effort local LAN IP, falling back to loopback."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("224.0.0.251", 5353))  # mDNS multicast; doesn't actually send
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def safe_load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    import yaml  # local import to keep shared/ importable in tight contexts

    with path.open() as f:
        return yaml.safe_load(f) or {}


def safe_dump_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)