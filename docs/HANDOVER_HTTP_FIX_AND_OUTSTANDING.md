# Handover: HTTP Test Fix & Outstanding CI Failures

**Branch**: `fix/chatgpt-mcp-compatibility`
**Fork**: `robert-cousins/mcp_agent_mail` (upstream: `Dicklesworthstone/mcp_agent_mail`)
**Date**: 2026-01-30
**Latest commit**: `f47f857` — `fix: resolve HTTP test hangs by delegating to SDK session manager`

---

## 1. Background

PR #2 converts HTTP middlewares from `BaseHTTPMiddleware` subclasses to pure ASGI callables for ChatGPT Desktop MCP compatibility. The branch also carries uncommitted changes to `app.py` (tool docstring refactoring) and `config.py` (tool filter defaults).

After the initial middleware conversion, all HTTP tests that authenticated successfully and reached the MCP layer hung indefinitely in CI. This blocked the PR.

---

## 2. Root Cause of HTTP Test Hangs (RESOLVED)

### The Problem

`StatelessMCPASGIApp` in `http.py` (lines 1097-1148, now removed) created its own `StreamableHTTPServerTransport` and called `self._server._mcp_server.run()` directly via `asyncio.create_task()`. This bypassed FastMCP's `_lifespan_manager`, which is required to set `_lifespan_result_set = True`.

The chain of failure:

1. `_mcp_server.run()` enters `_lifespan_proxy` (fastmcp/server/server.py:124-145)
2. `_lifespan_proxy` checks `_lifespan_result_set` — finds it `False`
3. Raises `RuntimeError("FastMCP server has a lifespan defined but no lifespan result is set")`
4. Error is silently swallowed by anyio's ExceptionGroup handling
5. `_receive_loop` never starts
6. `writer.send()` on the zero-buffer `anyio.MemoryObjectStream(0)` blocks forever — **deadlock**

Additionally, all HTTP tests used `AsyncClient(transport=ASGITransport(app=app))`. The `ASGITransport` class does **not** send ASGI lifespan events, so even the correctly-composed `lifespan_context` (which enters `mcp_http_app.lifespan()` → `_lifespan_manager()` + `session_manager.run()`) was never triggered.

### The Fix (commit `f47f857`)

Three coordinated changes:

#### 2a. `src/mcp_agent_mail/http.py` — Replace `StatelessMCPASGIApp`

