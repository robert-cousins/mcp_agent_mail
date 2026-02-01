#!/usr/bin/env python3
"""
Reference Watcher Client for MCP Agent Mail.

Supports two modes:
1. File Polling: Watches .signal files.
2. SSE: Connects to the server's SSE endpoint.

Usage:
  python scripts/watch_mail.py watch --project my-project --agent MyAgent --method sse --url http://127.0.0.1:8000
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Annotated, Optional

import httpx
import typer
from rich.console import Console

app = typer.Typer(help="MCP Agent Mail Watcher Client")
console = Console()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("watcher")


def _get_signal_path(project_slug: str, agent_name: str) -> Path:
    """Get the path to the signal file."""
    # Assuming standard location ~/.mcp_agent_mail/signals
    # Ideally this reads from .env or shared config, but for a reference client, default is fine.
    signals_dir = Path("~/.mcp_agent_mail/signals").expanduser()
    if os.environ.get("NOTIFICATIONS_SIGNALS_DIR"):
        signals_dir = Path(os.environ["NOTIFICATIONS_SIGNALS_DIR"]).expanduser()

    return signals_dir / "projects" / project_slug / "agents" / f"{agent_name}.signal"


async def _watch_file_polling(project_slug: str, agent_name: str, interval: float):
    """Watch for signal file changes via polling."""
    signal_path = _get_signal_path(project_slug, agent_name)
    console.print(f"[cyan]Polling file:[/cyan] {signal_path} (every {interval}s)")

    last_mtime = 0.0
    if signal_path.exists():
        last_mtime = signal_path.stat().st_mtime

    while True:
        if signal_path.exists():
            current_mtime = signal_path.stat().st_mtime
            if current_mtime > last_mtime:
                last_mtime = current_mtime
                try:
                    content = signal_path.read_text(encoding="utf-8")
                    data = json.loads(content)
                    console.print(f"[green]New Signal (File):[/green] {data}")
                    # In a real agent, you would trigger 'fetch_inbox' here
                except Exception as e:
                    console.print(f"[red]Error reading signal file:[/red] {e}")

        await asyncio.sleep(interval)


async def _watch_sse(project_slug: str, agent_name: str, url: str, token: Optional[str]):
    """Watch via SSE."""
    console.print(f"[cyan]Connecting to SSE:[/cyan] {url}/sse/events")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=None)

    retry_delay = 1.0

    while True:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client, client.stream(
                "GET",
                f"{url}/sse/events",
                params={"project_slug": project_slug, "agent_name": agent_name},
                headers=headers
            ) as response:
                if response.status_code != 200:
                    console.print(f"[red]SSE connection failed:[/red] {response.status_code}")
                    await asyncio.sleep(retry_delay)
                    continue

                console.print("[green]Connected to SSE stream.[/green]")
                retry_delay = 1.0 # Reset retry delay on success

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            console.print(f"[bold green]New Signal (SSE):[/bold green] {data}")
                        except json.JSONDecodeError:
                            console.print(f"[yellow]Invalid JSON in SSE:[/yellow] {data_str}")
                    if line.startswith("event: "):
                         pass # handle event types if needed

        except httpx.RemoteProtocolError:
             console.print("[yellow]Server disconnected, reconnecting...[/yellow]")
        except httpx.ConnectError:
             console.print(f"[red]Connection failed. Retrying in {retry_delay}s...[/red]")
        except Exception as e:
            console.print(f"[red]SSE Error:[/red] {e}")

        await asyncio.sleep(retry_delay)
        retry_delay = min(30.0, retry_delay * 1.5)


def main(
    project: Annotated[str, typer.Option("--project", "-p", help="Project slug")],
    agent: Annotated[str, typer.Option("--agent", "-a", help="Agent name")],
    method: Annotated[str, typer.Option("--method", "-m", help="Watch method: 'file' or 'sse'")] = "file",
    url: Annotated[str, typer.Option("--url", help="Base URL for SSE (e.g. http://localhost:8000)")] = "http://localhost:8000",
    interval: Annotated[float, typer.Option("--interval", help="Polling interval in seconds")] = 2.0,
    token: Annotated[Optional[str], typer.Option("--token", envvar="MCP_AGENT_MAIL_TOKEN", help="Bearer token")] = None,
):
    """
    Watch for new mail notifications.
    """
    if method == "file":
        asyncio.run(_watch_file_polling(project, agent, interval))
    elif method == "sse":
        asyncio.run(_watch_sse(project, agent, url, token))
    else:
        console.print(f"[red]Unknown method: {method}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
