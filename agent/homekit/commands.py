"""Action handlers invoked by the LLM agent.

The agent dispatches a `Command` to one of the handlers here. Handlers mutate
the HAP accessory state through the bridge, then the bridge's heartbeat picks
up the change and the state store updates.

Each handler is async and returns a `CommandResult`.
"""

from __future__ import annotations

from typing import Any

from shared.log import get_logger
from shared.types import Command, CommandResult
from shared.util import now

log = get_logger("homekit.commands")

# Registry of valid actions. The LLM agent's tool schema maps to these names.
ACTIONS = {
    "set_on",
    "set_brightness",
    "set_target_temperature",
    "set_humidity",
    "set_lock",
    "set_position",
    "trigger_scene",
    "refresh",
}


async def dispatch(command: Command, bridge: Any) -> CommandResult:
    """Dispatch a Command to its handler. Returns the new state or an error."""
    action = command.action
    if action not in ACTIONS:
        return CommandResult(
            ok=False,
            target_id=command.target_id,
            action=action,
            error=f"unknown action: {action}",
        )
    try:
        handler = _HANDLERS[action]
        return await handler(command, bridge)
    except Exception as e:
        log.error("command.failed", action=action, target_id=command.target_id, error=str(e))
        return CommandResult(
            ok=False,
            target_id=command.target_id,
            action=action,
            error=str(e),
        )


async def _set_on(command: Command, bridge: Any) -> CommandResult:
    on = bool(command.args.get("value"))
    await bridge.set_accessory_on(command.target_id, on)
    return CommandResult(
        ok=True,
        target_id=command.target_id,
        action=command.action,
    )


async def _set_brightness(command: Command, bridge: Any) -> CommandResult:
    pct = int(command.args["value"])
    if not 0 <= pct <= 100:
        raise ValueError(f"brightness must be 0..100, got {pct}")
    await bridge.set_accessory_brightness(command.target_id, pct)
    return CommandResult(ok=True, target_id=command.target_id, action=command.action)


async def _set_target_temperature(command: Command, bridge: Any) -> CommandResult:
    temp = float(command.args["value"])
    await bridge.set_accessory_target_temperature(command.target_id, temp)
    return CommandResult(ok=True, target_id=command.target_id, action=command.action)


async def _set_humidity(command: Command, bridge: Any) -> CommandResult:
    raise NotImplementedError("humidity control not supported by HomeKit")


async def _set_lock(command: Command, bridge: Any) -> CommandResult:
    locked = bool(command.args.get("value"))
    await bridge.set_accessory_locked(command.target_id, locked)
    return CommandResult(ok=True, target_id=command.target_id, action=command.action)


async def _set_position(command: Command, bridge: Any) -> CommandResult:
    pct = int(command.args["value"])
    if not 0 <= pct <= 100:
        raise ValueError(f"position must be 0..100, got {pct}")
    await bridge.set_accessory_position(command.target_id, pct)
    return CommandResult(ok=True, target_id=command.target_id, action=command.action)


async def _trigger_scene(command: Command, bridge: Any) -> CommandResult:
    scene_name = command.args.get("name") or command.target_id
    await bridge.trigger_scene(scene_name)
    return CommandResult(ok=True, target_id=scene_name, action=command.action)


async def _refresh(command: Command, bridge: Any) -> CommandResult:
    await bridge.refresh_from_hap()
    return CommandResult(ok=True, target_id=command.target_id, action=command.action)


_HANDLERS: dict[str, Any] = {
    "set_on": _set_on,
    "set_brightness": _set_brightness,
    "set_target_temperature": _set_target_temperature,
    "set_humidity": _set_humidity,
    "set_lock": _set_lock,
    "set_position": _set_position,
    "trigger_scene": _trigger_scene,
    "refresh": _refresh,
}