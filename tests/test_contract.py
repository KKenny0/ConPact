"""Tests for contract module."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conpact_server.contract import (
    VALID_TRANSITIONS,
    can_transition,
    read_contract,
    write_contract_atomic,
    find_contracts_by_assignee,
    find_contract_by_id,
    create_contract,
    claim_contract,
    update_progress,
    submit_contract,
    review_contract,
    close_contract,
    reassign_contract,
    append_log_entry,
    run_verification,
    ContractError,
)


class TestStateMachine:
    def test_valid_transitions(self):
        assert can_transition("assigned", "in_progress")
        assert can_transition("in_progress", "submitted")
        assert can_transition("submitted", "closed")
        assert can_transition("submitted", "revision_needed")
        assert can_transition("revision_needed", "in_progress")

    def test_invalid_transitions(self):
        assert not can_transition("assigned", "closed")
        assert not can_transition("closed", "assigned")
        assert not can_transition("in_progress", "assigned")


class TestReadWriteContract:
    def test_write_and_read_roundtrip(self, project_dir: Path):
        contract = {
            "protocol_version": "1.0",
            "id": "2026-04-14-test",
            "status": "assigned",
            "from": "claude-code",
            "assignee": "codex",
            "priority": "medium",
            "created_at": "2026-04-14T10:00:00Z",
            "updated_at": "2026-04-14T10:00:00Z",
            "delegation": {"objective": "Test"},
            "diligence": None,
            "result": None,
            "discernment": None,
        }
        path = project_dir / ".agents" / "contracts" / "@codex.2026-04-14-test.json"
        write_contract_atomic(path, contract)
        result = read_contract(path)
        assert result["id"] == "2026-04-14-test"
        assert result["status"] == "assigned"

    def test_read_nonexistent_raises(self, project_dir: Path):
        path = project_dir / ".agents" / "contracts" / "@codex.nonexistent.json"
        with pytest.raises(ContractError, match="not found"):
            read_contract(path)


class TestCreateContract:
    def test_creates_contract_file(self, project_dir: Path):
        contract = create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X in module Y",
            background="Part of EPIC-42",
            do_items=["Create file.py"],
            do_not_items=["Modify existing endpoint"],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
            suggested_steps=None,
            priority="high",
        )
        assert contract["status"] == "assigned"
        assert contract["from"] == "claude-code"
        assert contract["assignee"] == "codex"
        assert contract["priority"] == "high"
        # Verify file exists on disk
        files = list((project_dir / ".agents" / "contracts").glob("*.json"))
        assert len(files) == 1


class TestClaimContract:
    def test_claim_assigned_contract(self, project_dir: Path):
        create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X in module Y",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
        )
        cid = find_contracts_by_assignee(project_dir, "codex")[0]["id"]
        result = claim_contract(root=project_dir, caller_id="codex", contract_id=cid)
        assert result["status"] == "in_progress"
        assert result["last_diligence_at"] is not None

    def test_claim_wrong_assignee_raises(self, project_dir: Path):
        create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X in module Y",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
        )
        cid = find_contracts_by_assignee(project_dir, "codex")[0]["id"]
        with pytest.raises(ContractError, match="mismatch"):
            claim_contract(root=project_dir, caller_id="wrong-agent", contract_id=cid)


class TestSubmitContract:
    def test_submit_completed_work(self, project_dir: Path):
        create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X in module Y",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
        )
        cid = find_contracts_by_assignee(project_dir, "codex")[0]["id"]
        claim_contract(root=project_dir, caller_id="codex", contract_id=cid)
        result = submit_contract(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
            summary="Implemented feature X",
            files_changed=["file.py"],
            verification="All tests pass",
            notes=None,
        )
        assert result["status"] == "submitted"
        assert result["result"]["summary"] == "Implemented feature X"


class TestReviewContract:
    def test_approve_archives(self, project_dir: Path):
        create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X in module Y",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
        )
        cid = find_contracts_by_assignee(project_dir, "codex")[0]["id"]
        claim_contract(root=project_dir, caller_id="codex", contract_id=cid)
        submit_contract(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
            summary="Done",
            files_changed=["file.py"],
        )
        result = review_contract(
            root=project_dir,
            caller_id="claude-code",
            contract_id=cid,
            review_status="approved",
            feedback="Looks good",
        )
        assert result["status"] == "closed"
        # File should be in archive
        archive_files = list((project_dir / ".agents" / "contracts" / "_archive").glob("*.json"))
        assert len(archive_files) == 1

    def test_revision_needed(self, project_dir: Path):
        create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X in module Y",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
        )
        cid = find_contracts_by_assignee(project_dir, "codex")[0]["id"]
        claim_contract(root=project_dir, caller_id="codex", contract_id=cid)
        submit_contract(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
            summary="Done",
            files_changed=["file.py"],
        )
        result = review_contract(
            root=project_dir,
            caller_id="claude-code",
            contract_id=cid,
            review_status="revision_needed",
            feedback="Missing tests",
            requested_changes=["Add unit tests"],
        )
        assert result["status"] == "revision_needed"


class TestAppendLogEntry:
    def _make_contract(self, project_dir: Path) -> str:
        create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
        )
        return find_contracts_by_assignee(project_dir, "codex")[0]["id"]

    def test_append_info_entry(self, project_dir: Path):
        cid = self._make_contract(project_dir)
        result = append_log_entry(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
            entry_type="info",
            message="Started reading reference files",
        )
        assert len(result["log"]) == 1
        assert result["log"][0]["type"] == "info"
        assert result["log"][0]["message"] == "Started reading reference files"
        assert result["log"][0]["author"] == "codex"
        assert result["log"][0]["timestamp"] is not None

    def test_append_multiple_types(self, project_dir: Path):
        cid = self._make_contract(project_dir)
        for t in ["info", "decision", "blocker", "discovery"]:
            append_log_entry(
                root=project_dir,
                caller_id="codex",
                contract_id=cid,
                entry_type=t,
                message=f"Entry of type {t}",
            )
        _, contract = find_contract_by_id(project_dir, cid)
        assert len(contract["log"]) == 4

    def test_non_participant_rejected(self, project_dir: Path):
        cid = self._make_contract(project_dir)
        with pytest.raises(ContractError, match="participant"):
            append_log_entry(
                root=project_dir,
                caller_id="random-agent",
                contract_id=cid,
                entry_type="info",
                message="Should fail",
            )

    def test_delegator_can_append(self, project_dir: Path):
        cid = self._make_contract(project_dir)
        result = append_log_entry(
            root=project_dir,
            caller_id="claude-code",
            contract_id=cid,
            entry_type="decision",
            message="Use JWT for auth",
        )
        assert len(result["log"]) == 1

    def test_v1_contract_compat(self, project_dir: Path):
        """V1 contract without 'log' field should work with log append."""
        cid = self._make_contract(project_dir)
        # Manually remove log field to simulate v1
        path, contract = find_contract_by_id(project_dir, cid)
        del contract["log"]
        write_contract_atomic(path, contract)

        result = append_log_entry(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
            entry_type="info",
            message="Works on v1 contract",
        )
        assert len(result["log"]) == 1

    def test_with_metadata(self, project_dir: Path):
        cid = self._make_contract(project_dir)
        result = append_log_entry(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
            entry_type="decision",
            message="Chose approach A",
            metadata={"file": "src/auth.py", "alternatives": ["A", "B"]},
        )
        assert result["log"][0]["metadata"]["file"] == "src/auth.py"


class TestRunVerification:
    def _make_contract_with_verification(self, project_dir: Path, commands: list[str]) -> str:
        create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
            verification=commands,
        )
        return find_contracts_by_assignee(project_dir, "codex")[0]["id"]

    def test_run_passing_command(self, project_dir: Path):
        cid = self._make_contract_with_verification(project_dir, ["echo hello"])
        result = run_verification(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
        )
        assert len(result["verification_results"]) == 1
        assert result["verification_results"][0]["passed"] is True
        assert result["verification_results"][0]["exit_code"] == 0
        assert "hello" in result["verification_results"][0]["stdout"]

    def test_run_failing_command(self, project_dir: Path):
        cid = self._make_contract_with_verification(project_dir, ["exit 1"])
        result = run_verification(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
        )
        assert result["verification_results"][0]["passed"] is False
        assert result["verification_results"][0]["exit_code"] == 1

    def test_no_verification_commands_raises(self, project_dir: Path):
        create_contract(
            root=project_dir,
            caller_id="claude-code",
            assignee="codex",
            objective="Implement feature X",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
        )
        cid = find_contracts_by_assignee(project_dir, "codex")[0]["id"]
        with pytest.raises(ContractError, match="No verification commands"):
            run_verification(root=project_dir, caller_id="codex", contract_id=cid)

    def test_non_participant_rejected(self, project_dir: Path):
        cid = self._make_contract_with_verification(project_dir, ["echo hello"])
        with pytest.raises(ContractError, match="participant"):
            run_verification(root=project_dir, caller_id="random-agent", contract_id=cid)

    def test_multiple_commands(self, project_dir: Path):
        cid = self._make_contract_with_verification(project_dir, ["echo first", "echo second"])
        result = run_verification(
            root=project_dir,
            caller_id="codex",
            contract_id=cid,
        )
        assert len(result["verification_results"]) == 2
        assert all(r["passed"] for r in result["verification_results"])

    def test_delegator_can_run(self, project_dir: Path):
        cid = self._make_contract_with_verification(project_dir, ["echo hello"])
        result = run_verification(
            root=project_dir,
            caller_id="claude-code",
            contract_id=cid,
        )
        assert result["verification_results"][0]["passed"] is True
