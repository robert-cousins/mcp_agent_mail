# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical Rules

**Read AGENTS.md first** - it contains mandatory rules including:
- NEVER delete files without explicit permission
- NEVER run destructive git commands (`git reset --hard`, `git clean -fd`, `rm -rf`)
- NEVER run code transformation scripts; always make changes manually
- NEVER create file variants (e.g., `file_v2.py`, `file_improved.py`)

## Build, Lint, Test Commands

```bash
# Start HTTP server (default port 8765)
make serve-http

# Database migrations
make migrate

# Lint with auto-fix
make lint
# Or directly: uv run ruff check --fix --unsafe-fixes

# Type checking
make typecheck
# Or directly: uvx ty check

# Run tests
uv run pytest tests/

# Run single test file
uv run pytest tests/test_specific.py

# Run specific test
uv run pytest tests/test_specific.py::test_function_name -v

# Install pre-commit guard
make guard-install PROJECT=<abs-path> REPO=<abs-path>
```

**Always run `make lint` and `make typecheck` before committing.**

## Package Management

- Use `uv` only, never pip
- Python 3.14 target (no backwards compatibility needed)
- Config via `pyproject.toml`, not requirements.txt

## Configuration

All config loaded from `.env` via `python-decouple`:
```python
from decouple import Config as DecoupleConfig, RepositoryEnv
decouple_config = DecoupleConfig(RepositoryEnv(".env"))
VALUE = decouple_config("KEY", default="default")
```

Never use `os.getenv()` or `dotenv`.

## Architecture Overview

MCP Agent Mail is a FastMCP HTTP server that provides asynchronous coordination for coding agents working on the same codebase.

```
Agents (Claude Code, Codex, etc.)
        │ HTTP (bearer token auth)
        ▼
┌─────────────────────────────────┐
│  FastMCP Server (app.py)        │
│  ~80 tools in 9 clusters        │
└─────────┬───────────────────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
SQLite       Git Archive
(queries)    (audit trail)
```

### Main Source Files

| File | Purpose |
|------|---------|
| `app.py` | MCP tool registry, core coordination logic, FastMCP server |
| `http.py` | HTTP transport, FastAPI, auth (JWT/bearer), rate limiting |
| `storage.py` | Git archive persistence, commit queue, file locks |
| `cli.py` | Typer CLI for dev tooling, archive commands, guard install |
| `db.py` | SQLModel session management, async engine |
| `models.py` | SQLModel table definitions |
| `config.py` | Settings from `.env` via python-decouple |
| `guard.py` | Git pre-commit hook for file reservation enforcement |

### Tool Clusters

1. **infrastructure** - `ensure_project`, database setup
2. **identity** - `register_agent`, `create_agent_identity`, `whois`
3. **messaging** - `send_message`, `reply_message`, `fetch_inbox`
4. **contact** - cross-project agent linking
5. **search** - `search_messages`, `summarize_thread`
6. **file_reservations** - `file_reservation_paths`, `release_file_reservations`
7. **workflow_macros** - `macro_start_session`, `macro_prepare_thread`
8. **build_slots** - guard/pre-commit hooks
9. **product_bus** - multi-repo grouping

### Key Design Patterns

- **Dual persistence**: Git for human-auditable markdown, SQLite for indexed queries
- **Per-project isolation**: Each project gets its own SQLite DB and Git archive
- **Agent identities**: Adjective+Noun format (e.g., "GreenCastle", "BlueLake")
- **Advisory file reservations**: Agents voluntarily reserve files/globs with TTL
- **Concurrency**: Per-project `.archive.lock` and `.commit.lock` serialize Git mutations

### Database Notes (SQLModel/SQLAlchemy)

- Always use async patterns: `create_async_engine()`, `async_sessionmaker()`
- Await all database operations: `await session.execute()`, `await session.commit()`
- One `AsyncSession` per request/task; never share across concurrent coroutines
- Explicitly load relationships with `selectinload`/`joinedload` (no lazy loads in async)

## Entry Points

```bash
# CLI help
python -m mcp_agent_mail

# Start HTTP server
python -m mcp_agent_mail.cli serve-http

# Run migrations
python -m mcp_agent_mail.cli migrate
```

## Third-Party Documentation

Consult these files for library best practices:
- `third_party_docs/PYTHON_FASTMCP_BEST_PRACTICES.md`
- `third_party_docs/fastmcp_distilled_docs.md`
- `third_party_docs/mcp_protocol_specs.md`
- `third_party_docs/POSTGRES18_AND_PYTHON_BEST_PRACTICES.md`
