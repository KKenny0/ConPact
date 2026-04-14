"""Tests for schema validation."""

import pytest

from conpact_server.schema import validate_delegation, generate_contract_id


class TestValidateDelegation:
    def test_valid_minimal(self):
        validate_delegation(
            objective="Implement X",
            do_items=["Create file.py"],
            do_not_items=[],
            references=[{"path": "file.py", "purpose": "Main file"}],
            constraints=["Python 3.11+"],
            acceptance_criteria=["pytest passes"],
        )

    def test_empty_objective_raises(self):
        with pytest.raises(ValueError, match="objective"):
            validate_delegation(
                objective="",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[{"path": "file.py", "purpose": "Main file"}],
                constraints=["Python 3.11+"],
                acceptance_criteria=["pytest passes"],
            )

    def test_empty_do_items_raises(self):
        with pytest.raises(ValueError, match="do_items"):
            validate_delegation(
                objective="Implement X",
                do_items=[],
                do_not_items=[],
                references=[{"path": "file.py", "purpose": "Main file"}],
                constraints=["Python 3.11+"],
                acceptance_criteria=["pytest passes"],
            )

    def test_empty_references_raises(self):
        with pytest.raises(ValueError, match="references"):
            validate_delegation(
                objective="Implement X",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[],
                constraints=["Python 3.11+"],
                acceptance_criteria=["pytest passes"],
            )

    def test_reference_missing_path_raises(self):
        with pytest.raises(ValueError, match="path"):
            validate_delegation(
                objective="Implement X",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[{"purpose": "Missing path"}],
                constraints=["Python 3.11+"],
                acceptance_criteria=["pytest passes"],
            )

    def test_empty_constraints_raises(self):
        with pytest.raises(ValueError, match="constraints"):
            validate_delegation(
                objective="Implement X",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[{"path": "file.py", "purpose": "Main file"}],
                constraints=[],
                acceptance_criteria=["pytest passes"],
            )

    def test_empty_acceptance_criteria_raises(self):
        with pytest.raises(ValueError, match="acceptance_criteria"):
            validate_delegation(
                objective="Implement X",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[{"path": "file.py", "purpose": "Main file"}],
                constraints=["Python 3.11+"],
                acceptance_criteria=[],
            )


class TestGenerateContractId:
    def test_basic_slug(self):
        result = generate_contract_id(
            objective="Implement PATCH /users/:id/preferences with validation",
            existing_ids=set(),
        )
        assert result.startswith("2026-04-14-implement-patch-users-id")
        assert len(result) <= 60

    def test_collision_appends_counter(self):
        first = generate_contract_id(
            objective="Implement PATCH /users/:id/preferences with validation",
            existing_ids=set(),
        )
        second = generate_contract_id(
            objective="Implement PATCH /users/:id/preferences with validation",
            existing_ids={first},
        )
        assert second != first
        assert second.endswith("-2")

    def test_cjk_characters(self):
        result = generate_contract_id(
            objective="实现用户认证功能模块",
            existing_ids=set(),
        )
        assert len(result) > 0