Replaced with `_MCPHeaderFixupApp`, a thin ASGI wrapper that:
- Fixes Accept/Content-Type headers (same as before)
- Normalises empty path to `"/"` for Starlette mount compatibility
- **Delegates to `mcp_http_app`** (the SDK's built-in Starlette app)

The SDK's `StreamableHTTPSessionManager._handle_stateless_request()` properly uses `task_group.start()` with `task_status.started()`, which synchronises the `_receive_loop` startup before calling `handle_request()`. This eliminates the zero-buffer deadlock.

Also fixed:
- `_shutdown()`: Changed `suppress(Exception)` → `suppress(BaseException)` with `asyncio.wait_for(..., timeout=5.0)` guard. `CancelledError` is a `BaseException` in Python 3.9+.
- `_base_passthrough`: Changed `path=base_with_slash` (i.e. `"/mcp/"`) → `path="/"`. The sub-app expects paths relative to the mount point, not absolute.

#### 2b. `tests/_http_helpers.py` — New test helper

```python
@asynccontextmanager
async def http_test_client(app, **client_kwargs):
    async with app.router.lifespan_context(app):   # enters MCP lifespan
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", timeout=5.0, **client_kwargs) as client:
            yield client
```

This enters the FastAPI app's lifespan (which chains into `mcp_http_app.lifespan()` → `_lifespan_manager()` + `session_manager.run()`), initialising the session manager's task group before any requests are made. The 5s timeout provides defence-in-depth against future regressions.

#### 2c. All 10 HTTP test files updated

Every occurrence of:
```python
transport = ASGITransport(app=app)
async with AsyncClient(transport=transport, base_url="http://test") as client:
```
replaced with:
```python
async with http_test_client(app) as client:
```

#### 2d. CI yml

Removed `--ignore-glob="tests/test_http*.py"` from the unit test step, re-enabling all HTTP tests.

### Verification

- **91 HTTP tests pass**, 1 xfail, 0 hangs, completing in ~3.5 minutes
- Ubuntu CI: 653 passed, 3 xfailed, 1 xpassed
- macOS CI: 182 passed
- All remaining failures are from uncommitted `app.py`/`config.py` changes (see section 3)

---

## 3. Outstanding CI Failures

### 3a. Ubuntu Failures (3 tests) — Tool/Resource Filter Issue

**Root cause**: `config.py` changes the tool filter defaults:
```python
# Before:
enabled=False, profile="full"
# After:
enabled=True, profile="minimal"
```

The `"minimal"` profile (app.py:206-216) only exposes 6 tools:
```python
"minimal": {
    "clusters": [],
    "tools": ["health_check", "ensure_project", "register_agent",
              "send_message", "fetch_inbox", "acknowledge_message"],
}
```

With `clusters: []` and filtering enabled, **all resources are filtered out**. Tests that read resources fail:

| Test | Error | Resource |
|------|-------|----------|
| `test_identity_resources.py::test_whois_and_projects_resources` | `Unknown resource: 'resource://projects'` | `resource://projects` |
| `test_more_resources.py::test_core_resources` | `Unknown resource: 'resource://config/environment'` | `resource://config/environment` |
| `test_mcp_resources.py::test_outbox_resource_requires_project` | `Failed: Should require project parameter` | outbox resource |

**Fix plan**: Either:
1. **Option A** (recommended): Set `TOOLS_FILTER_ENABLED=false` in the test environment via `conftest.py` or `isolated_env` fixture so tests always see the full tool/resource set. The filter is a production concern, not a test concern.
2. **Option B**: Add resource names to the `"minimal"` profile definition.
3. **Option C**: Tests that read resources should set `TOOLS_FILTER_PROFILE=full` via `monkeypatch`.

### 3b. macOS Failures (3 tests) — Concurrency Race Conditions

All in `test_concurrency_agents.py`:

| Test | Error |
|------|-------|
| `TestRaceConditions::test_simultaneous_project_creation` | `OS error: [Errno 2] No such file or directory` |
| `TestRaceConditions::test_simultaneous_agent_registration_same_name` | Same `ensure_project` error |
| `TestRaceConditions::test_simultaneous_mark_read` | Same `ensure_project` error |

**Root cause**: The `app.py` docstring refactoring removed the `@mcp.tool(name="ensure_project")` decorator line and changed how the tool is registered. The tool itself still works (HTTP tests prove it), but the concurrency tests may be hitting a race condition during filesystem setup that the refactored code handles differently.

**Fix plan**: These need investigation. Start by running `test_concurrency_agents.py` locally with the `app.py` changes applied and examining the exact traceback. The `[Errno 2]` suggests a timing issue where the storage root directory hasn't been created before concurrent `ensure_project` calls try to use it.

### 3c. Pre-existing xfail Tests (4 tests)

These were marked xfail before our work and are not blocking:

| Test | Reason |
|------|--------|
| `test_concurrent_writes.py::test_concurrent_project_ensure` | Race condition on macOS |
| `test_http_transport.py::test_http_lock_status_endpoint` | Lock path mismatch in `isolated_env` |
| `test_git_index_lock.py::test_handles_permission_error_gracefully` | `Path.stat` mock teardown hang |
| `test_e2e_disaster_recovery.py::test_restore_specific_archive` | Returns all messages instead of subset |

### 3d. xpassed Test (1 test)

One xfail test unexpectedly passed in CI:
- Likely `test_concurrent_project_ensure` or `test_handles_permission_error_gracefully`
- If it passes consistently, the `xfail` marker can be removed

---

## 4. Uncommitted Changes Summary

Two files remain uncommitted (part of the original PR scope, not our HTTP fix):

### `src/mcp_agent_mail/app.py` (+30, -316 lines)
- Tool docstrings drastically shortened (from 30-50 line detailed docs to 1-3 line summaries)
- Detailed descriptions moved to `@mcp.tool(description=...)` decorator parameter
- Tool registration decorators restructured

### `src/mcp_agent_mail/config.py` (+2, -2 lines)
- `TOOLS_FILTER_ENABLED`: default `"false"` → `"true"`
- `TOOLS_FILTER_PROFILE`: default `"full"` → `"minimal"`

These changes are the cause of all remaining CI failures. They need to be either:
1. Committed as part of the PR with corresponding test fixes
2. Reverted if the filter changes are not intended for this PR

---

## 5. Untracked Files

These exist in the working tree but are not part of any commit:

| File | Notes |
|------|-------|
| `docs/TOKEN_EFFICIENCY_OPTIMIZATION_REPORT.md` | May be related to the docstring reduction work |
| `scripts/measure_token_overhead.py` | Token measurement tooling |
| `scripts/token_overhead_metrics.json` | Measurement results |
| `.beads/daemon-error` | Local tooling artifact — do not commit |
| `.beads/export-state/` | Local tooling artifact — do not commit |

---

## 6. Recommended Next Steps (Priority Order)

1. **Fix the tool filter test failures** — Option A from section 3a is simplest: add `monkeypatch.setenv("TOOLS_FILTER_ENABLED", "false")` to the `isolated_env` fixture in `conftest.py`, or set it globally in the test environment.

2. **Investigate macOS concurrency failures** — Run `test_concurrency_agents.py` with the `app.py` changes locally. The `[Errno 2]` errors suggest a storage-root race condition. May need an xfail marker or a fix in `ensure_project` to create directories more defensively.

3. **Commit `app.py` and `config.py`** — Once tests pass, stage and commit these as a separate commit (e.g., `refactor: reduce tool docstrings and enable minimal filter profile`).

4. **Review xpassed test** — If the previously-xfail test now passes consistently, remove its `xfail` marker.

5. **Clean up untracked files** — Decide whether `docs/TOKEN_EFFICIENCY_OPTIMIZATION_REPORT.md` and `scripts/` belong in the PR. Add to `.gitignore` or commit as appropriate.

---

## 7. Key Files Reference

| File | Purpose |
|------|---------|
| `src/mcp_agent_mail/http.py:1099-1127` | `_MCPHeaderFixupApp` — the fix for HTTP hangs |
| `src/mcp_agent_mail/http.py:938-944` | `_shutdown()` — improved with `suppress(BaseException)` + timeout |
| `src/mcp_agent_mail/http.py:948-957` | `lifespan_context` — composed lifespan entering MCP + session manager |
| `tests/_http_helpers.py` | `http_test_client()` — lifespan-aware test client |
| `src/mcp_agent_mail/app.py:197-221` | `TOOL_FILTER_PROFILES` — defines what "minimal" includes |
| `src/mcp_agent_mail/config.py:376-380` | Tool filter default settings |
| `.github/workflows/ci.yml:59-65` | Unit test step configuration |

---

## 8. How to Reproduce Locally

```bash
# Run all HTTP tests (should pass)
uv run pytest tests/test_http_auth.py tests/test_http_server.py tests/test_http_transport.py \
  tests/test_http_rate_limit.py tests/test_http_rate_limiting_comprehensive.py \
  tests/test_http_auth_rate_limit.py tests/test_http_logging_and_errors.py \
  tests/test_http_negative_jwt.py tests/test_http_redis_rate_limit.py \
  tests/test_http_workers_and_options.py tests/test_http_unit.py \
  --timeout=15 --timeout-method=thread -q

# Run the failing resource tests (will fail due to app.py/config.py changes)
uv run pytest tests/test_identity_resources.py::test_whois_and_projects_resources \
  tests/test_mcp_resources.py::test_outbox_resource_requires_project \
  tests/test_more_resources.py::test_core_resources \
  --timeout=30 -v

# Verify failures are from app.py, not HTTP fix
git stash -- src/mcp_agent_mail/app.py src/mcp_agent_mail/config.py
uv run pytest tests/test_identity_resources.py tests/test_mcp_resources.py tests/test_more_resources.py \
  --timeout=30 -q
# ^ should pass
git stash pop
```
