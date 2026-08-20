"""Unpairing CLI helper.

Removes the agent from any paired HomeKit home by deleting the pairing config
and clearing the bridge's HAP state.

Run: `python -m homekit.unpair`
"""

from __future__ import annotations

import argparse
import sys

from shared.log import configure_logging, get_logger
from shared.util import state_file

from .constants import PAIRING_FILE

log = get_logger("homekit.unpair")


def main() -> int:
    p = argparse.ArgumentParser(description="Remove homepod-agent from your HomeKit home")
    args = p.parse_args()

    configure_logging("homekit-unpair")

    pairing = state_file(PAIRING_FILE)
    if pairing.exists():
        pairing.unlink()
        log.info("pairing.removed", path=str(pairing))
        print(f"✅ Removed pairing config: {pairing}")
        print()
        print(" You may also need to remove 'HomePod Agent' from your iPhone Home app:")
        print("   Home → tap 'HomePod Agent' → Remove from Home")
        return 0

    print(" No pairing config found — already unpaired.")
    return 0


if __name__ == "__main__":
    sys.exit(main())