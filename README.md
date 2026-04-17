# ConPact

**Multi-Agent Contract Protocol** — Coordinate multiple coding agents through structured filesystem contracts.

## Why

When multiple coding agents (Claude Code, Codex, OpenClaw) work on the same project, they need a way to delegate tasks, track progress, and report results. Without structured coordination, agents waste tokens, duplicate work, and produce unreliable output.

## How It Works

ConPact uses **contracts** — JSON files that carry a task through its full lifecycle. An MCP server provides 16 tools for creating, claiming, updating, and reviewing contracts. All state lives on the shared filesystem.

```
Agent A delegates ──→ Agent B claims & works ──→ Agent B submits ──→ Agent A reviews
     │                        │                        │                    │
     └─ conpact_create        └─ conpact_claim          └─ conpact_submit   └─ conpact_review
```

## Key Features

- **Peer-to-peer** — any agent can delegate to any other, no central coordinator
- **16 MCP tools** — full lifecycle: init, register, create, check, overview, claim, update progress, submit, review, close, read, list, reassign, log, heartbeat, verify
- **State machine enforcement** — every transition is validated
- **Atomic writes** — prevents concurrent write corruption
- **Project isolation** — project root is bound at init, cross-project access is rejected
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

## How Agents Discover and Use These Tools

ConPact runs as an **MCP server** using stdio transport. After you register it with an agent, the agent sees the 15 `conpact_*` tools in its tool list — but **it does not automatically know when or how to use them**. You need to configure two things:

### 1. Register the MCP Server with Each Agent

Both agents must point to the **same project directory** via `cwd`. This is what makes the shared filesystem coordination work.

**Claude Code** — add to your project's `.claude/settings.json`:

```jsonc
{
  "mcpServers": {
    "conpact": {
      "command": "python",
      "args": ["-m", "conpact_server"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

Or via CLI:

```bash
claude mcp add conpact -- python -m conpact_server
```

**Codex** — add to your project's `codex/config.toml`:

```toml
[mcp_servers.conpact]
command = "python"
args = ["-m", "conpact_server"]
cwd = "/path/to/your/project"
```

> **Important:** The `cwd` must be the same absolute path for both agents. The MCP server resolves all contract files relative to this directory.

### 2. Add Behavioral Instructions (Required)

MCP tool descriptions tell the agent what each tool *does*, but not *when* to use it or *what workflow to follow*. **You must add coordination instructions to each agent's global config file, otherwise the protocol will not work** — agents will simply ignore the tools.

**For the delegator (e.g., Claude Code)** — add to `~/.claude/CLAUDE.md` (global, applies to all projects):

```markdown
## Multi-Agent Coordination (ConPact)

When the ConPact MCP tools are available and you receive a task that should be delegated:
1. Use `conpact_check` to see your pending work first
2. Use `conpact_create` to delegate with clear objective, do/don't items, references, and acceptance criteria
3. Periodically use `conpact_list(status="submitted")` to check for work to review
4. Use `conpact_review` to approve or request revisions

Do not start implementation yourself if the task is better suited for delegation.
```

**For the implementer (e.g., Codex)** — add to Codex's global instructions file (e.g., `codex/instructions.md` or equivalent):

```markdown
## Multi-Agent Coordination (ConPact)

On session start:
1. `conpact_register` with your agent_id
2. `conpact_check` to find contracts assigned to you

When you find an assigned or revision_needed contract:
1. `conpact_read` the full details
2. `conpact_claim` to start working
3. `conpact_update_progress` and `conpact_log` as you work
4. `conpact_verify` to run acceptance criteria
5. `conpact_submit` when done — do not merge or close yourself
```

> **Why this matters:** Without these instructions, an agent will see 15 new tools but treat them like any other tool — available but not part of a workflow. The behavioral instructions are what turn individual tools into a coordination protocol. This step is not optional.
>
> **Where to put it:** Each agent's **global** config file (not project-level), because the coordination behavior should follow the agent across projects, not be tied to a single repo.

## Quick Start

### One-Time Project Setup

Run this once in the project (from either agent — it only needs to happen once):

```
conpact_init
```

This creates `.agents/` with contracts directory, archive, registry, and a `project.json` that binds the project root for isolation.

### Per-Session Startup

Each agent registers itself at the start of a session:

```
# Claude Code session:
conpact_register(agent_id="claude-code", role="architect")

