import json
from typing import Any

import pytest
from fastmcp import Client

from mcp_agent_mail.app import build_mcp_server
from mcp_agent_mail.config import clear_settings_cache
from mcp_agent_mail.db import ensure_schema, reset_database_state


def _tool_data(result: Any) -> Any:
    data = getattr(result, "data", result)
    structured = getattr(result, "structured_content", None)
    if (
        isinstance(structured, dict)
        and "result" in structured
        and isinstance(data, list)
        and data
        and type(data[0]).__name__ == "Root"
    ):
        return structured["result"]
    return data


@pytest.mark.asyncio
async def test_ensure_product_and_link_project(tmp_path, monkeypatch) -> None:
    # Enable gated features for product bus
    monkeypatch.setenv("WORKTREES_ENABLED", "1")
    clear_settings_cache()
    reset_database_state()
    await ensure_schema()
    # Ensure product (unique ids to avoid cross-run collisions)
    unique = "_prod_" + hex(hash(str(tmp_path)) & 0xFFFFF)[2:]

    server = build_mcp_server()
    async with Client(server) as client:
        prod = _tool_data(
            await client.call_tool("ensure_product", {"product_key": f"my-product{unique}", "name": f"My Product{unique}"})
        )
        assert prod["product_uid"]
        # Ensure project exists for linking
        project_result = _tool_data(
            await client.call_tool("ensure_project", {"human_key": str(tmp_path)})
        )
        slug = project_result.get("slug") or project_result["project"]["slug"]
        # Link
        link = _tool_data(
            await client.call_tool("products_link", {"product_key": prod["product_uid"], "project_key": slug})
        )
        assert link["linked"] is True
        # Product resource lists the project
        res_list = await client.read_resource(f"resource://product/{prod['product_uid']}?format=json")
        assert res_list and res_list[0].text
        payload = json.loads(res_list[0].text)
        assert any(p["slug"] == slug for p in payload.get("projects", []))
