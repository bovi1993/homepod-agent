"""Discover HomePods on the local network via mDNS / Bonjour.

Uses zeroconf directly so we don't depend on pyatv at import time. Returns a
list of typed records we can later connect to.
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import Any

from shared.log import get_logger

log = get_logger("voice.discover")


@dataclass
class HomePodInfo:
    name: str
    address: str
    port: int
    model: str | None = None  # HomePod, HomePod mini, etc.
    room: str | None = None
    txt: dict[str, str] | None = None


def _parse_txt(record: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in record.properties.items() if hasattr(record, "properties") else []:
        try:
            ks = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            vs = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            out[ks] = vs
        except Exception:
            continue
    return out


def _mdns_browse_sync(timeout_s: float = 3.0) -> list[HomePodInfo]:
    """Synchronous mDNS browse — runs zeroconf ServiceBrowser for `timeout_s`."""
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

    results: list[HomePodInfo] = []

    class Listener(ServiceListener):
        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            if not info:
                return
            try:
                addresses = info.parsed_addresses()
                if not addresses:
                    return
                txt = _parse_txt(info)
                # Heuristic: AirPlay receivers are HomePods/Apple TVs.
                # Real check needs _hap._tcp; for now we accept any _airplay.
                if not name.lower().startswith(("homepod", "bedroom", "kitchen", "living")):
                    # Apple TVs / generic devices — skip
                    return
                results.append(
                    HomePodInfo(
                        name=name,
                        address=addresses[0],
                        port=info.port or 7000,
                        model=txt.get("am"),
                        room=txt.get("rs"),
                        txt=txt,
                    )
                )
            except Exception as e:
                log.debug("discover.parse_failed", name=name, error=str(e))

        def remove_service(self, *_args: Any, **_kw: Any) -> None:
            pass

    zc = Zeroconf()
    try:
        # Browse both AirPlay and HAP for completeness.
        ServiceBrowser(zc, "_airplay._tcp.local.", Listener())
        ServiceBrowser(zc, "_raop._tcp.local.", Listener())
        import time

        time.sleep(timeout_s)
    finally:
        zc.close()

    return results


async def list_homepods(timeout_s: float = 3.0) -> list[HomePodInfo]:
    """Async wrapper for the sync browse."""
    return await asyncio.to_thread(_mdns_browse_sync, timeout_s)


async def find_homepod(room: str | None = None) -> HomePodInfo | None:
    """Find a HomePod, optionally by room name (case-insensitive substring)."""
    pods = await list_homepods(timeout_s=3.0)
    if not pods:
        return None
    if room:
        rl = room.lower()
        for p in pods:
            if rl in p.name.lower() or (p.room and rl in p.room.lower()):
                return p
    return pods[0]