# Codex session:
conpact_register(agent_id="codex", role="implementer")
```

> `conpact_init` is per-project (once). `conpact_register` is per-agent-per-session (each time an agent starts).

### Typical Workflow

```
# 1. Delegator creates a contract
conpact_create(
    caller_id="claude-code",
    assignee="codex",
    objective="Add rate limiting to all API endpoints",
    do_items=["Install slowapi", "Apply 100 req/min globally"],
    do_not_items=["Do not modify auth middleware"],
    references=[{"path": "src/main.py", "purpose": "App factory"}],
    constraints=["Must not break existing tests"],
    acceptance_criteria=["pytest tests/ passes"],
    verification=["pytest tests/ -v"],
    priority="high"
)

# 2. Implementer picks up the contract
conpact_check(agent_id="codex")        # → sees "assigned" contract
conpact_read(contract_id="...")        # → reads full details
conpact_claim(contract_id="...", caller_id="codex")

# 3. Implementer works and reports progress
conpact_update_progress(contract_id="...", progress="Installing slowapi...")
conpact_log(contract_id="...", type="decision", message="Using in-memory limiter")

# 4. Implementer verifies and submits
conpact_verify(contract_id="...", caller_id="codex")  # → runs pytest
conpact_submit(contract_id="...", summary="Done", files_changed=["src/main.py"])

# 5. Delegator reviews
conpact_review(contract_id="...", review_status="approved", feedback="LGTM")
# → contract closed and archived
```

### Cross-Agent Workflow Example

A concrete walkthrough of managing a project with both Claude Code and Codex CLI. Each agent has ConPact configured as an MCP server pointing to the same project directory.

**Step 1: Project setup (one time, from Claude Code)**

```
$ claude   # in the project directory

You> Initialize ConPact for this project
→ conpact_init()
→ conpact_register(agent_id="claude-code", role="architect",
                   capabilities=["code-review", "system-design"])
```

**Step 2: Claude Code delegates a task**

```
$ claude   # Claude Code session

You> Add rate limiting to all API endpoints. Delegate this to Codex.
→ conpact_overview(agent_id="claude-code")
← actions_for_you: ["No actions needed."]

→ conpact_create(
    caller_id="claude-code",
    assignee="codex",
    objective="Add rate limiting to all API endpoints using slowapi",
    do_items=["Install slowapi", "Integrate with FastAPI app factory",
              "Apply 100 req/min globally", "Apply 20 req/min to /users/*"],
    do_not_items=["Do not modify auth middleware", "No Redis — use in-memory"],
    references=[
      {"path": "src/main.py", "purpose": "FastAPI app factory"},
      {"path": "src/routes/users.py", "purpose": "User endpoints"},
      {"path": "requirements.txt", "purpose": "Dependencies"}
    ],
    constraints=["Must not break existing tests"],
    acceptance_criteria=["pytest tests/ passes", "slowapi in requirements.txt"],
    verification=["pytest tests/ -v"],
    priority="high"
  )
← Contract created: 2026-04-17-add-rate-limiting-using-slowapi
```

User switches to Codex CLI.

**Step 3: Codex picks up the task**

```
$ codex   # Codex CLI session in the same project

You> What should I work on?
→ conpact_register(agent_id="codex", role="implementer",
                   capabilities=["code-generation", "testing"])

→ conpact_overview(agent_id="codex")
← actions_for_you: [
    "You have an assigned contract [2026-04-17-add-rate-limiting-using-slowapi]."
    "→ conpact_read('2026-04-17-add-rate-limiting-using-slowapi')"
    "→ conpact_claim('2026-04-17-add-rate-limiting-using-slowapi', caller_id='codex')"
  ]

