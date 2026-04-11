---
name: subagent-brief
description: "Methodology for constructing high-quality delegation context when handing off tasks from a parent agent to a coding subagent (Codex, Claude Code, OpenClaw sessions_spawn, etc). Use before spawning any coding subagent to ensure complete and well-structured context transfer."
metadata:
  openclaw:
    emoji: "📋"
---

# subagent-brief

Construct a complete, self-contained briefing before delegating any task to a coding subagent.

## When to Use

Before spawning or delegating to any coding subagent:
- OpenClaw `sessions_spawn`
- Codex exec
- Claude Code `--print`
- Any framework where a parent agent hands off a bounded task to a child agent

**If the child agent needs to work independently, use this skill.**

## The Briefing Template

Fill all six required categories. Add the seventh when the task is non-trivial.

### 1. Objective (required)

One-sentence goal + concrete deliverables.

```
Implement the `/users/:id/preferences` PATCH endpoint that accepts a JSON body and returns 204 on success.
Deliverables: handler function, request validation, unit tests.
```

> ❌ "Update the user preferences feature"
> ✅ "Implement PATCH /users/:id/preferences — accepts {theme, language, notifications}, returns 204, with validation and tests"

### 2. Background (required, compressible)

Why this task exists and where it came from. One paragraph max. The subagent doesn't need the full product history—just enough to understand motivation.

**If the parent agent has already done prior exploration** (tried an approach, found a dead end, discovered a constraint), state the conclusions here. The subagent must not repeat failed experiments.

```
Part of EPIC-42 (user settings overhaul). Current implementation is a monolithic /settings endpoint that needs拆分. This is the first extracted endpoint.

Note: Previous attempt to use PUT for partial updates was abandoned — PATCH is the correct method per RFC 7396.
```

### 3. Task Boundary (required)

Explicitly state what to do AND what not to do. This is the most commonly missed category.

```
DO:
- Create PATCH handler in src/api/users/preferences.py
- Add pydantic validation for allowed fields
- Write unit tests in tests/api/test_preferences.py

DO NOT:
- Modify the existing /settings endpoint
- Add database migrations (schema already exists)
- Implement authentication (middleware handles it)
- Change the frontend
```

### 4. Key References (required)

Every file, doc, or resource the subagent will touch or need. **Pairing rule:** every file mentioned in the task must appear here.

| Path | Purpose |
|------|---------|
| `src/api/users/__init__.py` | Register the new route |
| `src/schemas/user.py` | Existing UserPreferences schema — reuse or extend |
| `docs/api-spec.md#preferences` | API contract for this endpoint |
| `tests/api/conftest.py` | Shared fixtures for API tests |

> If the subagent **can** access the filesystem: provide path + one-line purpose. Inline a summary of critical content the task directly depends on.
>
> If the subagent **cannot** access the filesystem: inline all necessary content.

### 5. Constraints (required)

Technical constraints, coding standards, and design decisions the subagent must follow.

```
- Python 3.11+, use type hints everywhere
- Follow existing patterns in src/api/users/ (check existing handlers for style)
- Validation: use pydantic, reject unknown fields strictly
- All tests must pass with `pytest tests/api/test_preferences.py -v`
- No new dependencies — use only packages already in requirements.txt
```

### 6. Acceptance Criteria (required)

Executable verification steps, not vague goals.

```
- [ ] `pytest tests/api/test_preferences.py` passes all tests
- [ ] PATCH with valid body returns 204
- [ ] PATCH with invalid fields returns 422 with error details
- [ ] PATCH with unknown fields returns 422 (strict validation)
- [ ] `ruff check src/api/users/preferences.py` — no lint errors
```

### 7. Suggested Steps (optional)

Recommended execution order. Helps the subagent avoid planning drift on complex tasks. Skip for simple changes.

```
1. Read existing handler in src/api/users/settings.py for pattern reference
2. Create src/api/users/preferences.py with route skeleton
3. Add pydantic request schema (extend or reuse from src/schemas/user.py)
4. Implement handler logic (partial update, validation, 204 response)
5. Register route in __init__.py
6. Write tests: happy path → edge cases → error cases
7. Run lint + tests
```

## Reference vs Inline Decision Rules

Core principle: **the subagent must be able to start work immediately from the briefing alone, with zero follow-up questions.**

| Content type | Subagent has filesystem access | Subagent has NO filesystem access |
|-------------|-------------------------------|-----------------------------------|
| Objective | Inline | Inline |
| Task Boundary | Inline | Inline |
| Acceptance Criteria | Inline | Inline |
| Key References | Path + one-line purpose | Inline full content |
| Background | Inline (compressed) | Inline |
| Constraints | Inline | Inline |

### Critical rules

1. **Objective, Task Boundary, Acceptance** → always inline. Non-negotiable.
2. **Key file paths** → always include (as path or inlined content).
3. **Background** → compress freely. The subagent needs the "why," not the history.
4. **Pairing completeness** → every file/resource mentioned anywhere in the briefing must have a corresponding entry in Key References.
5. **Design decisions** → if there's a reason to choose approach A over B, state it in Constraints. The subagent can't ask you.

## Completeness Check

Before sending the briefing, run this self-check.

### The Core Question

> "If I were the subagent, with **zero prior context**, could I start work **immediately** from this briefing alone?"

If the answer isn't a confident "yes," something is missing.

### The Critical Context Question

> "Is there anything the subagent absolutely needs to know that isn't covered by the six categories above? If they don't know this, will they go down a wrong path?"

If yes, add it. Common examples: a known bug in a dependency, a non-obvious coupling between modules, a decision that was made in a prior conversation, a timeout constraint that affects the approach.

### Checklist

- [ ] **Objective** — is the goal clear in one sentence? Does it specify deliverables?
- [ ] **Task Boundary** — is "do" vs "don't do" explicitly stated?
- [ ] **Key References** — does every file mentioned in the briefing appear in the reference list?
- [ ] **Constraints** — are the constraints the subagent is most likely to violate covered?
- [ ] **Acceptance Criteria** — is each criterion executable? (not "it works" but "test X passes with output Y")
- [ ] **Prior exploration** — if the parent agent tried something before, are the conclusions documented in Background?
- [ ] **Critical context** — anything not covered by the six categories that would cause a wrong path if missing?

## Common Failure Patterns

| Pattern | What goes wrong | How this skill prevents it |
|---------|----------------|---------------------------|
| "Just implement X" | No boundary, subagent scope-creeps or guesses wrong | Task Boundary (required) forces explicit DO/DON'T |
| Missing doc paths | Subagent can't find the design doc | Key References with pairing rule |
| "Follow existing code" | Subagent follows the wrong pattern | Key References point to specific files as examples |
| "Make it work" | No clear done condition | Acceptance Criteria must be executable |
| TMI in background | Subagent confused by irrelevant history | Background marked compressible, one paragraph max |
| Repeating failed attempts | Subagent rediscovers a known dead end | Background requires prior exploration conclusions |
| Hidden trap | Subagent hits a non-obvious issue nobody warned about | Critical Context question catches uncategorized knowledge |
