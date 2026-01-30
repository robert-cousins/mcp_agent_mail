#!/usr/bin/env python3
"""Measure MCP Agent Mail token/context overhead for before/after comparison."""

import json
import subprocess
import time
from pathlib import Path

from decouple import Config as DecoupleConfig, RepositoryEnv

# Load config
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    decouple_config = DecoupleConfig(RepositoryEnv(str(env_path)))
    SERVER_URL = decouple_config("API_BASE_URL", default="http://127.0.0.1:8765") + "/mcp/"
    BEARER_TOKEN = decouple_config("STATIC_BEARER_TOKEN", default="")
else:
    SERVER_URL = "http://127.0.0.1:8765/mcp/"
    BEARER_TOKEN = ""

CHARS_PER_TOKEN = 4  # Rough estimate for English text


def call_mcp(method: str, params: dict | None = None) -> tuple[dict, float, int]:
    """Call MCP method, return (response, latency_ms, byte_count)."""
    payload = {
        "jsonrpc": "2.0",
        "id": f"measure-{method}",
        "method": method,
        "params": params or {},
    }
    headers = ["Content-Type: application/json"]
    if BEARER_TOKEN:
        headers.append(f"Authorization: Bearer {BEARER_TOKEN}")

    cmd = ["curl", "-s", "-X", "POST", SERVER_URL]
    for h in headers:
        cmd.extend(["-H", h])
    cmd.extend(["-d", json.dumps(payload)])

    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    latency = (time.perf_counter() - start) * 1000

    return json.loads(result.stdout), latency, len(result.stdout)


def measure_tools_list() -> dict:
    """Measure the tools/list payload."""
    resp, latency, byte_count = call_mcp("tools/list")
    tools = resp.get("result", {}).get("tools", [])

    # Calculate description lengths
    total_desc_chars = sum(len(t.get("description", "")) for t in tools)
    total_schema_chars = sum(len(json.dumps(t.get("inputSchema", {}))) for t in tools)

    return {
        "tool_count": len(tools),
        "total_bytes": byte_count,
        "estimated_tokens": byte_count // CHARS_PER_TOKEN,
        "description_chars": total_desc_chars,
        "description_tokens": total_desc_chars // CHARS_PER_TOKEN,
        "schema_chars": total_schema_chars,
        "latency_ms": round(latency, 2),
        "tools": [t.get("name") for t in tools],
    }


def measure_workflow_latency(project_key: str = "/tmp/mcp-measure-test") -> dict:
    """Measure a typical 3-call workflow."""
    timings = []

    # ensure_project
    _, lat, _ = call_mcp("tools/call", {"name": "ensure_project", "arguments": {"human_key": project_key}})
    timings.append(("ensure_project", lat))

    # register_agent
    resp, lat, _ = call_mcp(
        "tools/call",
        {"name": "register_agent", "arguments": {"project_key": project_key, "program": "measure", "model": "test"}},
    )
    timings.append(("register_agent", lat))
    agent_name = resp.get("result", {}).get("structuredContent", {}).get("name", "Unknown")

    # fetch_inbox
    _, lat, _ = call_mcp(
        "tools/call", {"name": "fetch_inbox", "arguments": {"project_key": project_key, "agent_name": agent_name}}
    )
    timings.append(("fetch_inbox", lat))

    return {
        "total_latency_ms": round(sum(t[1] for t in timings), 2),
        "call_count": len(timings),
        "avg_latency_ms": round(sum(t[1] for t in timings) / len(timings), 2),
        "breakdown": {name: round(lat, 2) for name, lat in timings},
    }


def main():
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.rule("[bold blue]MCP Agent Mail Token Overhead Measurement[/]")

    # Measure tools/list
    console.print("\n[cyan]Measuring tools/list payload...[/]")
    tools_metrics = measure_tools_list()

    table = Table(title="Tool Catalog Metrics")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Tool count", str(tools_metrics["tool_count"]))
    table.add_row("Total payload bytes", f"{tools_metrics['total_bytes']:,}")
    table.add_row("Estimated tokens", f"{tools_metrics['estimated_tokens']:,}")
    table.add_row("Description chars", f"{tools_metrics['description_chars']:,}")
    table.add_row("Description tokens", f"{tools_metrics['description_tokens']:,}")
    table.add_row("Latency (ms)", str(tools_metrics["latency_ms"]))
    console.print(table)

    # Measure workflow latency
    console.print("\n[cyan]Measuring 3-call workflow latency...[/]")
    workflow_metrics = measure_workflow_latency()

    table2 = Table(title="Workflow Latency (ensure_project → register_agent → fetch_inbox)")
    table2.add_column("Call", style="bold")
    table2.add_column("Latency (ms)", justify="right")
    for name, lat in workflow_metrics["breakdown"].items():
        table2.add_row(name, str(lat))
    table2.add_row("[bold]Total[/]", f"[bold]{workflow_metrics['total_latency_ms']}[/]")
    console.print(table2)

    # Summary
    console.print("\n[bold green]Summary for before/after comparison:[/]")
    console.print(f"  • Tools exposed: {tools_metrics['tool_count']}")
    console.print(f"  • Context overhead: ~{tools_metrics['estimated_tokens']:,} tokens")
    console.print(f"  • 3-call workflow: {workflow_metrics['total_latency_ms']}ms ({workflow_metrics['call_count']} round trips)")

    # Save to JSON for comparison
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tools": tools_metrics,
        "workflow": workflow_metrics,
    }
    output_path = Path(__file__).parent / "token_overhead_metrics.json"
    output_path.write_text(json.dumps(output, indent=2))
    console.print(f"\n[dim]Metrics saved to {output_path}[/]")


if __name__ == "__main__":
    main()
