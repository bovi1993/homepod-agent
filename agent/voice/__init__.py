"""voice — macOS-side HomePod bridge.

Two responsibilities:
  1. Discover HomePods on the LAN via mDNS (zeroconf).
  2. Stream TTS audio from the agent to a chosen HomePod via AirPlay 2 / RAOP.

Public surface:
  - discover: scan the LAN for HomePods.
  - bridge: long-running server that accepts /tts requests and streams audio.
  - stream: low-level wrapper around pyatv for sending audio.
"""

from .discover import list_homepods
from .main import main

__all__ = ["list_homepods", "main"]