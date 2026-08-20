"""LAN discovery for miio devices (UDP 54321 hello)."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Any

from shared.log import get_logger

log = get_logger("devices.discover")

# Classic miio discovery hello (32-byte header, no payload)
_HELLO = bytes.fromhex(
    "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)


@dataclass
class DiscoveredDevice:
    ip: str
    device_id: int | None
    token_hint: str | None  # often all-ff until paired
    raw_len: int


def _parse_hello_reply(data: bytes) -> tuple[int | None, str | None]:
    """Parse miio header: magic 0x2131, length, unknown, device_id, stamp, md5/token."""
    if len(data) < 32 or data[0:2] != b"\x21\x31":
        return None, None
    device_id = int.from_bytes(data[8:12], "big")
    token_bytes = data[16:32]
    token_hex = token_bytes.hex()
    # Uninitialized devices echo ff…; real tokens only after handshake with key
    if token_hex == "f" * 32:
        token_hex = None  # type: ignore[assignment]
    return device_id, token_hex


def discover_miio(
    broadcast: str = "192.168.178.255",
    timeout_s: float = 4.0,
    unicast_ips: list[str] | None = None,
) -> list[DiscoveredDevice]:
    """Broadcast + optional unicast miio hello. Returns unique IPs that answered."""
    found: dict[str, DiscoveredDevice] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.4)
    try:
        sock.sendto(_HELLO, (broadcast, 54321))
        targets = list(unicast_ips or [])
        for ip in targets:
            try:
                sock.sendto(_HELLO, (ip, 54321))
            except OSError:
                pass

        end = time.time() + timeout_s
        while time.time() < end:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            ip = addr[0]
            did, token = _parse_hello_reply(data)
            found[ip] = DiscoveredDevice(
                ip=ip, device_id=did, token_hint=token, raw_len=len(data)
            )
            log.info("devices.discovered", ip=ip, device_id=did)
    finally:
        sock.close()
    return list(found.values())


def discover_miio_mdns(timeout_s: float = 5.0) -> list[dict[str, Any]]:
    """Optional mDNS _miio._udp discovery (often empty on modern firmware)."""
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError:
        return []

    results: list[dict[str, Any]] = []

    class L(ServiceListener):
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name, timeout=2000)
            if not info:
                return
            results.append(
                {
                    "name": name,
                    "addresses": info.parsed_addresses(),
                    "port": info.port,
                    "properties": {
                        k.decode() if isinstance(k, bytes) else k: (
                            v.decode() if isinstance(v, bytes) else v
                        )
                        for k, v in (info.properties or {}).items()
                    },
                }
            )

        def remove_service(self, *args: Any) -> None:
            pass

        def update_service(self, *args: Any) -> None:
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, "_miio._udp.local.", L())
        time.sleep(timeout_s)
    finally:
        zc.close()
    return results
