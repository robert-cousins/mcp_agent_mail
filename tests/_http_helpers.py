"""Shared helpers for HTTP integration tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from httpx import ASGITransport, AsyncClient


@asynccontextmanager
async def http_test_client(app: Any, **client_kwargs: Any):
    """Create an ``AsyncClient`` with the FastAPI app's ASGI lifespan entered.

    ``httpx.ASGITransport`` does **not** send ASGI lifespan events, so the
    MCP session-manager task group is never initialised and authenticated
    requests that reach the MCP layer hang forever on the zero-buffer
    memory-object stream.

    This helper enters the composed lifespan (MCP ``_lifespan_manager`` +
    ``StreamableHTTPSessionManager.run()``) before yielding the client and
    tears it down cleanly afterwards.

    Usage::

        app = build_http_app(settings, server)
        async with http_test_client(app) as client:
            resp = await client.post("/mcp/", ...)
    """
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        merged: dict[str, Any] = {"base_url": "http://test", "timeout": 5.0}
        merged.update(client_kwargs)
        async with AsyncClient(transport=transport, **merged) as client:
            yield client
