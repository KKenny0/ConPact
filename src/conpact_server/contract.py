"""Contract CRUD, state machine, and atomic writes."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conpact_server.paths import (
    get_contracts_dir,
    get_archive_dir,
    get_contract_path,
)
from conpact_server.schema import validate_delegation, generate_contract_id


class ContractError(Exception):
    """Raised when a contract operation fails."""


# State machine: current_status -> set of allowed next statuses
VALID_TRANSITIONS: dict[str, set[str]] = {
    "assigned": {"in_progress"},
    "in_progress": {"submitted"},
    "submitted": {"closed", "revision_needed"},
    "revision_needed": {"in_progress"},
}


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_contract(path: Path) -> dict[str, Any]:
    """Read a contract JSON file. Raises ContractError if not found."""
    if not path.exists():
        raise ContractError(f"Contract not found: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_contract_atomic(path: Path, contract: dict[str, Any]) -> None:
    """Write contract atomically: write tmp -> rename."""
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    # Atomic rename (on Windows, need os.replace)
    os.replace(tmp_path, path)


def atomic_update(path: Path, updater_fn) -> dict[str, Any]:
    """Read -> apply updater -> verify updated_at unchanged -> write atomically."""
    contract = read_contract(path)
    old_updated_at = contract["updated_at"]
    # Re-read to get the freshest version
    contract = read_contract(path)
    if contract["updated_at"] != old_updated_at:
        raise ContractError("Concurrent modification detected")
    contract = updater_fn(contract)
    contract["updated_at"] = _now_iso()
    write_contract_atomic(path, contract)
    return contract


def find_contracts_by_assignee(root: Path, agent_id: str) -> list[dict]:
    """Find contracts assigned to an agent with claimable statuses."""
    contracts_dir = get_contracts_dir(root)
    results = []
    if not contracts_dir.exists():
        return results
    for f in contracts_dir.glob(f"@{agent_id}.*.json"):
        contract = read_contract(f)
        if contract.get("assignee") == agent_id and contract["status"] in (
            "assigned",
            "revision_needed",
            "in_progress",
        ):
            results.append(contract)
    return results


def find_contract_by_id(root: Path, contract_id: str) -> tuple[Path, dict]:
    """Find a contract by ID, searching contracts/ and _archive/."""
    contracts_dir = get_contracts_dir(root)
    archive_dir = get_archive_dir(root)
    for search_dir in [contracts_dir, archive_dir]:
        if not search_dir.exists():
            continue
        for f in search_dir.glob("*.json"):
            contract = read_contract(f)
            if contract["id"] == contract_id:
                return f, contract
    raise ContractError(f"Contract not found: {contract_id}")


def _get_existing_ids(root: Path) -> set[str]:
    """Collect all existing contract IDs."""
    ids: set[str] = set()
    contracts_dir = get_contracts_dir(root)
    archive_dir = get_archive_dir(root)
    for d in [contracts_dir, archive_dir]:
        if d.exists():
            for f in d.glob("*.json"):
                try:
                    c = read_contract(f)
                    ids.add(c["id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


def create_contract(
    *,
    root: Path,
    caller_id: str,
    assignee: str,
    objective: str,
    background: str | None = None,
    do_items: list[str],
    do_not_items: list[str],
    references: list[dict],
    constraints: list[str],
    acceptance_criteria: list[str],
    suggested_steps: list[str] | None = None,
    priority: str = "medium",
) -> dict[str, Any]:
    """Create a new contract."""
    validate_delegation(
        objective=objective,
        do_items=do_items,
        do_not_items=do_not_items,
        references=references,
        constraints=constraints,
        acceptance_criteria=acceptance_criteria,
    )

    existing_ids = _get_existing_ids(root)
    contract_id = generate_contract_id(objective, existing_ids)
    now = _now_iso()

    contract: dict[str, Any] = {
        "protocol_version": "1.0",
        "id": contract_id,
        "status": "assigned",
        "from": caller_id,
        "assignee": assignee,
        "priority": priority,
        "created_at": now,
        "updated_at": now,
        "delegation": {
            "objective": objective,
            "background": background,
            "boundary": {"do": do_items, "do_not": do_not_items},
            "references": references,
            "constraints": constraints,
            "acceptance_criteria": acceptance_criteria,
            "suggested_steps": suggested_steps,
        },
        "diligence": None,
        "result": None,
        "discernment": None,
        "last_diligence_at": None,
    }

    path = get_contract_path(root, assignee, contract_id)
    write_contract_atomic(path, contract)
    return contract


def claim_contract(*, root: Path, caller_id: str, contract_id: str) -> dict[str, Any]:
    """Claim an assigned contract."""
    path, contract = find_contract_by_id(root, contract_id)

    if contract["assignee"] != caller_id:
        raise ContractError(f"Assignee mismatch: contract assigned to '{contract['assignee']}', not '{caller_id}'")

    if not can_transition(contract["status"], "in_progress"):
        raise ContractError(f"Cannot claim contract in status '{contract['status']}'")

    now = _now_iso()
    contract["status"] = "in_progress"
    contract["updated_at"] = now
    contract["last_diligence_at"] = now
    write_contract_atomic(path, contract)
    return contract


def update_progress(
    *,
    root: Path,
    caller_id: str,
    contract_id: str,
    progress: str | None,
    blockers: list[str] | None,
    next_check_in: str | None,
) -> dict[str, Any]:
    """Update diligence progress on an in-progress contract."""
    path, contract = find_contract_by_id(root, contract_id)

    if contract["assignee"] != caller_id:
        raise ContractError(f"Assignee mismatch: contract assigned to '{contract['assignee']}'")

    if contract["status"] != "in_progress":
        raise ContractError(f"Can only update progress on 'in_progress' contracts, got '{contract['status']}'")

    now = _now_iso()
    diligence = contract.get("diligence") or {"progress": None, "blockers": [], "next_check_in": None}

    if progress is not None:
        diligence["progress"] = progress
    if blockers is not None:
        diligence["blockers"] = blockers
    if next_check_in is not None:
        diligence["next_check_in"] = next_check_in

    contract["diligence"] = diligence
    contract["last_diligence_at"] = now
    contract["updated_at"] = now
    write_contract_atomic(path, contract)
    return contract


def submit_contract(
    *,
    root: Path,
    caller_id: str,
    contract_id: str,
    summary: str,
    files_changed: list[str],
    verification: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Submit completed work."""
    path, contract = find_contract_by_id(root, contract_id)

    if contract["assignee"] != caller_id:
        raise ContractError(f"Assignee mismatch")

    if not can_transition(contract["status"], "submitted"):
        raise ContractError(f"Cannot submit from status '{contract['status']}'")

    now = _now_iso()
    contract["result"] = {
        "summary": summary,
        "files_changed": files_changed,
        "verification": verification,
        "notes": notes,
    }
    contract["status"] = "submitted"
    contract["updated_at"] = now
    write_contract_atomic(path, contract)
    return contract


