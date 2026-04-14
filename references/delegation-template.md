# Delegation Template Reference

Detailed guide for filling the 7-category `delegation` section of a ConPact contract. Read this when you need to construct or review a contract's delegation.

## Table of Contents

1. [objective](#1-objective-required)
2. [background](#2-background-optional)
3. [boundary](#3-boundary-required)
4. [references](#4-references-required)
5. [constraints](#5-constraints-required)
6. [acceptance_criteria](#6-acceptance_criteria-required)
7. [suggested_steps](#7-suggested_steps-optional)
8. [Completeness Check](#completeness-check)

---

## 1. objective (required)

One sentence containing the **goal** and **concrete deliverables**. The assignee should read this and immediately know what to build.

Good — tells you exactly what to build and where:
```
Implement PATCH /users/:id/preferences — accepts {theme, language, notifications}, returns 204, with pydantic validation and unit tests.
```

Bad — no deliverables, no scope:
```
Update the user preferences feature
```

Another good example:
```
Add a CSV export endpoint at GET /reports/transactions — accepts date range filters (from, to as ISO dates), streams the response as text/csv, reuses the existing TransactionQuery service.
```

The key test: can the assignee start coding after reading only this line? If not, add more specificity.

## 2. background (optional)

Why this task exists and any conclusions from prior exploration. One paragraph max. This prevents the assignee from repeating dead-end approaches.

```
Part of EPIC-42 (user settings overhaul). The monolithic /settings endpoint needs splitting — preferences are the first slice.

Prior exploration: PUT for partial updates was abandoned because it requires sending the full object. PATCH is correct per RFC 7396 (JSON Merge Patch). The frontend team has already updated their API client to expect PATCH.
```

What to include:
- Which project/epic this belongs to
- What was tried before and why it didn't work
- Any decisions already made that constrain the implementation
- Dependencies on other teams or ongoing work

What not to include:
- Implementation details (those go in boundary and constraints)
- Vague context ("this is important") without actionable information

## 3. boundary (required)

Explicitly list what to do AND what not to do. This is the most effective tool for preventing scope creep.

```json
{
  "do": [
    "Create PATCH handler in src/api/users/preferences.py",
    "Add pydantic validation for allowed fields (theme, language, notifications)",
    "Write tests in tests/api/test_preferences.py"
  ],
  "do_not": [
    "Modify the existing /settings endpoint",
    "Add database migrations (schema already exists)",
    "Implement authentication (middleware handles it)",
    "Change the frontend"
  ]
}
```

Guidelines:
- Each item in `do` should be a specific, verifiable action — name the file, name the function, name the test.
- `do_not` is not the inverse of `do`. It lists things that a reasonable person might think are in scope but aren't. Think about what an enthusiastic assignee might accidentally touch.
- When in doubt, add more `do_not` items. Over-specifying what's out of scope is cheaper than undoing scope creep.

## 4. references (required)

Every file, doc, or resource the assignee will touch or need. **Pairing rule:** every file path mentioned anywhere in the delegation (boundary, constraints, acceptance_criteria, suggested_steps) must appear here.

```json
[
  {"path": "src/api/users/__init__.py", "purpose": "Register the new route"},
  {"path": "src/schemas/user.py", "purpose": "Existing UserPreferences schema — reuse or extend"},
  {"path": "docs/api-spec.md#preferences", "purpose": "API contract for this endpoint"},
  {"path": "src/api/users/settings.py", "purpose": "Pattern reference — follow the same structure"}
]
```

Guidelines:
- `purpose` should be one sentence: why the assignee needs to look at this file and what they'll find there.
- Order matters. Put the files the assignee will touch first, reference files second.

**Reference vs inline decision:**
- Assignee **has** filesystem access → path + one-line purpose. Inline summaries only for content the task directly depends on (e.g., a schema definition the assignee must match exactly).
- Assignee **has no** filesystem access → inline all necessary content in the reference entry, e.g.: `{"path": "N/A", "purpose": "The UserPreferences schema has fields: theme (str, enum: light/dark/system), language (str, ISO 639-1), notifications (bool)"}`

## 5. constraints (required)

Technical constraints, coding standards, and design decisions the assignee must follow. These are non-negotiable rules, not suggestions.

```
- Python 3.11+, type hints everywhere
- Follow existing patterns in src/api/users/
- pydantic validation, reject unknown fields strictly (model_config = ConfigDict(extra='forbid'))
- No new dependencies
- All database access through existing service layer in src/services/
- Error responses must match the existing error schema in src/schemas/errors.py
```

Think about what the assignee is most likely to get wrong:
- Unwritten conventions in the codebase
- Non-obvious dependencies or couplings
- Performance or security requirements that aren't visible from the code
- Decisions from prior conversations that constrain this task

## 6. acceptance_criteria (required)

Each criterion must be **executable** — not "it works" but a specific test or command with expected output.

```
- pytest tests/api/test_preferences.py passes
- PATCH /users/123/preferences with valid body → 204
- PATCH /users/123/preferences with unknown field "foo" → 422 with error detail "extra fields not permitted"
- PATCH /users/123/preferences with missing required field → 422
- ruff check src/api/users/preferences.py — no errors
```

Bad — not executable:
```
- Works correctly
- Is properly validated
- Handles errors
```

The distinction: "passes test X" is executable. "Works correctly" requires interpretation. The assignee should be able to run each criterion as-is and get a pass/fail.

## 7. suggested_steps (optional)

Recommended execution order for non-trivial tasks. Skip for simple changes where the order is obvious.

```
1. Read src/api/users/settings.py for pattern reference
2. Create src/api/users/preferences.py with route skeleton
3. Add pydantic request schema to src/schemas/user.py
4. Implement handler logic
5. Register route in src/api/users/__init__.py
6. Write tests: happy path → edge cases → error cases
7. Run lint + tests
```

This is a suggestion, not a requirement. The assignee may deviate if they find a better order. The value is in pointing out non-obvious dependencies between steps (e.g., "read the existing pattern first before writing new code").

---

## Completeness Check

Before finalizing the delegation, answer these questions:

1. **"If I were the assignee, with zero prior context, could I start work immediately from this delegation alone?"** — If not confident "yes," something is missing.

2. **"Is there anything the assignee absolutely needs to know that isn't covered by the seven categories?"** — Common gaps:
   - A known bug in a dependency
   - A non-obvious coupling between modules
   - A decision from a prior conversation
   - A timeout or performance constraint
   - The reason something was done a certain way

Checklist:
- [ ] objective — one-sentence goal + specific deliverables
- [ ] boundary — explicit DO and DO NOT
- [ ] references — every file mentioned in the delegation has an entry here
- [ ] constraints — covers the pitfalls the assignee is most likely to hit
- [ ] acceptance_criteria — each criterion is executable (test command or expected HTTP response)
- [ ] Prior exploration — failed attempts and conclusions documented in background
- [ ] Critical context — anything not covered by the six categories that would cause a wrong path
