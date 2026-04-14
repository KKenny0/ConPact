"""Tests for paths module."""

import tempfile
from pathlib import Path

from conpact_server.paths import (
    get_agents_dir,
    get_contracts_dir,
    get_archive_dir,
    get_registry_path,
    get_contract_path,
    is_initialized,
)


class TestGetAgentsDir:
    def test_returns_agents_dir_under_root(self, project_dir: Path):
        result = get_agents_dir(project_dir)
        assert result == project_dir / ".agents"


class TestIsInitialized:
    def test_true_when_agents_dir_exists(self, project_dir: Path):
        assert is_initialized(project_dir) is True

    def test_false_when_agents_dir_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert is_initialized(Path(tmp)) is False


class TestGetContractPath:
    def test_returns_path_with_assignee_prefix(self, project_dir: Path):
        result = get_contract_path(project_dir, "codex", "2026-04-14-task-auth")
        expected = project_dir / ".agents" / "contracts" / "@codex.2026-04-14-task-auth.json"
        assert result == expected
