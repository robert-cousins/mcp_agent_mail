
import pytest
from fastmcp import Client
from mcp_agent_mail.app import build_mcp_server
from mcp_agent_mail.db import get_session

@pytest.mark.asyncio
async def test_reproduce_granted_plus_conflicts(isolated_env):
    """Bug reproduction: Response includes both 'granted' and 'conflicts' for the same path."""
    server = build_mcp_server()
    async with Client(server) as client:
        project_key = "/test/res/race"
        await client.call_tool("ensure_project", {"human_key": project_key})

        # Register two agents
        a1 = await client.call_tool("register_agent", {"project_key": project_key, "program": "a1", "model": "m1"})
        agent1_name = a1.data["name"]
        a2 = await client.call_tool("register_agent", {"project_key": project_key, "program": "a2", "model": "m2"})
        agent2_name = a2.data["name"]

        # Agent 1 takes exclusive lock
        res1 = await client.call_tool(
            "file_reservation_paths",
            {
                "project_key": project_key,
                "agent_name": agent1_name,
                "paths": ["conflict.txt"],
                "exclusive": True,
            },
        )
        assert len(res1.data["granted"]) == 1
        assert len(res1.data.get("conflicts", [])) == 0

        # Agent 2 tries to take exclusive lock on SAME path
        res2 = await client.call_tool(
            "file_reservation_paths",
            {
                "project_key": project_key,
                "agent_name": agent2_name,
                "paths": ["conflict.txt"],
                "exclusive": True,
            },
        )

        # Expected BUG (per PearlCove): It is BOTH granted AND has conflicts
        # We want to eventually FIX this so it is NOT granted if there is a conflict.
        
        has_granted = any(g["path_pattern"] == "conflict.txt" for g in res2.data.get("granted", []))
        has_conflict = any(c["path"] == "conflict.txt" for c in res2.data.get("conflicts", []))
        
        assert has_conflict, "Should have reported a conflict"
        assert not has_granted, "BUG: Should NOT have granted a conflicting exclusive lock"
        
        # Verify NO double-exclusive in DB
        async with get_session() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT COUNT(*) FROM file_reservations WHERE path_pattern = 'conflict.txt' AND released_ts IS NULL")
            )
            count = result.scalar()
            assert count == 1, f"BUG: Should have exactly ONE active reservation in DB, found {count}"
