"""Tests for the LLM tool schema and dispatcher."""

from __future__ import annotations

import pytest

from llm.tools import TOOL_SCHEMAS, HANDLERS, run_tool, tool_names


@pytest.mark.asyncio
async def test_tool_names_present() -> None:
    names = tool_names()
    assert "list_accessories" in names
    assert "set_light" in names
    assert "trigger_scene" in names
    assert "speak_to_homepod" in names


def test_schema_is_well_formed() -> None:
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "parameters" in schema["function"]
        assert schema["function"]["parameters"]["type"] == "object"


@pytest.mark.asyncio
async def test_unknown_tool() -> None:
    res = await run_tool("nope", {})
    assert not res.ok
    assert "unknown" in (res.error or "")


@pytest.mark.asyncio
async def test_handler_registry_matches_schemas() -> None:
    schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    handler_names = set(HANDLERS.keys())
    missing = schema_names - handler_names
    extra = handler_names - schema_names
    assert not missing, f"schemas without handlers: {missing}"
    assert not extra, f"handlers without schemas: {extra}"