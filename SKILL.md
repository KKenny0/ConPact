---
name: ConPact
description: "Multi-Agent Contract Protocol — a structured, file-based protocol for coordinating multiple coding agents (Claude Code, Codex, OpenClaw workers) via shared filesystem. Use when setting up multi-agent workflows, delegating tasks between agents, or establishing cross-agent communication in tmux split-pane, shared-project, or any environment where agents share a filesystem."
---

# ConPact — Multi-Agent Contract Protocol

A pure-documentation protocol for coordinating multiple coding agents through shared filesystem. No scripts, no MCP, no runtime dependencies — any agent that can read and write files can participate.

## Quick Reference

```
.agents/
├── registry.json              # Optional agent directory
├── contracts/
│   ├── @<assignee>.<id>.json  # Active contracts
│   └── _archive/              # Closed contracts
```

Each agent discovers work by scanning `contracts/` for files prefixed with `@<its-own-id>`.

## Directory Structure

### `.agents/registry.json` (optional)

Advisory agent directory. The protocol works correctly without it — contracts are the single source of truth.

```json
{
  "updated_at": "2026-04-14T10:30:00Z",
  "agents": [
    {
      "id": "claude-code",
      "role": "architect",
      "capabilities": ["code-generation", "review", "planning"],
      "status": "available",
      "last_heartbeat": "2026-04-14T10:30:00Z"
    }
  ]
}
```

- `capabilities` are freeform string tags, not an enum.
- `status` is `available` or `busy`.
- `last_heartbeat` is optional. Agents may update it to signal liveness.
- Registry status is advisory. Last-writer-wins is acceptable.

### `.agents/contracts/`

Each contract is one JSON file carrying a task through its full lifecycle. Filenames embed the assignee: `@<assignee-id>.<contract-id>.json`.

Closed contracts move to `_archive/` retaining their filename. Archive is never pruned by the protocol.

## Contract State Machine

```
draft ──→ assigned ──→ in_progress ──→ submitted ──→ reviewed ──→ closed
               ↑            ↑                        │
               │            └── revision_needed ←─────┘
               │
               └── reassigned (delegator reassigns stale contract)
```

| State | Who acts | Next states |
|-------|----------|-------------|
| `draft` | delegator | `assigned` |
| `assigned` | assignee | `in_progress` |
| `in_progress` | assignee | `submitted` |
| `submitted` | delegator | `reviewed` |
| `reviewed` | delegator | `closed` or `revision_needed` |
| `revision_needed` | assignee | `in_progress` |
| `closed` | either | terminal (move to _archive/) |

Ownership per state prevents conflicting writes:
- `draft` / `assigned`: only delegator modifies
- `in_progress`: only assignee modifies
- `submitted`: only delegator modifies

## Contract JSON Structure

```json
{
  "protocol_version": "1.0",
  "id": "2026-04-14-task-auth",
  "status": "assigned",
  "from": "claude-code",
  "assignee": "codex",
  "priority": "high",
  "created_at": "2026-04-14T10:30:00Z",
  "updated_at": "2026-04-14T10:30:00Z",

  "delegation": {
    "objective": "...",
    "background": "...",
    "boundary": { "do": [...], "do_not": [...] },
    "references": [...],
    "constraints": [...],
    "acceptance_criteria": [...],
    "suggested_steps": [...]
  },

  "diligence": null,
  "result": null,
  "discernment": null
}
```

### Top-level fields

| Field | Required | Description |
|-------|----------|-------------|
| `protocol_version` | yes | `"1.0"`. If unrecognized, attempt to parse with latest known schema. |
| `id` | yes | `YYYY-MM-DD-<slug>`. Append counter (`-2`) if same date+topic conflicts. |
| `status` | yes | Current state in the lifecycle. |
| `from` | yes | Agent ID of the delegator. |
| `assignee` | conditional | Agent ID of executor. Required except in `draft` (may be null). |
| `priority` | no | `low`, `medium` (default), `high`. Process high first when multiple available. |
| `created_at` | yes | ISO 8601 timestamp. |
| `updated_at` | yes | ISO 8601 timestamp. Updated on every write. Serves as concurrency token. |

### `delegation` — Task Specification

The core of the contract. Seven categories — six required, one optional.

#### 1. `objective` (required)

One-sentence goal + concrete deliverables.

Example: `"Implement PATCH /users/:id/preferences — accepts {theme, language, notifications}, returns 204, with validation and tests"`

Not: `"Update the user preferences feature"`

#### 2. `background` (optional)

Why this task exists. One paragraph max. Include conclusions from prior exploration so the assignee doesn't repeat failed experiments.

Example: `"Part of EPIC-42 (user settings overhaul). Prior: PUT for partial updates was abandoned — PATCH is correct per RFC 7396."`

#### 3. `boundary` (required)

Explicit DO and DO NOT lists.

```json
{
  "do": [
    "Create PATCH handler in src/api/users/preferences.py",
    "Add pydantic validation for allowed fields",
    "Write tests in tests/api/test_preferences.py"
  ],
  "do_not": [
    "Modify the existing /settings endpoint",
    "Add database migrations",
    "Change the frontend"
  ]
}
```

#### 4. `references` (required)

Every file mentioned in the contract must appear here. Pairing rule: if you name a file anywhere in delegation, it gets an entry.

