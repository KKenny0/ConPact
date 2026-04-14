---
name: ConPact
description: "Multi-Agent Contract Protocol — a structured, file-based protocol for coordinating multiple coding agents (Claude Code, Codex, OpenClaw workers) via shared filesystem. Use when setting up multi-agent workflows, delegating tasks between agents, or establishing cross-agent communication in tmux split-pane, shared-project, or any environment where agents share a filesystem."
---

# ConPact

Fill all six required categories before delegating. Add the seventh when the task is non-trivial.

## Briefing Template

### 1. Objective (required)

One-sentence goal + concrete deliverables.

```
Implement PATCH /users/:id/preferences — accepts {theme, language, notifications}, returns 204, with pydantic validation and unit tests.
```

❌ "Update the user preferences feature"
✅ "Implement PATCH /users/:id/preferences — accepts {theme, language, notifications}, returns 204, with validation and tests"

### 2. Background (required, compressible)

Why this task exists. One paragraph max. Include conclusions from any prior exploration so the subagent doesn't repeat failed experiments.

```
Part of EPIC-42 (user settings overhaul). Monolithic /settings endpoint needs splitting.

Prior: PUT for partial updates was abandoned — PATCH is correct per RFC 7396.
```

### 3. Task Boundary (required)

Explicitly state what to do AND what not to do.

```
DO:
- Create PATCH handler in src/api/users/preferences.py
- Add pydantic validation for allowed fields
- Write tests in tests/api/test_preferences.py

DO NOT:
- Modify the existing /settings endpoint
- Add database migrations (schema already exists)
- Implement authentication (middleware handles it)
- Change the frontend
```

### 4. Key References (required)

Every file, doc, or resource the subagent will touch or need. **Pairing rule:** every file mentioned in the briefing must appear here.

| Path | Purpose |
|------|---------|
| `src/api/users/__init__.py` | Register the new route |
| `src/schemas/user.py` | Existing UserPreferences schema — reuse or extend |
| `docs/api-spec.md#preferences` | API contract for this endpoint |

**Reference vs Inline decision:**
- Subagent **has** filesystem access → path + one-line purpose; inline summaries only for content the task directly depends on
- Subagent **has no** filesystem access → inline all necessary content

### 5. Constraints (required)

Technical constraints, coding standards, design decisions the subagent must follow.

```
- Python 3.11+, type hints everywhere
- Follow existing patterns in src/api/users/
- pydantic validation, reject unknown fields strictly
- No new dependencies
```

### 6. Acceptance Criteria (required)

Executable verification steps, not vague goals.

```
- [ ] pytest tests/api/test_preferences.py passes
- [ ] PATCH valid body → 204
- [ ] PATCH invalid fields → 422 with error details
- [ ] ruff check src/api/users/preferences.py — no errors
```

### 7. Suggested Steps (optional)

Recommended execution order. Skip for simple changes.

```
1. Read src/api/users/settings.py for pattern reference
2. Create src/api/users/preferences.py with route skeleton
3. Add pydantic request schema
4. Implement handler logic
5. Register route in __init__.py
6. Write tests: happy path → edge cases → error cases
7. Run lint + tests
```

## Completeness Check

Before sending, answer two questions:

1. **"If I were the subagent, with zero prior context, could I start work immediately from this briefing alone?"** — If not confident "yes," something is missing.

2. **"Is there anything the subagent absolutely needs to know that isn't covered by the six categories?"** — Common examples: a known bug in a dependency, a non-obvious coupling, a decision from a prior conversation, a timeout constraint.

**Checklist:**

- [ ] Objective — one-sentence goal + specific deliverables
- [ ] Task Boundary — explicit DO and DO NOT
- [ ] Key References — every file mentioned in the briefing has a corresponding entry
- [ ] Constraints — covers pitfalls the subagent is most likely to hit
- [ ] Acceptance Criteria — each criterion is executable (not "it works" but "test X passes with output Y")
- [ ] Prior exploration — failed attempts and conclusions documented in Background
- [ ] Critical context — anything not covered by the six categories that would cause a wrong path
