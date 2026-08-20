"""Tool schema exposed to the LLM.

Tools wrap calls to the HomeKit control layer. Each tool:
  1. Has a JSON schema describing its inputs (sent to the LLM).
  2. Has an async `run(args, bridge)` that returns a ToolResult.

The tools are intentionally narrow: cover the LLM's likely needs without
exposing arbitrary HomeKit writes (which could damage the home).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from shared.log import get_logger
from shared.types import ToolResult

log = get_logger("llm.tools")

# Default HomeKit control layer URL — overridden by env var in production.
HOMEKIT_URL = "http://127.0.0.1:51827"


# ---------------------------------------------------------------------------
# Tool schema definitions (sent to the LLM)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_accessories",
            "description": "List all HomeKit accessories and their current state. Use this whenever the user asks about the home or specific devices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "light", "switch", "outlet", "thermostat", "lock",
                            "door", "window", "window_covering", "fan", "speaker",
                            "tv", "camera", "sensor_motion", "sensor_contact",
                            "sensor_temperature", "sensor_humidity", "sensor_light",
                        ],
                        "description": "Filter by accessory kind (optional).",
                    },
                    "room": {"type": "string", "description": "Filter by room name (optional)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_accessory",
            "description": "Get the current state of a single accessory by its name or id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {
                        "type": "string",
                        "description": "Accessory UUID or display name.",
                    }
                },
                "required": ["id_or_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_light",
            "description": "Turn a light on/off, optionally with brightness (0..100).",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {"type": "string"},
                    "on": {"type": "boolean"},
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["id_or_name", "on"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_thermostat",
            "description": "Set the target temperature on a thermostat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {"type": "string"},
                    "target_celsius": {"type": "number"},
                },
                "required": ["id_or_name", "target_celsius"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_lock",
            "description": "Lock or unlock a door lock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {"type": "string"},
                    "locked": {"type": "boolean"},
                },
                "required": ["id_or_name", "locked"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_scene",
            "description": "Trigger a HomeKit scene by name (e.g., 'Good Morning', 'Bedtime').",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "speak_to_homepod",
            "description": "Send a text message that the agent will speak through the user's HomePod.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to say. Keep under 200 chars."},
                    "room": {"type": "string", "description": "Room of the HomePod, e.g. 'Bedroom'."},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_history",
            "description": "Search the recent change history of HomeKit accessories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "accessory_id_or_name": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_devices",
            "description": (
                "List Xiaomi/Dreame devices (air purifiers, robot vacuums) and their "
                "live state (AQI, power, battery, cleaning status)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["air_purifier", "vacuum"],
                        "description": "Optional filter.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_air_purifier",
            "description": "Turn a Xiaomi air purifier on/off, or set mode/fan level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {"type": "string"},
                    "on": {"type": "boolean"},
                    "mode": {
                        "type": "string",
                        "description": "e.g. Auto, Sleep, Favorite, Manual",
                    },
                    "fan_level": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["id_or_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_vacuum",
            "description": (
                "Control a Dreame (Dreamehome) robot vacuum: start cleaning, stop, "
                "or send it back to the dock."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["start", "stop", "home", "locate"],
                    },
                },
                "required": ["id_or_name", "action"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@dataclass
class ToolContext:
    homekit_url: str = HOMEKIT_URL
    voice_url: str = "http://127.0.0.1:8765"
    devices_url: str = "http://127.0.0.1:8002"
    http: httpx.AsyncClient | None = None

    def client(self) -> httpx.AsyncClient:
        # Do not `async with` this — closing would kill the shared session.
        if self.http is None or self.http.is_closed:
            self.http = httpx.AsyncClient(timeout=30.0)
        return self.http


async def _find_by_name(ctx: ToolContext, name_or_id: str) -> dict[str, Any] | None:
    """Resolve an accessory by name (case-insensitive) or id."""
    c = ctx.client()
    r = await c.get(f"{ctx.homekit_url}/accessories")
    r.raise_for_status()
    data = r.json()
    items = (data.get("data") or [])
    # try exact id first
    for it in items:
        if str(it.get("id")) == str(name_or_id):
            return it
    # fallback to case-insensitive name
    target = name_or_id.lower()
    for it in items:
        if (it.get("name") or "").lower() == target:
            return it
    # fallback to substring match
    for it in items:
        if target in (it.get("name") or "").lower():
            return it
    return None


async def tool_list_accessories(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        c = ctx.client()
        r = await c.get(f"{ctx.homekit_url}/accessories")
        r.raise_for_status()
        items = r.json().get("data") or []
        kind = args.get("kind")
        room = args.get("room")
        if kind:
            items = [i for i in items if i.get("kind") == kind]
        if room:
            room_l = room.lower()
            items = [i for i in items if room_l in (i.get("room") or "").lower()]
        return ToolResult(ok=True, data=items)
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_get_accessory(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        item = await _find_by_name(ctx, args["id_or_name"])
        if not item:
            return ToolResult(ok=False, error=f"accessory not found: {args['id_or_name']}")
        return ToolResult(ok=True, data=item)
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_set_light(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        item = await _find_by_name(ctx, args["id_or_name"])
        if not item:
            return ToolResult(ok=False, error=f"accessory not found: {args['id_or_name']}")
        aid = item["id"]
        c = ctx.client()
        r = await c.post(
            f"{ctx.homekit_url}/command",
            json={"target_id": aid, "action": "set_on", "args": {"value": args["on"]}},
        )
        r.raise_for_status()
        if args.get("brightness") is not None:
            r2 = await c.post(
                f"{ctx.homekit_url}/command",
                json={
                    "target_id": aid,
                    "action": "set_brightness",
                    "args": {"value": args["brightness"]},
                },
            )
            r2.raise_for_status()
        return ToolResult(ok=True, data={"id": aid, "on": args["on"], "brightness": args.get("brightness")})
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_set_thermostat(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        item = await _find_by_name(ctx, args["id_or_name"])
        if not item:
            return ToolResult(ok=False, error=f"accessory not found: {args['id_or_name']}")
        c = ctx.client()
        r = await c.post(
            f"{ctx.homekit_url}/command",
            json={
                "target_id": item["id"],
                "action": "set_target_temperature",
                "args": {"value": args["target_celsius"]},
            },
        )
        r.raise_for_status()
        return ToolResult(ok=True, data={"id": item["id"], "target_celsius": args["target_celsius"]})
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_set_lock(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        item = await _find_by_name(ctx, args["id_or_name"])
        if not item:
            return ToolResult(ok=False, error=f"accessory not found: {args['id_or_name']}")
        c = ctx.client()
        r = await c.post(
            f"{ctx.homekit_url}/command",
            json={
                "target_id": item["id"],
                "action": "set_lock",
                "args": {"value": args["locked"]},
            },
        )
        r.raise_for_status()
        return ToolResult(ok=True, data={"id": item["id"], "locked": args["locked"]})
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_trigger_scene(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        c = ctx.client()
        r = await c.post(f"{ctx.homekit_url}/scene", json={"name": args["name"]})
        r.raise_for_status()
        return ToolResult(ok=True, data={"triggered": args["name"]})
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_speak_to_homepod(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Tell the voice bridge to TTS the text on the chosen HomePod."""
    try:
        c = ctx.client()
        r = await c.post(
            f"{ctx.voice_url}/tts",
            json={"text": args["text"], "home_pod_room": args.get("room")},
            timeout=10.0,
        )
        r.raise_for_status()
        return ToolResult(ok=True, data={"spoke": args["text"]})
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_search_history(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        name_or_id = args.get("accessory_id_or_name")
        params: dict[str, Any] = {"limit": args.get("limit", 50)}
        if name_or_id:
            item = await _find_by_name(ctx, name_or_id)
            if not item:
                return ToolResult(ok=False, error=f"accessory not found: {name_or_id}")
            params["accessory_id"] = item["id"]
        c = ctx.client()
        r = await c.get(f"{ctx.homekit_url}/history", params=params)
        r.raise_for_status()
        return ToolResult(ok=True, data=r.json().get("data"))
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def _find_device(ctx: ToolContext, name_or_id: str) -> dict[str, Any] | None:
    c = ctx.client()
    r = await c.get(f"{ctx.devices_url}/devices")
    r.raise_for_status()
    items = r.json().get("data") or []
    for it in items:
        if str(it.get("id")) == str(name_or_id):
            return it
    target = name_or_id.lower()
    for it in items:
        if (it.get("name") or "").lower() == target:
            return it
    for it in items:
        if target in (it.get("name") or "").lower() or target in str(it.get("id", "")).lower():
            return it
    return None


async def tool_list_devices(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        c = ctx.client()
        r = await c.get(f"{ctx.devices_url}/devices")
        r.raise_for_status()
        items = r.json().get("data") or []
        kind = args.get("kind")
        if kind:
            items = [i for i in items if i.get("kind") == kind]
        return ToolResult(ok=True, data=items)
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_set_air_purifier(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        item = await _find_device(ctx, args["id_or_name"])
        if not item:
            return ToolResult(ok=False, error=f"device not found: {args['id_or_name']}")
        did = item["id"]
        results = []
        c = ctx.client()
        if "on" in args:
            action = "on" if args["on"] else "off"
            r = await c.post(
                f"{ctx.devices_url}/devices/{did}/command",
                json={"action": action, "args": {}},
            )
            r.raise_for_status()
            results.append(r.json())
        if args.get("mode"):
            r = await c.post(
                f"{ctx.devices_url}/devices/{did}/command",
                json={"action": "set_mode", "args": {"mode": args["mode"]}},
            )
            r.raise_for_status()
            results.append(r.json())
        if args.get("fan_level") is not None:
            r = await c.post(
                f"{ctx.devices_url}/devices/{did}/command",
                json={
                    "action": "set_fan_level",
                    "args": {"level": args["fan_level"]},
                },
            )
            r.raise_for_status()
            results.append(r.json())
        if not results:
            return ToolResult(ok=False, error="nothing to do — pass on, mode, or fan_level")
        return ToolResult(ok=True, data={"id": did, "results": results})
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


async def tool_control_vacuum(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        item = await _find_device(ctx, args["id_or_name"])
        if not item:
            return ToolResult(ok=False, error=f"device not found: {args['id_or_name']}")
        did = item["id"]
        action = args["action"]
        c = ctx.client()
        r = await c.post(
            f"{ctx.devices_url}/devices/{did}/command",
            json={"action": action, "args": {}},
        )
        r.raise_for_status()
        body = r.json()
        return ToolResult(ok=bool(body.get("ok", True)), data=body.get("data"), error=body.get("error"))
    except Exception as e:
        return ToolResult(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

HANDLERS: dict[str, Callable[..., Any]] = {
    "list_accessories": tool_list_accessories,
    "get_accessory": tool_get_accessory,
    "set_light": tool_set_light,
    "set_thermostat": tool_set_thermostat,
    "set_lock": tool_set_lock,
    "trigger_scene": tool_trigger_scene,
    "speak_to_homepod": tool_speak_to_homepod,
    "search_history": tool_search_history,
    "list_devices": tool_list_devices,
    "set_air_purifier": tool_set_air_purifier,
    "control_vacuum": tool_control_vacuum,
}


async def run_tool(name: str, args: dict[str, Any], ctx: ToolContext | None = None) -> ToolResult:
    ctx = ctx or ToolContext()
    handler = HANDLERS.get(name)
    if not handler:
        return ToolResult(ok=False, error=f"unknown tool: {name}")
    log.info("tool.call", name=name, args=args)
    try:
        result = await handler(ctx, args)
        log.info("tool.result", name=name, ok=result.ok)
        return result
    except Exception as e:
        log.error("tool.failed", name=name, error=str(e))
        return ToolResult(ok=False, error=str(e))


def tool_names() -> list[str]:
    return list(HANDLERS.keys())


# Pretty-print the tool schema as JSON (useful for prompts)
def schema_json() -> str:
    return json.dumps(TOOL_SCHEMAS, indent=2)