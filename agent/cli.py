"""Top-level CLI for homepod-agent.

Subcommands:
  serve     - start all services
  pair      - run the HomeKit pairing helper
  unpair    - remove pairing
  chat      - one-shot chat (for shell use)
  discover  - ONVIF camera discovery

Examples:
  homepod-agent serve
  homepod-agent pair
  homepod-agent chat "turn on the kitchen light"
  homepod-agent discover
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Sequence


def cmd_serve(_: argparse.Namespace) -> int:
    from agent.cli_daemon import run_all

    asyncio.run(run_all())
    return 0


def cmd_pair(args: argparse.Namespace) -> int:
    from agent.homekit.pair import main as pair_main

    sys.argv = ["pair", *([] if not args.setup_code else ["--setup-code", args.setup_code])]
    pair_main()
    return 0


def cmd_unpair(_: argparse.Namespace) -> int:
    from agent.homekit.unpair import main as unpair_main

    return unpair_main()


def cmd_chat(args: argparse.Namespace) -> int:
    import httpx

    user = args.text
    room = args.room
    try:
        r = httpx.post(
            f"{args.url}/chat",
            json={"user": user, "room": room},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        print(data.get("data", {}).get("reply", ""))
        return 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def cmd_discover(args: argparse.Namespace) -> int:
    from agent.cameras.discovery import discover_onvif

    cams = asyncio.run(discover_onvif(timeout_s=args.timeout))
    if not cams:
        print("no cameras found")
        return 1
    for c in cams:
        print(f"  {c.name:30s}  {c.address}:{c.port}  {c.manufacturer or '?'}/{c.model or '?'}")
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    """Delegate to devices package CLI (cloud-sync, status, cmd, serve, …)."""
    from devices.__main__ import main as devices_main

    rest = list(args.devices_argv or [])
    if rest and rest[0] == "--":
        rest = rest[1:]
    return devices_main(rest)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="homepod-agent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="start all services")
    p_serve.set_defaults(func=cmd_serve)

    p_pair = sub.add_parser("pair", help="HomeKit pairing helper")
    p_pair.add_argument("--setup-code", default="528-23-142")
    p_pair.set_defaults(func=cmd_pair)

    p_unpair = sub.add_parser("unpair", help="remove pairing")
    p_unpair.set_defaults(func=cmd_unpair)

    p_chat = sub.add_parser("chat", help="one-shot chat")
    p_chat.add_argument("text")
    p_chat.add_argument("--room", default=None)
    p_chat.add_argument("--url", default="http://127.0.0.1:8000")
    p_chat.set_defaults(func=cmd_chat)

    p_disc = sub.add_parser("discover", help="ONVIF camera discovery")
    p_disc.add_argument("--timeout", type=float, default=4.0)
    p_disc.set_defaults(func=cmd_discover)

    p_dev = sub.add_parser(
        "devices",
        help="Xiaomi air purifier + Dreame vacuum (cloud-sync, status, cmd, serve)",
    )
    p_dev.add_argument(
        "devices_argv",
        nargs=argparse.REMAINDER,
        help="passed to devices CLI; try: cloud-sync | status | discover | serve",
    )
    p_dev.set_defaults(func=cmd_devices)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())