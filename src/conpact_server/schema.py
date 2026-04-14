"""JSON schema definitions and validation for ConPact contracts."""

import re
import unicodedata
from datetime import date


def validate_delegation(
    *,
    objective: str,
    do_items: list[str],
    do_not_items: list[str],
    references: list[dict],
    constraints: list[str],
    acceptance_criteria: list[str],
) -> None:
    """Validate required delegation fields. Raises ValueError on failure."""
    if not objective or not objective.strip():
        raise ValueError("'objective' must be a non-empty string")

    if not do_items:
        raise ValueError("'do_items' must be a non-empty list")

    if not references:
        raise ValueError("'references' must be a non-empty list")

    for i, ref in enumerate(references):
        if "path" not in ref or not ref["path"]:
            raise ValueError(f"'references[{i}]' must have a 'path' field")
        if "purpose" not in ref or not ref["purpose"]:
            raise ValueError(f"'references[{i}]' must have a 'purpose' field")

    if not constraints:
        raise ValueError("'constraints' must be a non-empty list")

    if not acceptance_criteria:
        raise ValueError("'acceptance_criteria' must be a non-empty list")


def _slugify(text: str, max_words: int = 5, max_len: int = 40) -> str:
    """Convert text to a URL-safe slug."""
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)
    # Lowercase
    text = text.lower()
    # Replace non-alphanumeric with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)
    # Strip leading/trailing hyphens
    text = text.strip("-")
    # Take first N words
    words = text.split("-")[:max_words]
    slug = "-".join(words)
    # Truncate
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "contract"


def generate_contract_id(objective: str, existing_ids: set[str]) -> str:
    """Generate a unique contract ID: YYYY-MM-DD-<slug>."""
    today = date.today().isoformat()
    slug = _slugify(objective)
    base_id = f"{today}-{slug}"

    if base_id not in existing_ids:
        return base_id

    counter = 2
    while f"{today}-{slug}-{counter}" in existing_ids:
        counter += 1
    return f"{today}-{slug}-{counter}"
