"""HAP-typed constants used across the homekit package.

References:
  - HomeKit Accessory Protocol: https://developer.apple.com/homekit/
  - HAP-NodeJS spec: https://github.com/homebridge/HAP-NodeJS

These constants are kept narrow: only what the agent actually uses.
"""

from __future__ import annotations

# Default HAP port. pyhap uses 51826 by default; we leave it configurable.
HAP_PORT_DEFAULT = 51826

# Manufacturer / model advertised to HomeKit during pairing.
MANUFACTURER = "homepod-agent"
MODEL = "Bridge v1"
FIRMWARE_REVISION = "0.1.0"

# Setup code prefix; pyhap builds the full code from this base.
# Override with --setup-code on the CLI for a stable, recoverable code.
DEFAULT_SETUP_CODE_PREFIX = "52823145"

# Pairing persistence file under state dir.
PAIRING_FILE = "pairing.json"

# WebSocket subscribers (clients of /ws/state) cap to keep memory bounded.
WS_MAX_SUBSCRIBERS = 32