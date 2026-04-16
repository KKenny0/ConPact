"""Tests for registry module."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

from conpact_server.registry import register_agent, list_agents, heartbeat, get_agent_liveness


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


class TestHeartbeat:
    def test_heartbeat_updates_timestamp(self, project_dir: Path):
        register_agent(root=project_dir, agent_id="codex", role="executor", capabilities=[])
        import time
        time.sleep(0.01)  # ensure timestamp differs
        entry = heartbeat(root=project_dir, agent_id="codex")
        assert entry["last_heartbeat"] is not None
        # Should be recent
        last_dt = datetime.fromisoformat(entry["last_heartbeat"])
        now = datetime.now(timezone.utc)
        assert (now - last_dt).total_seconds() < 5

    def test_heartbeat_updates_status(self, project_dir: Path):
        register_agent(root=project_dir, agent_id="codex", role="executor", capabilities=[])
        entry = heartbeat(root=project_dir, agent_id="codex", current_status="busy")
        assert entry["status"] == "busy"

    def test_heartbeat_unregistered_raises(self, project_dir: Path):
        import pytest
        with pytest.raises(ValueError, match="not registered"):
            heartbeat(root=project_dir, agent_id="unknown-agent")


class TestGetAgentLiveness:
    def test_active_agent_not_stale(self, project_dir: Path):
        register_agent(root=project_dir, agent_id="codex", role="executor", capabilities=[])
        heartbeat(root=project_dir, agent_id="codex")
        liveness = get_agent_liveness(project_dir, "codex")
        assert liveness["is_stale"] is False
        assert liveness["staleness_minutes"] < 1

    def test_stale_agent_detected(self, project_dir: Path):
        register_agent(root=project_dir, agent_id="codex", role="executor", capabilities=[])
        # Manually set old heartbeat
        import json
        reg_path = project_dir / ".agents" / "registry.json"
        reg = json.loads(reg_path.read_text())
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        reg["agents"][0]["last_heartbeat"] = old_time
        reg_path.write_text(json.dumps(reg, indent=2))
        liveness = get_agent_liveness(project_dir, "codex")
        assert liveness["is_stale"] is True

    def test_unknown_agent(self, project_dir: Path):
        liveness = get_agent_liveness(project_dir, "nonexistent")
        assert liveness["status"] == "unknown"
        assert liveness["is_stale"] is True