def review_contract(
    *,
    root: Path,
    caller_id: str,
    contract_id: str,
    review_status: str,
    feedback: str | None,
    requested_changes: list[str] | None = None,
) -> dict[str, Any]:
    """Review a submitted contract."""
    path, contract = find_contract_by_id(root, contract_id)

    if contract["from"] != caller_id:
        raise ContractError(f"Only the delegator can review")

    if contract["status"] != "submitted":
        raise ContractError(f"Can only review 'submitted' contracts, got '{contract['status']}'")

    now = _now_iso()
    contract["discernment"] = {
        "review_status": review_status,
        "feedback": feedback,
        "requested_changes": requested_changes,
    }

    if review_status == "approved":
        contract["status"] = "closed"
        contract["updated_at"] = now
        # Move to archive
        archive_dir = get_archive_dir(root)
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / path.name
        os.replace(str(path), str(archive_path))
        return contract
    elif review_status == "revision_needed":
        if not can_transition("submitted", "revision_needed"):
            raise ContractError("Invalid transition")
        contract["status"] = "revision_needed"
        contract["updated_at"] = now
        write_contract_atomic(path, contract)
        return contract
    else:
        raise ContractError(f"Invalid review_status: {review_status}")


def close_contract(
    *,
    root: Path,
    caller_id: str,
    contract_id: str,
    reason: str,
) -> dict[str, Any]:
    """Force-close a contract."""
    path, contract = find_contract_by_id(root, contract_id)

    if contract["status"] == "closed":
        raise ContractError("Contract is already closed")

    if contract["from"] != caller_id:
        raise ContractError("Only the delegator can close a contract")

    now = _now_iso()
    existing_feedback = (contract.get("discernment") or {}).get("feedback") or ""
    contract["discernment"] = {
        "review_status": "closed",
        "feedback": f"{existing_feedback}\nForce-closed: {reason}".strip(),
        "requested_changes": None,
    }
    contract["status"] = "closed"
    contract["updated_at"] = now

    archive_dir = get_archive_dir(root)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / path.name
    os.replace(str(path), str(archive_path))
    return contract


def reassign_contract(
    *,
    root: Path,
    caller_id: str,
    contract_id: str,
    new_assignee: str,
) -> dict[str, Any]:
    """Reassign a stale contract."""
    path, contract = find_contract_by_id(root, contract_id)

    if contract["from"] != caller_id:
        raise ContractError("Only the delegator can reassign")

    if contract["status"] != "in_progress":
        raise ContractError("Can only reassign 'in_progress' contracts")

    # Dual-condition staleness check
    now = datetime.now(timezone.utc)
    last_diligence = contract.get("last_diligence_at")
    if last_diligence:
        last_dt = datetime.fromisoformat(last_diligence)
        minutes_idle = (now - last_dt).total_seconds() / 60
    else:
        raise ContractError("No diligence timestamp; cannot verify staleness")

    if minutes_idle < 30:
        raise ContractError(f"Contract updated {minutes_idle:.0f} minutes ago (requires 30 min inactivity)")

    diligence = contract.get("diligence") or {}
    next_check_in = diligence.get("next_check_in")
    if next_check_in:
        next_dt = datetime.fromisoformat(next_check_in)
        if now < next_dt:
            raise ContractError(f"next_check_in ({next_check_in}) has not passed yet")

    # Reassign
    old_assignee = contract["assignee"]
    contract["assignee"] = new_assignee
    contract["status"] = "assigned"
    contract["last_diligence_at"] = None
    contract["updated_at"] = _now_iso()

    bg = contract["delegation"].get("background") or ""
    contract["delegation"]["background"] = f"{bg}\nReassigned from {old_assignee} due to inactivity.".strip()

    # Write to new path
    new_path = get_contract_path(root, new_assignee, contract["id"])
    write_contract_atomic(new_path, contract)
    # Remove old file
    path.unlink()
    return contract
