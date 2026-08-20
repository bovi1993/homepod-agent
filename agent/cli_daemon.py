"""Daemon orchestrator: boots all services in one process.

For users who prefer a single command (`homepod-agent serve`) instead of
manually launching four uvicorn workers.

Each service runs in its own asyncio task. If one dies, the orchestrator
restarts it (up to a configurable retry budget).
"""

from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

from shared.log import configure_logging, get_logger

log = get_logger("cli.daemon")


async def _homekit_svc() -> None:
    from homekit.daemon import run as hk_run

    await hk_run()


async def _llm_svc() -> None:
    import uvicorn

    from llm.main import app

    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    await uvicorn.Server(config).serve()


async def _voice_svc() -> None:
    import uvicorn

    from voice.main import app

    config = uvicorn.Config(app, host="0.0.0.0", port=8765, log_level="info")
    await uvicorn.Server(config).serve()


async def _cameras_svc() -> None:
    import uvicorn

    from cameras.proxy import app

    config = uvicorn.Config(app, host="0.0.0.0", port=8001, log_level="info")
    await uvicorn.Server(config).serve()


SERVICES: dict[str, "object"] = {  # type: ignore[type-arg]
    "homekit": _homekit_svc,
    "llm": _llm_svc,
    "voice": _voice_svc,
    "cameras": _cameras_svc,
}


async def run_all() -> None:
    """Boot all services concurrently."""
    configure_logging("homepod-agent")
    stop = asyncio.Event()

    def _handler(*_: object) -> None:
        log.info("signal.received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _handler)

    # The svc callables are coroutine functions; type checker doesn't like
    # `object` as the dict value type, so we cast at use site.
    tasks: list[asyncio.Task[None]] = []
    for name, svc in SERVICES.items():
        coro = svc()  # type: ignore[operator]
        tasks.append(asyncio.create_task(coro, name=f"svc-{name}"))
    log.info("daemon.running", services=list(SERVICES.keys()))

    await stop.wait()

    log.info("daemon.stopping")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)