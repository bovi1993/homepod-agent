"""Long-running daemon: starts the HAP bridge + exposes REST + WebSocket APIs.

Start with `python -m homekit.daemon` or `make run`.
"""

from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

from shared.log import configure_logging, get_logger
from shared.util import state_dir

from .bridge import BridgeConfig, HomeKitBridge
from .state import store

log = get_logger("homekit.daemon")


async def run() -> None:
    """Boot the HAP bridge and the REST/WS server."""
    from .server import HomeKitServer

    bridge = HomeKitBridge(BridgeConfig())
    await bridge.start()

    server = HomeKitServer(bridge, store)
    server_task = asyncio.create_task(server.start())

    log.info("daemon.started", state_dir=str(state_dir()))

    stop = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        log.info("daemon.signal")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _signal_handler)

    await stop.wait()
    log.info("daemon.stopping")
    server_task.cancel()
    with suppress(asyncio.CancelledError):
        await server_task
    await bridge.stop()


def main() -> None:
    configure_logging("homekit-daemon")
    asyncio.run(run())


if __name__ == "__main__":
    main()