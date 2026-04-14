"""Filesystem path helpers for .agents/ directory structure."""

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


def is_initialized(root: Path) -> bool:
    return get_contracts_dir(root).is_dir()
