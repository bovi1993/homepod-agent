"""homekit — HomeKit control layer.

Public surface:
  - HomeKitBridge: the long-running HAP accessory that joins the home.
  - StateStore: in-memory cache of the latest home snapshot.
  - commands: action handlers invoked by the LLM agent.
  - pair: CLI helper for the initial pairing dance.
  - unpair: CLI helper for removing the agent from the home.

See `daemon.py` for the runtime entry point.
"""

from .constants import HAP_PORT_DEFAULT
from .state import StateStore
from .bridge import HomeKitBridge

__all__ = ["HAP_PORT_DEFAULT", "StateStore", "HomeKitBridge"]