# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ConPact is a Multi-Agent Contract Protocol — an MCP server that provides 12 tools for coordinating multiple coding agents (Claude Code, Codex, OpenClaw) via shared filesystem contracts. Agents delegate tasks, track progress, and review results through structured JSON contract files.

## Development Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -v

# Run a single test module
python -m pytest tests/test_contract.py -v

# Run a single test
python -m pytest tests/test_contract.py::TestStateMachine::test_valid_transitions -v

# Run the MCP server locally
python -m conpact_server
```

## Architecture

**Module dependency flow (read bottom-up):**

```
server.py ──→ contract.py ──→ schema.py
    │              │
    ├─→ registry.py ──→ paths.py
    └─→ paths.py
```

- **`paths.py`** — Pure path helpers for `.agents/` directory structure. No logic, no I/O.
- **`schema.py`** — Validates delegation fields and generates contract IDs (`YYYY-MM-DD-<slug>`). Stateless.
- **`contract.py`** — Core module. State machine (`VALID_TRANSITIONS`), CRUD operations, atomic writes (`write_contract_atomic`). All mutations go through here. `ContractError` is the domain exception.
- **`registry.py`** — Agent directory management. Read/write `.agents/registry.json`. Advisory — the protocol works without it.
- **`server.py`** — MCP server wiring. Defines 12 `Tool` objects and dispatches `handle_call_tool` to `_handle_*` functions. Uses `mcp.server.Server` with decorators. Each handler extracts `_root` from arguments to resolve the project directory.

**Key patterns:**
- **Atomic writes**: Write to `.json.tmp` → `os.replace()` to target. Prevents concurrent write corruption.
- **Filename-based discovery**: Contract files named `@<assignee>.<id>.json` — agents find their work by globbing their prefix.
- **State machine enforcement**: Every mutation validates current status against `VALID_TRANSITIONS` before proceeding.
- **Dual-condition reassignment**: Requires both 30-min inactivity AND `next_check_in` expired.

**State machine:**
```
assigned → in_progress → submitted → closed
                            ↑            ↓
                            └─ revision_needed
```
(v1 skips `draft` and `reviewed` states from the protocol spec)

## Important Conventions

- The `docs/` directory is **local only** — never committed to git (gitignored). It contains design specs and implementation plans.
- MCP SDK uses `inputSchema` (camelCase) on `Tool` objects, and `NotificationOptions` imports from `mcp.server` (not `mcp.types`).
- Handler functions in `server.py` are sync; the `@server.call_tool()` decorator handles the async wrapper.
- Tests use `tempfile.TemporaryDirectory` instead of pytest's `tmp_path` (Windows permission issues with `pytest-asyncio`).
