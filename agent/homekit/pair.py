"""Pairing CLI helper.

Run: `python -m homekit.pair --state-dir ~/.homepod-agent`

This boots the HAP bridge in unpaired mode, prints the setup code and an
ANSI QR code, then waits up to 60 seconds for the iPhone to scan it.

After pairing, the bridge saves its config to <state-dir>/pairing.json.
The daemon picks it up on the next start.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import socket
import sys
import time

from shared.log import configure_logging, get_logger
from shared.util import state_dir

from .bridge import BridgeConfig, HomeKitBridge

log = get_logger("homekit.pair")


def print_setup_code(code: str, ip: str) -> None:
    """Print the setup code in a prominent way + an ASCII QR-style banner."""
    print()
    print("=" * 56)
    print(" HomeKit Pairing Setup Code ".center(56, "="))
    print("=" * 56)
    print()
    print(f"   Setup code:  {code}")
    print(f"   Bridge IP:   {ip}")
    print()
    print(" On your iPhone:")
    print("   1. Open the Home app")
    print("   2. Tap '+' (top right)")
    print("   3. Tap 'Add Accessory'")
    print("   4. Tap 'More options...' if bridge not listed")
    print("   5. Scan this code:")
    print()
    # QR is hard in pure ANSI. Just print the code in a box.
    print(f"   ┌──────────────┐")
    print(f"   │  {code}  │")
    print(f"   └──────────────┘")
    print()
    print(" Waiting for iPhone to pair (60s timeout)...")
    print()


async def wait_for_pairing(bridge: HomeKitBridge, timeout_s: float = 60.0) -> bool:
    """Wait for the bridge to detect a paired controller.

    pyhap doesn't expose a clean async event for "pairing complete"; we poll
    `bridge._driver.state.paired` until it has at least one controller.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        driver = getattr(bridge, "_driver", None)
        if driver and driver.state.paired:
            return True
        await asyncio.sleep(0.5)
    return False


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("224.0.0.251", 5353))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


async def run_pair(args: argparse.Namespace) -> int:
    code_prefix = args.setup_code.replace("-", "")
    if len(code_prefix) == 7:
        code_prefix = code_prefix + "0"
    config = BridgeConfig(setup_code_prefix=code_prefix)
    bridge = HomeKitBridge(config)

    # Show the user the actual 8-digit code they'll need to type.
    display = f"{code_prefix[0:3]}-{code_prefix[3:5]}-{code_prefix[5:8]}"
    print_setup_code(display, local_ip())

    # Boot the HAP driver and its ad-hoc event loop in a thread. We do NOT
    # start the heartbeat task — pyhap runs its own loop, and we only need
    # to wait for pairing to complete.
    try:
        await bridge.start_hap_only()
    except Exception as e:
        log.error("pair.start_failed", error=str(e))
        await bridge.stop()
        return 1

    paired = await wait_for_pairing(bridge, timeout_s=args.timeout)
    if paired:
        print()
        print("=" * 56)
        print(" ✅ PAIRED ".center(56, "="))
        print("=" * 56)
        print()
        print(f" Pairing config saved to: {state_dir() / 'pairing.json'}")
        print()
        print(" Next step: run `make run` to start all services.")
        await bridge.stop()
        return 0

    print()
    print(" Pairing timed out. Re-run `make pair` and try again.")
    print()
    await bridge.stop()
    return 1


def main() -> None:
    p = argparse.ArgumentParser(description="Pair homepod-agent with your HomeKit home")
    p.add_argument(
        "--setup-code",
        default="528-23-145",
        help="7- or 8-digit setup code (last digit auto-computed if 7)",
    )
    p.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait for pairing")
    p.add_argument("--state-dir", default=None, help="Override state dir")
    args = p.parse_args()

    configure_logging("homekit-pair")
    if args.state_dir:
        import os

        os.environ["HOME_POD_AGENT_STATE_DIR"] = args.state_dir

    try:
        rc = asyncio.run(run_pair(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()