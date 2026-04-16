"""Agent registry management."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conpact_server.paths import get_registry_path


def _read_registry(root: Path) -> dict[str, Any]:
    path = get_registry_path(root)
    if not path.exists():
        return {"updated_at": _now_iso(), "agents": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_registry(root: Path, registry: dict[str, Any]) -> None:
    path = get_registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_agent(*, root: Path, agent_id: str, role: str | None = None, capabilities: list[str] | None = None) -> dict[str, Any]:
    """Register or update an agent in the registry."""
    registry = _read_registry(root)
    capabilities = capabilities or []
    entry = {
        "id": agent_id,
        "role": role or "",
        "capabilities": capabilities,
        "status": "available",
        "last_heartbeat": _now_iso(),
    }
    # Update existing or append new
    agents = registry.get("agents", [])
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            agents[i] = entry
            break
    else:
        agents.append(entry)
    registry["agents"] = agents
    registry["updated_at"] = _now_iso()
    _write_registry(root, registry)
    return entry


def list_agents(root: Path) -> list[dict[str, Any]]:
    """List all registered agents."""
    registry = _read_registry(root)
    return registry.get("agents", [])


def heartbeat(*, root: Path, agent_id: str, current_status: str | None = None) -> dict[str, Any]:
    """Update agent's heartbeat timestamp. Must be registered first."""
    registry = _read_registry(root)
    agents = registry.get("agents", [])

    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            agents[i]["last_heartbeat"] = _now_iso()
            if current_status is not None:
                agents[i]["status"] = current_status
            registry["updated_at"] = _now_iso()
            _write_registry(root, registry)
            return agents[i]

    raise ValueError(f"Agent '{agent_id}' not registered. Call conpact_register first.")


def get_agent_liveness(root: Path, agent_id: str, threshold_minutes: int = 30) -> dict[str, Any]:
    """Get liveness info for a specific agent."""
    agents = list_agents(root)
    for a in agents:
        if a["id"] == agent_id:
            last_hb = a.get("last_heartbeat")
            if last_hb:
                last_dt = datetime.fromisoformat(last_hb)
                now = datetime.now(timezone.utc)
                minutes_since = (now - last_dt).total_seconds() / 60
                return {
                    **a,
                    "staleness_minutes": round(minutes_since, 1),
                    "is_stale": minutes_since > threshold_minutes,
                }
            return {**a, "staleness_minutes": None, "is_stale": True}
    return {"id": agent_id, "staleness_minutes": None, "is_stale": True, "status": "unknown"}
