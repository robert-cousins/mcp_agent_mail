#!/usr/bin/env python3
"""
MCP Agent Mail Watcher Client — real-time notification sidecar.

Watches for new-message signals (via SSE or file polling) and reacts with
visible alerts, automatic inbox fetches, and/or custom hook commands.

Modes
-----
1. **SSE** (recommended): Connects to the server's ``/sse/events`` endpoint.
2. **File Polling**: Watches ``.signal`` files on the local filesystem.

Notification Features
---------------------
--dev-notify    Print a human-visible alert line with terminal bell on each
                new message.  Example output::

                    🔔 New mail for MyAgent in my-project: Alice — Re: deploy plan (id=42)

--auto-fetch    After each notification, fetch the latest message from the
                server and print a short summary (subject/from/importance).
                Add ``--show-body`` to include the full message body.

--on-notify CMD Execute *CMD* as a shell command for every notification.
                The following environment variables are set::

                    AM_PROJECT, AM_AGENT, AM_MESSAGE_ID,
                    AM_FROM, AM_SUBJECT, AM_IMPORTANCE

--buffer-file PATH  Update a local markdown file with a summary of pending
                    notifications. This allows agents to 'see' unread mail
                    by checking this file at the start of their turn.

--sentinel-file PATH  Write a JSON sentinel file on each notification.
                      A PreToolUse hook (check_notifications.sh) reads this
                      file and injects "you have mail" into the agent's
                      context before every tool call.  The hook consumes
                      (deletes) the file after reading, so the agent is
                      only notified once per message.

Examples
--------
Run as a terminal sidecar with alerts + auto-fetch::

    uv run python scripts/watch_mail.py \\
        --method sse --project data-projects-mcp-agent-mail \\
        --agent SapphireOtter --url http://127.0.0.1:8765 \\
        --token "$HTTP_BEARER_TOKEN" \\
        --dev-notify --auto-fetch

Fire a custom hook on each notification::

    uv run python scripts/watch_mail.py \\
        --method sse --project my-project --agent MyAgent \\
        --url http://127.0.0.1:8765 --token "$TOKEN" \\
        --on-notify 'notify-send "New mail from $AM_FROM: $AM_SUBJECT"'

Bridge notifications into Claude Code agent context via sentinel::

    uv run python scripts/watch_mail.py \\
        --method sse --project data-projects-mcp-agent-mail \\
        --agent SapphireOtter --url http://127.0.0.1:8765 \\
        --token "$HTTP_BEARER_TOKEN" \\
        --dev-notify --sentinel-file /tmp/mcp-mail-pending-SapphireOtter.json

Run with file-polling fallback (no SSE dependency)::

    uv run python scripts/watch_mail.py \\
        --method file --project my-project --agent MyAgent \\
        --dev-notify --auto-fetch
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import httpx
import typer
from rich.console import Console

app = typer.Typer(help="MCP Agent Mail Watcher Client")
console = Console()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("watcher")

# ---------------------------------------------------------------------------
# De-duplication state
# ---------------------------------------------------------------------------
_last_seen_message_id: int = 0
_last_seen_timestamp: str = ""


def _is_duplicate(message_id: int, timestamp: str) -> bool:
    """Return True if this event was already processed (dedup guard)."""
    global _last_seen_message_id, _last_seen_timestamp
    if message_id and message_id <= _last_seen_message_id:
        return True
    if timestamp and timestamp == _last_seen_timestamp and message_id == _last_seen_message_id:
        return True
    if message_id:
        _last_seen_message_id = message_id
    if timestamp:
        _last_seen_timestamp = timestamp
    return False


# ---------------------------------------------------------------------------
# Notification actions
# ---------------------------------------------------------------------------

def _dev_notify(project: str, agent: str, data: dict) -> None:
    """Print a human-visible alert with terminal bell."""
    msg = data.get("message") or {}
    msg_id = msg.get("id", "?")
    sender = msg.get("from", "unknown")
    subject = msg.get("subject", "(no subject)")
    importance = msg.get("importance", "normal")

    prefix = "🔴 " if importance in ("high", "urgent") else ""
    line = f"🔔 {prefix}New mail for {agent} in {project}: {sender} — {subject} (id={msg_id})"
    console.print(f"[bold yellow]{line}[/bold yellow]")
    # Terminal bell
    sys.stdout.write("\a")
    sys.stdout.flush()


async def _auto_fetch(
    project: str, agent: str, url: str, token: Optional[str], show_body: bool,
) -> None:
    """Fetch the latest inbox message and print a summary."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "fetch_inbox",
            "arguments": {
                "project_key": project,
                "agent_name": agent,
                "limit": 1,
                "include_bodies": show_body,
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{url}/mcp/", json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()

        # Navigate the JSON-RPC response
        rpc_result = result.get("result", {})
        messages = None

        # Try structuredContent first (has parsed objects)
        if isinstance(rpc_result, dict) and "structuredContent" in rpc_result:
            sc = rpc_result["structuredContent"]
            messages = sc.get("result") if isinstance(sc, dict) else None

        # Fallback: parse from text content block
        if messages is None and isinstance(rpc_result, dict) and "content" in rpc_result:
            for block in rpc_result["content"]:
                if block.get("type") == "text":
                    inner = json.loads(block["text"])
                    # May be a list directly or wrapped in {"result": [...]}
                    if isinstance(inner, list):
                        messages = inner
                    elif isinstance(inner, dict):
                        messages = inner.get("result", [])
                    break

        if messages:
            m = messages[0]
            console.print(f"  [cyan]Latest:[/cyan] [bold]{m.get('subject', '?')}[/bold] from {m.get('from', '?')} [{m.get('importance', 'normal')}]")
            if show_body and m.get("body_md"):
                body_preview = m["body_md"][:300]
                console.print(f"  [dim]{body_preview}[/dim]")
        elif messages is not None:
            console.print("  [dim](inbox empty)[/dim]")
        else:
            console.print("  [dim](could not parse inbox response)[/dim]")
    except Exception as e:
        console.print(f"  [red]Auto-fetch error:[/red] {e}")


def _run_on_notify(command: str, project: str, agent: str, data: dict) -> None:
    """Execute a user-supplied hook command with notification env vars."""
    msg = data.get("message") or {}
    env = {
        **os.environ,
        "AM_PROJECT": project,
        "AM_AGENT": agent,
        "AM_MESSAGE_ID": str(msg.get("id", "")),
        "AM_FROM": str(msg.get("from", "")),
        "AM_SUBJECT": str(msg.get("subject", "")),
        "AM_IMPORTANCE": str(msg.get("importance", "")),
    }
    try:
        subprocess.Popen(command, shell=True, env=env)
    except Exception as e:
        console.print(f"[red]on-notify hook error:[/red] {e}")


def _update_buffer_file(path: str, project: str, agent: str, data: dict) -> None:
    """Update a markdown buffer file with the latest notification summary."""
    msg = data.get("message") or {}
    msg_id = msg.get("id", "?")
    sender = msg.get("from", "unknown")
    subject = msg.get("subject", "(no subject)")
    importance = msg.get("importance", "normal")
    ts = data.get("timestamp", "unknown")

    p = Path(path)
    header = (
        "# 🔔 Pending Agent Mail\n\n"
        "*This file is automatically maintained by the watch_mail.py sidecar. "
        "Agents should check this file at the start of every session.*\n\n"
        "| Agent | Project | From | Subject | Importance | Received | ID |\n"
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
    )

    row = f"| {agent} | {project} | {sender} | {subject} | {importance} | {ts} | {msg_id} |\n"

    try:
        if not p.exists():
            p.write_text(header + row, encoding="utf-8")
        else:
            lines = p.read_text(encoding="utf-8").splitlines()
            # If the file exists but doesn't have our header, just overwrite
            if not lines or "# 🔔 Pending Agent Mail" not in lines[0]:
                p.write_text(header + row, encoding="utf-8")
            else:
                # Add as new row if not already present
                if row not in lines:
                    p.write_text("\n".join(lines) + "\n" + row, encoding="utf-8")
    except Exception as e:
        console.print(f"[red]buffer-file update error:[/red] {e}")


def _write_sentinel(path: str, data: dict) -> None:
    """Write a JSON sentinel file for the PreToolUse hook to pick up."""
    msg = data.get("message") or {}
    sentinel = {
        "id": msg.get("id", ""),
        "from": msg.get("from", ""),
        "subject": msg.get("subject", ""),
        "importance": msg.get("importance", "normal"),
        "timestamp": data.get("timestamp", ""),
    }
    try:
        Path(path).write_text(json.dumps(sentinel), encoding="utf-8")
    except Exception as e:
        console.print(f"[red]sentinel-file write error:[/red] {e}")


async def _handle_event(
    data: dict,
    project: str,
    agent: str,
    dev_notify: bool,
    auto_fetch: bool,
    on_notify: Optional[str],
    buffer_file: Optional[str],
    sentinel_file: Optional[str],
    url: str,
    token: Optional[str],
    show_body: bool,
) -> None:
    """Central handler for a notification event (from SSE or file)."""
    msg = data.get("message") or {}
    message_id = msg.get("id", 0)
    timestamp = data.get("timestamp", "")

    if _is_duplicate(message_id, timestamp):
        return

    # Always print the raw signal if no specific action is enabled
    if not (dev_notify or auto_fetch or on_notify or buffer_file or sentinel_file):
        console.print(f"[bold green]New Signal:[/bold green] {data}")
        return

    if dev_notify:
        _dev_notify(project, agent, data)

    if auto_fetch:
        await _auto_fetch(project, agent, url, token, show_body)

    if on_notify:
        _run_on_notify(on_notify, project, agent, data)

    if buffer_file:
        _update_buffer_file(buffer_file, project, agent, data)

    if sentinel_file:
        _write_sentinel(sentinel_file, data)


# ---------------------------------------------------------------------------
# Signal path helper
# ---------------------------------------------------------------------------

def _get_signal_path(project_slug: str, agent_name: str) -> Path:
    """Get the path to the signal file."""
    signals_dir = Path("~/.mcp_agent_mail/signals").expanduser()
    if os.environ.get("NOTIFICATIONS_SIGNALS_DIR"):
        signals_dir = Path(os.environ["NOTIFICATIONS_SIGNALS_DIR"]).expanduser()
    return signals_dir / "projects" / project_slug / "agents" / f"{agent_name}.signal"


# ---------------------------------------------------------------------------
# Watchers
# ---------------------------------------------------------------------------

async def _watch_file_polling(
    project_slug: str,
    agent_name: str,
    interval: float,
    dev_notify: bool,
    auto_fetch: bool,
    on_notify: Optional[str],
    buffer_file: Optional[str],
    sentinel_file: Optional[str],
    url: str,
    token: Optional[str],
    show_body: bool,
):
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
                    await _handle_event(
                        data, project_slug, agent_name,
                        dev_notify, auto_fetch, on_notify, buffer_file,
                        sentinel_file, url, token, show_body,
                    )
                except Exception as e:
                    console.print(f"[red]Error reading signal file:[/red] {e}")

        await asyncio.sleep(interval)


async def _watch_sse(
    project_slug: str,
    agent_name: str,
    url: str,
    token: Optional[str],
    dev_notify: bool,
    auto_fetch: bool,
    on_notify: Optional[str],
    buffer_file: Optional[str],
    sentinel_file: Optional[str],
    show_body: bool,
):
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
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    console.print(f"[red]SSE connection failed:[/red] {response.status_code}")
                    await asyncio.sleep(retry_delay)
                    continue

                console.print("[green]Connected to SSE stream.[/green]")
                retry_delay = 1.0

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            await _handle_event(
                                data, project_slug, agent_name,
                                dev_notify, auto_fetch, on_notify, buffer_file,
                                sentinel_file, url, token, show_body,
                            )
                        except json.JSONDecodeError:
                            console.print(f"[yellow]Invalid JSON in SSE:[/yellow] {data_str}")

        except httpx.RemoteProtocolError:
            console.print("[yellow]Server disconnected, reconnecting...[/yellow]")
        except httpx.ConnectError:
            console.print(f"[red]Connection failed. Retrying in {retry_delay}s...[/red]")
        except Exception as e:
            console.print(f"[red]SSE Error:[/red] {e}")

        await asyncio.sleep(retry_delay)
        retry_delay = min(30.0, retry_delay * 1.5)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(
    project: Annotated[str, typer.Option("--project", "-p", help="Project slug")],
    agent: Annotated[str, typer.Option("--agent", "-a", help="Agent name")],
    method: Annotated[str, typer.Option("--method", "-m", help="Watch method: 'file' or 'sse'")] = "file",
    url: Annotated[str, typer.Option("--url", help="Base URL for server (e.g. http://localhost:8765)")] = "http://localhost:8765",
    interval: Annotated[float, typer.Option("--interval", help="Polling interval in seconds (file mode)")] = 2.0,
    token: Annotated[Optional[str], typer.Option("--token", envvar="MCP_AGENT_MAIL_TOKEN", help="Bearer token")] = None,
    dev_notify: Annotated[bool, typer.Option("--dev-notify", help="Print alert line + terminal bell on new messages")] = False,
    auto_fetch: Annotated[bool, typer.Option("--auto-fetch", help="Fetch and print latest message on notification")] = False,
    show_body: Annotated[bool, typer.Option("--show-body", help="Include message body in auto-fetch output")] = False,
    on_notify: Annotated[Optional[str], typer.Option("--on-notify", help="Shell command to run on notification (env: AM_PROJECT, AM_AGENT, AM_MESSAGE_ID, AM_FROM, AM_SUBJECT, AM_IMPORTANCE)")] = None,
    buffer_file: Annotated[Optional[str], typer.Option("--buffer-file", help="Path to a markdown file to update with pending notification summary")] = None,
    sentinel_file: Annotated[Optional[str], typer.Option("--sentinel-file", help="Path to JSON sentinel file for PreToolUse hook integration (consumed on read by check_notifications.sh)")] = None,
):
    """
    Watch for new mail notifications and react with alerts, fetches, or hooks.

    Run as a sidecar process in a terminal or IDE task runner for real-time
    awareness of incoming agent mail.
    """
    if method == "file":
        asyncio.run(_watch_file_polling(
            project, agent, interval,
            dev_notify, auto_fetch, on_notify, buffer_file,
            sentinel_file, url, token, show_body,
        ))
    elif method == "sse":
        asyncio.run(_watch_sse(
            project, agent, url, token,
            dev_notify, auto_fetch, on_notify, buffer_file,
            sentinel_file, show_body,
        ))
    else:
        console.print(f"[red]Unknown method: {method}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
