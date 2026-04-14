# ConPact

**Multi-Agent Contract Protocol** — Structured file-based coordination for coding agents.

## Problem

When multiple coding agents (Claude Code, Codex, OpenClaw workers) operate on the same project, they lack a structured way to delegate tasks, track progress, and report results. The "tmux split-pane" approach — running agents side by side and hoping they figure out how to communicate — is unreliable and token-wasteful.

**Result:** wasted tokens, rework, and unreliable output.

## Solution

ConPact defines a lightweight, pure-documentation protocol that any agent can follow by reading a SKILL.md. The core concept is a **contract** — a single JSON file that carries a task through its entire lifecycle, from delegation to completion.

### How it works

1. **Agent A** creates a contract file in `.agents/contracts/`, specifying the task and assignee
2. **Agent B** discovers the contract (via filename-based polling), claims it, and starts work
3. **Agent B** submits results back into the same contract file
4. **Agent A** reviews the result and closes the contract

All communication happens through the shared filesystem. No scripts, no MCP servers, no runtime dependencies.

### Key features

| Feature | Description |
|---------|-------------|
| **Peer-to-peer** | Any agent can delegate to any other — no central coordinator required |
| **Multi-agent** | Supports 3+ agents coordinating simultaneously |
| **Contract lifecycle** | State machine: `draft → assigned → in_progress → submitted → reviewed → closed` |
| **Atomic writes** | Write-to-temp + verify + rename pattern prevents concurrent write conflicts |
| **Four capabilities** | Built around Delegation, Description, Discernment, and Diligence |
| **Framework-agnostic** | Works with Claude Code, Codex, OpenClaw, or any agent with filesystem access |

## Protocol Overview

### Directory structure

```
.agents/
├── registry.json              # Optional agent directory (weak dependency)
├── contracts/
│   ├── @<assignee>.<id>.json  # Active contracts
│   └── _archive/              # Closed contracts
```

### Contract structure

A contract is a single JSON file with four sections:

| Section | Capability | Purpose |
|---------|-----------|---------|
| `delegation` | Delegation + Description | Task specification using the 7-category delegation template |
| `diligence` | Diligence | Progress tracking and blocker reporting |
| `result` | — | Execution results: summary, files changed, verification |
| `discernment` | Discernment | Review feedback and revision requests |

### State machine

```
draft ──→ assigned ──→ in_progress ──→ submitted ──→ reviewed ──→ closed
               ↑            ↑                        │
               │            └── revision_needed ←─────┘
```

## Installation

### As a Skill (Claude Code / OpenClaw)

```bash
cp -r . ~/.claude/skills/ConPact/
```

### Standalone

The `SKILL.md` is a self-contained protocol specification. Any agent can read it and follow the rules — no installation required beyond placing the file where the agent can access it.

## Usage

See [SKILL.md](SKILL.md) for the full protocol specification and agent behavior rules.

See [docs/superpowers/specs/2026-04-14-contract-protocol-design.md](docs/superpowers/specs/2026-04-14-contract-protocol-design.md) for the design rationale and detailed field reference.

## Name

**ConPact** = **Con**tract + **Pact**, also a homophone of *compact* — reflecting the protocol's lightweight, zero-dependency design.

## Inspired By

The structured delegation template draws from Hermes Agent's context compression algorithm, which uses a similar six-field structure for preserving context across compression boundaries. ConPact applies the same "minimal complete information set" principle to multi-agent coordination.

## License

MIT
