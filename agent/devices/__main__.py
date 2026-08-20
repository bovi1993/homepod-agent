"""CLI entry: python -m devices … / wired via homepod-agent devices."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Sequence

from shared.log import configure_logging


def cmd_list(_: argparse.Namespace) -> int:
    from .config import load_devices_file
    from .manager import DeviceManager

    cfg = load_devices_file()
    if not cfg.devices:
        print("No devices in ~/.homepod-agent/devices.yaml")
        print("Run:  homepod-agent devices cloud-sync --username EMAIL --password '…'")
        print("  or:  homepod-agent devices init")
        return 1
    print(f"{'ID':20s} {'KIND':14s} {'IP':16s} {'TOKEN':6s} NAME")
    for d in cfg.devices:
        tok = "yes" if d.token else "NO"
        print(
            f"{d.id:20s} {d.kind.value:14s} {(d.ip or '-'):16s} {tok:6s} {d.name}"
            + (f"  [{d.model}]" if d.model else "")
        )
    return 0


def cmd_init(_: argparse.Namespace) -> int:
    from pathlib import Path

    from .config import devices_path, example_devices_yaml

    p = devices_path()
    if p.exists() and p.stat().st_size > 0:
        print(f"already exists: {p}")
        return 0
    p.write_text(example_devices_yaml())
    p.chmod(0o600)
    print(f"wrote {p}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from .discover import discover_miio, discover_miio_mdns

    print(f"Scanning miio UDP (timeout={args.timeout}s)…")
    found = discover_miio(timeout_s=args.timeout)
    if not found:
        print("  (no miio replies — device offline, different VLAN, or cloud-only firmware)")
    for d in found:
        print(f"  {d.ip:16s}  did={d.device_id}  token_hint={d.token_hint or 'n/a'}")
    mdns = discover_miio_mdns(timeout_s=min(args.timeout, 5.0))
    if mdns:
        print("mDNS _miio._udp:")
        for m in mdns:
            print(f"  {m}")
    return 0 if found or mdns else 1


def cmd_cloud_sync(args: argparse.Namespace) -> int:
    from .cloud import sync_from_cloud

    try:
        cfg = sync_from_cloud(
            username=args.username,
            password=args.password,
            country=args.country,
            kinds_only=set(args.kinds.split(",")) if args.kinds else None,
        )
    except Exception as e:
        print(f"cloud-sync failed: {e}", file=sys.stderr)
        return 1
    print(f"Imported/updated devices → ~/.homepod-agent/devices.yaml")
    print(f"  country={cfg.cloud.get('country')}  count={len(cfg.devices)}")
    for d in cfg.devices:
        print(
            f"  - {d.id}: {d.name} ({d.kind.value}) ip={d.ip or '?'} "
            f"token={'yes' if d.token else 'NO'} model={d.model}"
        )
    print("\nNext: homepod-agent devices status")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from .manager import DeviceManager

    async def _run() -> int:
        mgr = DeviceManager()
        mgr.reload()
        snaps = await mgr.refresh_all()
        if not snaps:
            print("no devices configured")
            return 1
        for s in snaps:
            flag = "OK" if s.reachable else "DOWN"
            line = f"[{flag}] {s.id:20s} {s.name:24s} {s.kind.value}"
            if s.kind.value == "air_purifier":
                line += f"  on={s.on} aqi={s.aqi} mode={s.mode} filter={s.filter_life_remaining}"
            elif s.kind.value == "vacuum":
                line += (
                    f"  status={s.status} bat={s.battery_level}% "
                    f"cleaning={s.cleaning} charging={s.charging}"
                )
            if s.error:
                line += f"  err={s.error}"
            print(line)
            if args.json:
                print(json.dumps(s.model_dump(), indent=2))
        return 0 if any(s.reachable for s in snaps) else 2

    return asyncio.run(_run())


def cmd_cmd(args: argparse.Namespace) -> int:
    from .manager import DeviceManager
    from .models import DeviceCommand

    async def _run() -> int:
        mgr = DeviceManager()
        mgr.reload()
        extra = {}
        if args.arg:
            for pair in args.arg:
                k, _, v = pair.partition("=")
                if v.lower() in ("true", "false"):
                    extra[k] = v.lower() == "true"
                else:
                    try:
                        extra[k] = int(v)
                    except ValueError:
                        try:
                            extra[k] = float(v)
                        except ValueError:
                            extra[k] = v
        result = await mgr.run_command(
            DeviceCommand(device_id=args.device_id, action=args.action, args=extra)
        )
        print(json.dumps(result.model_dump(), indent=2, default=str))
        return 0 if result.ok else 1

    return asyncio.run(_run())


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .manager import DeviceManager
    from .server import DevicesServer

    async def _serve() -> None:
        mgr = DeviceManager(poll_interval_s=args.poll)
        await mgr.start()
        server = DevicesServer(mgr, port=args.port)
        config = uvicorn.Config(
            server.app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
        await uvicorn.Server(config).serve()

    asyncio.run(_serve())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="homepod-agent devices",
        description="Xiaomi air purifier + Dreame (Dreamehome) vacuum control",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="write example devices.yaml")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("list", help="list configured devices")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("discover", help="LAN miio UDP discovery")
    s.add_argument("--timeout", type=float, default=4.0)
    s.set_defaults(func=cmd_discover)

    s = sub.add_parser(
        "cloud-sync",
        help="login to Xiaomi cloud (Dreamehome account) and pull IP+token",
    )
    s.add_argument("--username", required=True, help="Xiaomi / Dreamehome email or phone")
    s.add_argument("--password", required=True)
    s.add_argument(
        "--country",
        default="de",
        help="cloud server: cn|de|us|ru|tw|sg|in|i2 (default de for EU/NL)",
    )
    s.add_argument(
        "--kinds",
        default="air_purifier,vacuum",
        help="comma kinds to import, or 'all'",
    )
    s.set_defaults(func=cmd_cloud_sync)

    s = sub.add_parser("status", help="poll live status for all devices")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("cmd", help="run a command on a device")
    s.add_argument("device_id")
    s.add_argument(
        "action",
        help="purifier: on|off|set_mode|set_fan_level · vacuum: start|stop|home|locate",
    )
    s.add_argument(
        "--arg",
        action="append",
        help="key=value (repeatable), e.g. --arg mode=Auto --arg level=2",
    )
    s.set_defaults(func=cmd_cmd)

    s = sub.add_parser("serve", help="run devices HTTP API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8002)
    s.add_argument("--poll", type=float, default=30.0)
    s.set_defaults(func=cmd_serve)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging("devices")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
