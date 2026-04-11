# subagent-brief 📋

**Methodology for constructing high-quality delegation context when handing off tasks from a parent agent to a coding subagent.**

## Problem

When a parent agent (main session) delegates a task to a coding subagent (Codex, Claude Code, OpenClaw sessions_spawn, etc.), the context it passes often lacks critical information — missing file paths, unclear task boundaries, unstated constraints. The subagent then either guesses wrong, scopes creeps, or has to ask follow-up questions that break the flow.

**Result:** wasted tokens, rework, and unreliable output.

## Solution

`subagent-brief` is an OpenClaw skill that provides a structured briefing methodology. Before spawning any coding subagent, the parent agent fills out a six-category template:

| Category | Purpose | Compressible? |
|----------|---------|:------------:|
| **Objective** | One-sentence goal + deliverables | ❌ |
| **Background** | Why this task exists | ✅ |
| **Task Boundary** | Do / Don't do | ❌ |
| **Key References** | File paths + purposes | structure ❌, description ✅ |
| **Constraints** | Tech constraints, coding standards | items ❌, detail ✅ |
| **Acceptance Criteria** | Executable verification steps | ❌ |
| **Suggested Steps** *(optional)* | Recommended execution order | ✅ |

The skill also includes:
- **Reference vs Inline decision rules** — what to inline vs what to pass as a path, depending on subagent access
- **Completeness check** — a self-check protocol with a core question and 7-item checklist
- **Common failure patterns** — 7 typical mistakes and how each category prevents them

## Installation

### OpenClaw

```bash
cp -r SKILL.md ~/.openclaw/skills/subagent-brief/
```

Then restart the gateway:
```bash
openclaw gateway restart
```

### Standalone

The `SKILL.md` is a self-contained methodology document. You can use it as a prompt template or reference guide for any agent framework, not just OpenClaw.

## Usage

When you're about to spawn or delegate to a coding subagent, read `SKILL.md` and follow the briefing template. The structure is designed to be directly executable — an agent can read it and produce a complete briefing without interpretation.

## Key Design Decisions

1. **Seven categories, six required** — Suggested Steps is optional; simple tasks don't need execution order guidance
2. **Examples are inline** — each category has ❌/✅ examples so the agent can self-calibrate
3. **Pairing rule** — every file mentioned in the briefing must appear in Key References
4. **Prior exploration** — if the parent agent tried something before, conclusions must be documented in Background
5. **Critical Context** — a catch-all question for knowledge that doesn't fit the six categories but would cause a wrong path if missing

## Inspired By

The structured template draws from Hermes Agent's [context compression algorithm](https://github.com/nousresearch/hermes-agent), which uses a similar six-field structure (Goal, Progress, Key Decisions, Relevant Files, Next Steps, Critical Context) for preserving context across compression boundaries. While Hermes uses this structure to compress history, `subagent-brief` uses it to construct context from scratch — proving the structure is a general-purpose "minimal complete information set" for agent handoffs.

## License

MIT
