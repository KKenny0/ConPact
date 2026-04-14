"""Tests for registry module."""

from pathlib import Path

from conpact_server.registry import register_agent, list_agents


class TestRegisterAgent:
    def test_register_new_agent(self, project_dir: Path):
        entry = register_agent(
            root=project_dir,
            agent_id="claude-code",
            role="architect",
            capabilities=["code-gen", "review"],
        )
        assert entry["id"] == "claude-code"
        assert entry["role"] == "architect"
        assert entry["status"] == "available"

    def test_register_updates_existing(self, project_dir: Path):
        register_agent(root=project_dir, agent_id="codex", role="executor", capabilities=[])
        entry = register_agent(root=project_dir, agent_id="codex", role="worker", capabilities=["test"])
        assert entry["role"] == "worker"
        agents = list_agents(project_dir)
        assert len(agents) == 1


class TestListAgents:
    def test_empty_registry(self, project_dir: Path):
        assert list_agents(project_dir) == []

    def test_returns_registered_agents(self, project_dir: Path):
        register_agent(root=project_dir, agent_id="a1", role="r1", capabilities=[])
        register_agent(root=project_dir, agent_id="a2", role="r2", capabilities=[])
        agents = list_agents(project_dir)
        assert len(agents) == 2