→ conpact_read(contract_id="2026-04-17-add-rate-limiting-using-slowapi")
← Full contract details: objective, do/don't items, references, constraints...

→ conpact_claim(contract_id="2026-04-17-...", caller_id="codex")
← Status: assigned → in_progress

→ [Codex implements: installs slowapi, modifies main.py, etc.]

→ conpact_update_progress(contract_id="...", caller_id="codex",
                          progress="Slowapi integrated, global limiter applied",
                          next_check_in="2026-04-17T16:00:00Z")

→ conpact_verify(contract_id="...", caller_id="codex")
← all_passed: true

→ conpact_submit(contract_id="...", caller_id="codex",
                 summary="Added slowapi: global 100/min, /users/* 20/min",
                 files_changed=["src/main.py", "src/routes/users.py", "requirements.txt"],
                 verification_passed=true)
← Status: in_progress → submitted
```

User switches back to Claude Code.

**Step 4: Claude Code reviews the work**

```
$ claude   # Claude Code session

You> What's the status?
→ conpact_overview(agent_id="claude-code")
← actions_for_you: [
    "You have a contract awaiting review [2026-04-17-..., status: submitted]."
    "→ conpact_read('2026-04-17-...')"
    "→ Review the changed files, then conpact_review(...)"
  ]

→ conpact_read(contract_id="2026-04-17-...")
← Full details including result.summary and files_changed

→ [Claude Code reads src/main.py, src/routes/users.py to review]

→ conpact_review(contract_id="2026-04-17-...", caller_id="claude-code",
                 review_status="approved", feedback="LGTM, clean implementation")
← Status: submitted → closed (archived)
```

> **Key point:** Every session starts with `conpact_overview`. One call tells the agent everything — what contracts exist, who's working on what, and exactly what to do next. No need to remember which tool to call first.

## Architecture

```
Agent A (Claude Code)                    Agent B (Codex)
    │ stdin/stdout                             │ stdin/stdout
    ▼                                          ▼
┌──────────────┐                        ┌──────────────┐
│  MCP Client  │                        │  MCP Client  │
└──────┬───────┘                        └──────┬───────┘
       │                                       │
       ▼                                       ▼
┌─────────────────────────────────────────────────────┐
│              conpact-server (stdio)                 │
│         MCP Server Process (per agent)              │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
              .agents/  (shared filesystem)
              ├── project.json        ← project root binding
              ├── registry.json       ← agent identities
              └── contracts/
                  ├── @codex.2026-04-17-*.json
                  └── _archive/       ← closed contracts
```

Each agent runs its own MCP server process. Coordination happens through the shared `.agents/` directory — no network, no message queue.

## Project Isolation

`conpact_init` writes a `project.json` with the absolute project root. Every subsequent operation validates the current root against this file. This prevents:

- Operating on the wrong project's contracts
- Reading contracts that were copied from another project
- Accidental cross-project writes

```
# This will be rejected:
conpact_init()   # in /project-a
# then from another session with wrong cwd:
conpact_list()   # → "Project root mismatch"
```

## Protocol Structure

```
.agents/
├── project.json               # Project root binding (created by init)
├── registry.json              # Agent directory
└── contracts/
    ├── @<assignee>.<id>.json  # Active contracts
    └── _archive/              # Closed contracts
```

Each contract has four sections:

| Section | Purpose |
|---------|---------|
| `delegation` | Task spec: objective, boundaries, references, acceptance criteria |
| `diligence` | Progress tracking and blocker reporting |
| `result` | Execution summary, files changed, verification |
| `discernment` | Review feedback and revision requests |

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
python -m conpact_server      # Run MCP server locally
```

## Name

**Con**tract + **Pact** — also a homophone of *compact*, reflecting the protocol's lightweight design.

## License

MIT
