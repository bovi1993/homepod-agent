"""cameras — ONVIF discovery + RTSP → HLS proxy.

Public surface:
  - discover: ONVIF WS-Discovery scan of the LAN
  - proxy: FastAPI service that proxies RTSP as HLS via go2rtc
  - motion: motion-event subscription (best-effort)

Run with: `python -m cameras.proxy --port 8001`
"""

from .discovery import discover_onvif, list_cameras
from .proxy import main

__all__ = ["discover_onvif", "list_cameras", "main"]