```json
[
  {"path": "src/api/users/__init__.py", "purpose": "Register the new route"},
  {"path": "src/schemas/user.py", "purpose": "Existing UserPreferences schema — reuse or extend"}
]
```

If the assignee has no filesystem access, inline the necessary content instead of paths.

#### 5. `constraints` (required)

Technical constraints and coding standards the assignee must follow.

Example: `["Python 3.11+, type hints everywhere", "Follow existing patterns in src/api/users/", "No new dependencies"]`

#### 6. `acceptance_criteria` (required)

Executable verification steps — not "it works" but "test X passes with output Y".

Example: `["pytest tests/api/test_preferences.py passes", "PATCH valid body → 204", "PATCH invalid fields → 422 with error details"]`

#### 7. `suggested_steps` (optional)

Recommended execution order. Skip for simple changes.

Example: `["Read existing patterns", "Create handler", "Add validation schema", "Implement logic", "Register route", "Write tests", "Run lint + tests"]`

### `diligence` — Progress Tracking

Optional. Updated by the assignee during execution.

```json
{
  "progress": "Step 3 of 7: implementing handler logic",
  "blockers": [],
  "next_check_in": "2026-04-14T11:00:00Z"
}
```

- `progress`: freeform status description.
- `blockers`: list of blocking issues.
- `next_check_in`: ISO 8601 timestamp for when to expect the next update.

### `result` — Execution Output

Filled by the assignee on submission. Required from `submitted` onward.

```json
{
  "summary": "Implemented JWT refresh token rotation",
  "files_changed": [
    "src/api/auth/refresh.py",
    "src/services/auth.py",
    "tests/api/test_refresh.py"
  ],
  "verification": "All 12 tests pass. ruff check clean.",
  "notes": "Reused existing token utility from src/utils/tokens.py"
}
```

### `discernment` — Review Feedback

Filled by the delegator on review. Required from `reviewed` onward.

```json
{
  "review_status": "approved",
  "feedback": "Clean implementation. Tests cover edge cases well.",
  "requested_changes": null
}
```

- `review_status`: `approved` or `revision_needed`. For infeasible tasks, use `approved` with explanatory feedback and close — no separate `rejected` state.
- `requested_changes`: required when `review_status` is `revision_needed`.

## Agent Behavior Rules

### Startup

1. If `registry.json` exists, read it for situational awareness. Optionally register yourself — registration is not required.
2. Scan `contracts/` for files prefixed with `@<your-id>`. For each with status `assigned`, verify the `assignee` field matches your ID. Claim matching contracts by updating status to `in_progress`. Skip mismatches.

### Delegating a task

1. Create `@<assignee>.<id>.json` with status `assigned` (skip `draft` if assignee is known).
2. Fill all required `delegation` fields using the template above.
3. Optionally update `registry.json` to set assignee status to `busy`.

### Executing a task

1. Read the contract. Verify all required delegation fields are present (objective, boundary, references, constraints, acceptance_criteria). If any are missing, set status back to `assigned` and add a `diligence.blockers` entry listing what is missing. Do not start work on an incomplete contract.
2. Update status to `in_progress`.
3. For long tasks, periodically update `diligence.progress`.
4. When done, fill `result` and set status to `submitted`.

### Reviewing a result

1. Read the `result` section.
2. Verify against `acceptance_criteria`.
3. Fill `discernment`: `review_status` to `approved` or `revision_needed`.
4. If `approved`: set status to `closed`, move to `_archive/`, optionally update registry.
5. If `revision_needed`: set status to `revision_needed`, provide specific `requested_changes`.

## Atomic Writes

All contract writes follow this sequence:

1. Write updated JSON to a temp file (`@<assignee>.<id>.json.tmp`).
2. Re-read the original file. Verify `updated_at` has not changed since your last read.
3. If `updated_at` matches: rename temp to replace original (atomic on most filesystems). Set `updated_at` to current time.
4. If `updated_at` changed: another agent wrote first. Discard temp, re-read, and retry.

This read-check-write-rename pattern prevents split-brain from concurrent writes. `updated_at` is the optimistic concurrency token.

## Staleness and Reassignment

A contract may be reassigned only when **both** conditions are met:

1. No `diligence` update for longer than 30 minutes.
2. `diligence.next_check_in` is set and has passed (or was never set).

Both must be true. If the assignee set a future `next_check_in`, wait even if the 30-minute threshold passed.

Reassignment steps: set status to `assigned`, update `assignee`, rename file to new prefix, append note to `delegation.background`.

## Notification

Default: filename-based polling. After completing any action, check contracts/ once. While idle, check every 5 minutes.

Optional enhancements (not required for correctness):
- **tmux send-keys**: notify the assignee's pane after creating a contract
- **Signal files**: write `.agents/notifications/<agent-id>.signal`

## Completeness Check

Before submitting a contract, answer:

1. "If I were the assignee, with zero prior context, could I start work immediately from this contract alone?"
2. "Is there anything the assignee needs to know that isn't covered by the delegation fields?"

Checklist:
- [ ] `objective` — one-sentence goal + specific deliverables
- [ ] `boundary` — explicit DO and DO NOT
- [ ] `references` — every file mentioned has an entry
- [ ] `constraints` — covers pitfalls the assignee is most likely to hit
- [ ] `acceptance_criteria` — each criterion is executable
- [ ] Prior exploration — failed attempts and conclusions in `background`
- [ ] Critical context — anything not covered above that would cause a wrong path
