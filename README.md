# ConPact

**Multi-Agent Contract Protocol** — Coordinate multiple coding agents through structured filesystem contracts.

## Why

When multiple coding agents (Claude Code, Codex, OpenClaw) work on the same project, they need a way to delegate tasks, track progress, and report results. Without structured coordination, agents waste tokens, duplicate work, and produce unreliable output.

## How It Works

ConPact uses **contracts** — JSON files that carry a task through its full lifecycle. An MCP server provides 12 tools for creating, claiming, updating, and reviewing contracts. All state lives on the shared filesystem.

```
Agent A delegates ──→ Agent B claims & works ──→ Agent B submits ──→ Agent A reviews
     │                        │                        │                    │
     └─ conpact_create        └─ conpact_claim          └─ conpact_submit   └─ conpact_review
```

## Key Features

- **Peer-to-peer** — any agent can delegate to any other, no central coordinator
- **12 MCP tools** — full lifecycle: init, register, create, check, claim, update, submit, review, close, read, list, reassign
- **State machine enforcement** — every transition is validated
- **Atomic writes** — prevents concurrent write corruption
- **Framework-agnostic** — works with any MCP-compatible agent

## State Machine

```
assigned → in_progress → submitted → closed
                            ↑            ↓
                            └─ revision_needed
```

## Installation

```bash
pip install -e .
```

Register with your agent:

```bash
# Claude Code
claude mcp add conpact -- python -m conpact_server

# Codex (config.toml)
[mcp_servers.conpact]
command = "python"
args = ["-m", "conpact_server"]
```

## Quick Start

```
1. conpact_init                                    # Enable coordination in your project
2. conpact_register(agent_id="claude-code")        # Register your identity
3. conpact_create(assignee="codex", objective=...)  # Delegate a task
4. conpact_check(agent_id="codex")                 # Other agent picks up work
5. conpact_submit → conpact_review                 # Submit and close the loop
```

## Protocol Structure

```
.agents/
├── registry.json              # Agent directory (optional)
├── contracts/
│   ├── @<assignee>.<id>.json  # Active contracts
│   └── _archive/              # Closed contracts
```

Each contract has four sections:

| Section | Purpose |
|---------|---------|
| `delegation` | Task spec: objective, boundaries, references, acceptance criteria |
| `diligence` | Progress tracking and blocker reporting |
| `result` | Execution summary, files changed, verification |
| `discernment` | Review feedback and revision requests |

## Name

**Con**tract + **Pact** — also a homophone of *compact*, reflecting the protocol's lightweight design.

## License

MIT
