"""Filesystem path helpers for .agents/ directory structure."""

import json
from pathlib import Path


def get_agents_dir(root: Path) -> Path:
    return root / ".agents"


def get_contracts_dir(root: Path) -> Path:
    return get_agents_dir(root) / "contracts"


def get_archive_dir(root: Path) -> Path:
    return get_contracts_dir(root) / "_archive"


def get_registry_path(root: Path) -> Path:
    return get_agents_dir(root) / "registry.json"


def get_contract_path(root: Path, assignee: str, contract_id: str) -> Path:
    return get_contracts_dir(root) / f"@{assignee}.{contract_id}.json"


def get_project_path(root: Path) -> Path:
    return get_agents_dir(root) / "project.json"


def is_initialized(root: Path) -> bool:
    return get_contracts_dir(root).is_dir()


def validate_project_root(root: Path) -> None:
    """Validate that this .agents/ belongs to the given project root.

    Raises ValueError if project.json is missing or root doesn't match.
    """
    project_path = get_project_path(root)
    if not project_path.exists():
        raise ValueError("Not initialized. Run conpact_init first.")
    stored = json.loads(project_path.read_text(encoding="utf-8"))
    if Path(stored["root"]).resolve() != root.resolve():
        raise ValueError(
            f"Project root mismatch: .agents/ belongs to '{stored['root']}'"
        )
