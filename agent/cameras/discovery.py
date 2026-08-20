"""ONVIF discovery of cameras on the LAN.

ONVIF devices advertise themselves via WS-Discovery multicast on
239.255.255.250:3702. We send a Probe and parse the ProbeMatches.

The resulting `CameraInfo` records are persisted to <state-dir>/cameras.yaml.
"""

from __future__ import annotations

import asyncio
import socket
import struct
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from shared.log import get_logger
from shared.types import CameraInfo
from shared.util import safe_dump_yaml, safe_load_yaml, state_file

log = get_logger("cameras.discovery")

CAMERAS_FILE = "cameras.yaml"

WS_DISCOVERY_MULTICAST = ("239.255.255.250", 3702)


@dataclass
class DiscoveredCamera:
    name: str
    address: str
    port: int
    xaddr: str
    manufacturer: str | None = None
    model: str | None = None
    scopes: list[str] = field(default_factory=list)
    requires_auth: bool = True

    def to_camera_info(self) -> CameraInfo:
        # Best-effort RTSP URL; if no auth, use anonymous main-stream path.
        path = "/Streaming/Channels/101"  # Hikvision-style default
        if "reolink" in (self.manufacturer or "").lower():
            path = "/h264Preview_01_main"
        creds = "user:pass@" if self.requires_auth else ""
        rtsp = f"rtsp://{creds}{self.address}:554{path}"
        return CameraInfo(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, self.xaddr)),
            name=self.name,
            rtsp_url=rtsp,
            online=True,
        )


# ---------------------------------------------------------------------------
# WS-Discovery Probe (XML-over-UDP multicast)
# ---------------------------------------------------------------------------


PROBE_XML = """<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:dn="http://www.onvif.org/ver10/network/wsdl"
          xmlns="http://www.w3.org/2003/05/soap-envelope">
  <Header>
    <wsa:MessageID xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
      uuid:{msg_id}
    </wsa:MessageID>
    <wsa:To xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
      urn:schemas-xmlsoap-org:ws:2005:04:discovery
    </wsa:To>
    <wsa:Action xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
      http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe
    </wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <Types>dn:NetworkVideoTransmitter</Types>
    </Probe>
  </Body>
</Envelope>"""


async def discover_onvif(timeout_s: float = 4.0) -> list[DiscoveredCamera]:
    """Send a single WS-Discovery Probe and collect ProbeMatches."""
    msg_id = uuid.uuid4().urn.split(":")[-1]
    payload = PROBE_XML.format(msg_id=msg_id).encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.settimeout(timeout_s)

    cameras: list[DiscoveredCamera] = []

    try:
        sock.sendto(payload, WS_DISCOVERY_MULTICAST)
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                data, addr = sock.recvfrom(8192)
                cam = _parse_probe_match(data, addr)
                if cam and not any(c.xaddr == cam.xaddr for c in cameras):
                    cameras.append(cam)
            except socket.timeout:
                break
    finally:
        sock.close()

    return cameras


def _parse_probe_match(data: bytes, addr: tuple[str, int]) -> DiscoveredCamera | None:
    """Parse a single ProbeMatch response into a DiscoveredCamera."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    ns = {
        "d": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
        "dn": "http://www.onvif.org/ver10/network/wsdl",
    }

    xaddr_el = root.find(".//dn:XAddrs", ns)
    scopes_el = root.find(".//d:Scopes", ns)
    if xaddr_el is None or not xaddr_el.text:
        return None
    xaddr = xaddr_el.text.strip().split()[0]  # take first URL
    scopes_text = (scopes_el.text or "").strip() if scopes_el is not None else ""

    # Parse XAddr into host:port
    if xaddr.startswith("http://"):
        xaddr = xaddr[len("http://") :]
    host_port = xaddr.split("/")[0]
    if ":" in host_port:
        host, port_s = host_port.split(":", 1)
        port = int(port_s)
    else:
        host = host_port
        port = 80

    manufacturer = None
    model = None
    for scope in scopes_text.split():
        if scope.startswith("onvif://www.onvif.org/name/"):
            parts = scope.rsplit("/", 1)[-1].rsplit(" ", 1)
            manufacturer = parts[0] if len(parts) > 0 else None
            model = parts[-1] if len(parts) > 1 else None

    name = model or host
    return DiscoveredCamera(
        name=name,
        address=host,
        port=port,
        xaddr=xaddr,
        manufacturer=manufacturer,
        model=model,
        scopes=scopes_text.split(),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def list_cameras(path: Path | None = None) -> list[CameraInfo]:
    """Return all configured cameras, persisting newly discovered ones."""
    target = path or state_file(CAMERAS_FILE)
    cfg = safe_load_yaml(target)
    return [CameraInfo(**c) for c in cfg.get("cameras", [])]


async def save_cameras(cams: list[CameraInfo], path: Path | None = None) -> None:
    target = path or state_file(CAMERAS_FILE)
    safe_dump_yaml(target, {"cameras": [asdict(c) if hasattr(c, "__dict__") else c.model_dump() for c in cams]})


async def discover_and_persist() -> list[CameraInfo]:
    cams = await discover_onvif(timeout_s=4.0)
    infos = [c.to_camera_info() for c in cams]
    await save_cameras(infos)
    return infos