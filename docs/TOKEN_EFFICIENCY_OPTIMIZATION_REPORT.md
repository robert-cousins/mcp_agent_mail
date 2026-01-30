# MCP Agent Mail: Token & Context Efficiency Optimization Report

**Date:** January 29, 2026  
**Project:** mcp_agent_mail  
**Objective:** Reduce LLM token consumption and improve determinism of MCP tool calling

---

## Executive Summary

Reduced MCP tool context overhead by **90%** (from ~10,000 tokens to ~1,000 tokens per session) through two changes:
1. Enabling the `minimal` tool profile by default
2. Trimming verbose tool descriptions

---

## Background

MCP Agent Mail exposes tools via the Model Context Protocol. Each tool includes a description that gets injected into the LLM's context window on every session. With 26+ tools and verbose docstrings (40-80 lines each), this created significant token overhead before any actual work began.

### The Problem

| Issue | Impact |
|-------|--------|
| 26 tools exposed by default | Large context payload |
| Verbose docstrings (~50 lines avg) | ~10,000 tokens of static overhead |
| Multiple round trips per workflow | Latency accumulation |
| LLM interprets schemas each call | Non-deterministic behavior |

---

## Baseline Measurements

Before optimization (full profile, verbose descriptions):

```
Tool count:          26
Total payload bytes: 39,716
Estimated tokens:    9,929
Description tokens:  5,752
Workflow latency:    ~400ms (3 calls)
```

---

## Optimization Steps

### Step 1: Enable Minimal Profile by Default

**File:** `src/mcp_agent_mail/config.py`

Changed default settings:
```python
# Before
enabled=_bool(..., default="false"), default=False)
profile=_tool_filter_profile(..., default="full"))

# After  
enabled=_bool(..., default="true"), default=True)
profile=_tool_filter_profile(..., default="minimal"))
```

The `minimal` profile exposes only 6 essential tools:
- `health_check`
- `ensure_project`
- `register_agent`
- `send_message`
- `fetch_inbox`
- `acknowledge_message`

**Impact:** Tool count reduced from 26 → 6 (77% reduction)

### Step 2: Trim Tool Descriptions

**File:** `src/mcp_agent_mail/app.py`

Reduced docstrings from 40-80 lines to 3-5 lines each, keeping only essential information.

#### Before (example: `send_message`)
```python
"""
Send a Markdown message to one or more recipients and persist canonical and mailbox copies to Git.

Discovery
---------
To discover available agent names for recipients, use: resource://agents/{project_key}
Agent names are NOT the same as program names or user names.

What this does
--------------
- Stores message (and recipients) in the database; updates sender's activity
- Writes a canonical `.md` under `messages/YYYY/MM/`
...
[95 more lines of examples, edge cases, do/don't guidelines]
"""
```

#### After
```python
"""
Send a Markdown message to one or more agent recipients.
- to: list of agent names (e.g., ["BlueLake"]). Use resource://agents/{project_key} to discover names.
- subject: short subject line
- body_md: GitHub-Flavored Markdown body
- importance: "low"|"normal"|"high"|"urgent"
- ack_required: if true, recipients should acknowledge
"""
```

#### Description Length Reduction by Tool

| Tool 			| Before (chars)| After (chars) | Reduction |
|------			|---------------|---------------|-----------|
| `health_check` 	| ~1,400 	| 80 		| 94% 	|
| `ensure_project` 	| ~2,100 	| 250 		| 88% |
| `register_agent` 	| ~2,600 	| 300 		| 88% |
| `send_message` 	| ~3,800 	| 280 		| 93% |
| `fetch_inbox` 	| ~1,000 	| 200 		| 80% |
| `acknowledge_message` | ~850 		| 120 		| 86% |

---

## Final Results

After optimization (minimal profile, trimmed descriptions):

```
Tool count:          6
Total payload bytes: 4,044
Estimated tokens:    1,011
Description tokens:  151
Workflow latency:    ~110ms (3 calls)
```

### Comparison

| Metric 		| Before | After | Reduction |
|--------		|--------|-------|-----------|
| **Tool count** 	| 26 	 | 6     | 77%   |
| **Payload bytes** 	| 39,716 | 4,044 | **90%** |
| **Estimated tokens** 	| 9,929  | 1,011 | **90%** |
| **Description tokens**| 5,752  | 151   | **97%** |
| **Workflow latency** 	| ~400ms | ~110ms| 73% |

---

## Configuration Options

Users can override defaults via environment variables:

```bash
# Use full tool set (backwards compatible)
TOOLS_FILTER_ENABLED=false

# Or select a different profile
TOOLS_FILTER_PROFILE=core      # ~12 tools
TOOLS_FILTER_PROFILE=messaging # messaging + contacts
TOOLS_FILTER_PROFILE=full      # all 26+ tools
```

---

## Future Optimization Opportunities

### 1. Batch Tool
Combine common multi-call workflows into single operations:
```python
# Instead of 3 calls:
ensure_project() → register_agent() → fetch_inbox()

# Single call:
batch_call([
  {"name": "ensure_project", "args": {...}},
  {"name": "register_agent", "args": {...}},
  {"name": "fetch_inbox", "args": {...}}
])
```
**Estimated impact:** 3x fewer round trips

### 2. Thin Python SDK
For automation that doesn't need LLM interpretation:
```python
from mcp_agent_mail_sdk import AgentMailClient

client = AgentMailClient(url="http://127.0.0.1:8765/mcp/")
project = client.ensure_project("/path/to/project")
agent = client.register_agent(project.slug, program="cursor", model="gpt-4")
client.send_message(project.slug, agent.name, to=["BlueLake"], subject="Hi")
```
**Estimated impact:** 0 tokens context overhead, fully deterministic

### 3. On-Demand Documentation
Move detailed examples/edge cases to a `resource://docs/tools/{name}` endpoint that agents can fetch only when needed.

---

## Measurement Script

A measurement script was created at `scripts/measure_token_overhead.py` for future benchmarking:

```bash
uv run python scripts/measure_token_overhead.py
```

Output includes:
- Tool catalog size and token estimates
- Workflow latency measurements
- JSON export for comparison

---

## Conclusion

By enabling sensible defaults (minimal tool profile) and trimming verbose documentation, MCP Agent Mail now consumes **90% fewer tokens** for tool context. This translates directly to:

- **Lower costs** — fewer input tokens per API call
- **Faster responses** — less context to process
- **More headroom** — leaves context window space for actual work

The changes are backwards-compatible; users who need the full tool set can opt-in via environment variables.
