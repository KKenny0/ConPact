"""Integration tests for the MCP server tool handlers."""

import json
import tempfile
from pathlib import Path

from conpact_server.server import handle_call_tool, handle_list_tools


def _call(name: str, _root: Path | None = None, **kwargs) -> object:
    args = dict(kwargs)
    if _root is not None:
        args["_root"] = _root
    import asyncio
    return asyncio.get_event_loop().run_until_complete(handle_call_tool(name, args))


def _call_sync(name: str, _root: Path | None = None, **kwargs) -> object:
    """Synchronous wrapper for async handle_call_tool."""
    args = dict(kwargs)
    if _root is not None:
        args["_root"] = _root
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, handle_call_tool(name, args))
                return future.result()
        return loop.run_until_complete(handle_call_tool(name, args))
    except RuntimeError:
        return asyncio.run(handle_call_tool(name, args))


def _init_project(tmp: Path) -> Path:
    """Initialize a ConPact project directory."""
    agents_dir = tmp / ".agents"
    agents_dir.mkdir()
    (agents_dir / "contracts").mkdir()
    (agents_dir / "contracts" / "_archive").mkdir()
    (agents_dir / "registry.json").write_text(
        json.dumps({"updated_at": "2026-04-14T00:00:00Z", "agents": []})
    )
    (agents_dir / "project.json").write_text(
        json.dumps({
            "root": str(tmp.resolve()),
            "initialized_at": "2026-04-14T00:00:00Z",
        })
    )
    return tmp


class TestListTools:
    def test_returns_12_tools(self):
        result = asyncio.run(handle_list_tools()) if False else None
        import asyncio
        tools = asyncio.run(handle_list_tools())
        assert len(tools) == 16
        names = [t.name for t in tools]
        assert "conpact_init" in names
        assert "conpact_reassign" in names
        assert "conpact_overview" in names


class TestInitTool:
    def test_init_creates_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _call_sync("conpact_init", _root=root)
            assert not result.isError
            assert (root / ".agents" / "contracts").is_dir()
            assert (root / ".agents" / "registry.json").exists()
            assert (root / ".agents" / "project.json").exists()
            project_data = json.loads(
                (root / ".agents" / "project.json").read_text()
            )
            assert project_data["root"] == str(root.resolve())

    def test_init_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _call_sync("conpact_init", _root=root)
            result = _call_sync("conpact_init", _root=root)
            assert not result.isError


class TestFullLifecycle:
    def test_create_claim_submit_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(Path(tmp))

            # Create with verification commands
            result = _call_sync(
                "conpact_create",
                _root=root,
                caller_id="claude-code",
                assignee="codex",
                objective="Implement feature X in module Y",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[{"path": "file.py", "purpose": "Main"}],
                constraints=["Python 3.11+"],
                acceptance_criteria=["pytest passes"],
                verification=["echo ok"],
            )
            assert not result.isError
            contract = json.loads(result.content[0].text)
            assert contract["status"] == "assigned"
            assert contract["delegation"]["verification"] == ["echo ok"]
            cid = contract["id"]

            # Check
            result = _call_sync("conpact_check", _root=root, agent_id="codex")
            assert not result.isError
            check_data = json.loads(result.content[0].text)
            assert "contracts" in check_data
            assert len(check_data["contracts"]) == 1

            # Claim
            result = _call_sync("conpact_claim", _root=root, caller_id="codex", contract_id=cid)
            assert not result.isError

            # Log
            result = _call_sync(
                "conpact_log",
                _root=root,
                caller_id="codex",
                contract_id=cid,
                type="info",
                message="Starting implementation",
            )
            assert not result.isError
            contract = json.loads(result.content[0].text)
            assert len(contract["log"]) == 1

            # Verify
            result = _call_sync(
                "conpact_verify",
                _root=root,
                caller_id="codex",
                contract_id=cid,
            )
            assert not result.isError
            verify_data = json.loads(result.content[0].text)
            assert verify_data["all_passed"] is True

            # Update progress
            result = _call_sync(
                "conpact_update_progress",
                _root=root,
                caller_id="codex",
                contract_id=cid,
                progress="Halfway done",
            )
            assert not result.isError

            # Submit
            result = _call_sync(
                "conpact_submit",
                _root=root,
                caller_id="codex",
                contract_id=cid,
                summary="Implemented feature X",
                files_changed=["file.py"],
                verification_passed=True,
            )
            assert not result.isError
            contract = json.loads(result.content[0].text)
            assert contract["status"] == "submitted"
            assert contract["result"]["verification_passed"] is True

            # Review (approve)
            result = _call_sync(
                "conpact_review",
                _root=root,
                caller_id="claude-code",
                contract_id=cid,
                review_status="approved",
                feedback="Looks good",
            )
            assert not result.isError
            contract = json.loads(result.content[0].text)
            assert contract["status"] == "closed"


class TestProjectIsolation:
    def test_uninitialized_project_rejected(self):
        """Operations fail when conpact_init has not been called."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _call_sync("conpact_check", _root=root, agent_id="agent-1")
            assert result.isError
            assert "Not initialized" in result.content[0].text

    def test_wrong_root_rejected(self):
        """Operations fail when project.json root doesn't match."""
        with tempfile.TemporaryDirectory() as tmp_a, \
             tempfile.TemporaryDirectory() as tmp_b:
            root_a = _init_project(Path(tmp_a))
            root_b = Path(tmp_b)

            # root_b has .agents/project.json that claims to belong to root_a
            agents_dir_b = root_b / ".agents"
            agents_dir_b.mkdir()
            (agents_dir_b / "project.json").write_text(
                json.dumps({
                    "root": str(root_a.resolve()),
                    "initialized_at": "2026-04-14T00:00:00Z",
                })
            )

            result = _call_sync("conpact_list", _root=root_b)
            assert result.isError
            assert "Project root mismatch" in result.content[0].text

    def test_init_migrates_old_installation(self):
        """conpact_init creates project.json on old .agents/ without it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents_dir = root / ".agents"
            agents_dir.mkdir()
            (agents_dir / "contracts").mkdir()
            (agents_dir / "contracts" / "_archive").mkdir()
            (agents_dir / "registry.json").write_text(
                json.dumps({"updated_at": "2026-04-01T00:00:00Z", "agents": []})
            )
            # No project.json — old installation

            result = _call_sync("conpact_init", _root=root)
            assert not result.isError
            assert (root / ".agents" / "project.json").exists()

            # Operations should work now
            result = _call_sync("conpact_check", _root=root, agent_id="agent-1")
            assert not result.isError


class TestOverviewTool:
    def test_empty_project(self):
        """Overview returns empty state for project with no contracts."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(Path(tmp))
            result = _call_sync("conpact_overview", _root=root, agent_id="agent-1")
            assert not result.isError
            data = json.loads(result.content[0].text)
            assert data["contracts"] == []
            assert data["agents"] == []
            assert data["actions_for_you"] == ["No actions needed."]
            assert data["blocking_on"] == []

    def test_assigned_contract_shows_action(self):
        """Overview suggests claim action when agent has assigned contracts."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(Path(tmp))

            # Create an assigned contract for codex
            _call_sync(
                "conpact_create",
                _root=root,
                caller_id="claude-code",
                assignee="codex",
                objective="Implement feature X",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[{"path": "file.py", "purpose": "Main file"}],
                constraints=["Python 3.11+"],
                acceptance_criteria=["pytest passes"],
            )

            # codex's overview should suggest claiming
            result = _call_sync("conpact_overview", _root=root, agent_id="codex")
            data = json.loads(result.content[0].text)
            assert len(data["contracts"]) == 1
            assert any("assigned contract" in a and "conpact_claim" in a
                       for a in data["actions_for_you"])

            # claude-code's overview should show no actions (delegator waits)
            result = _call_sync("conpact_overview", _root=root, agent_id="claude-code")
            data = json.loads(result.content[0].text)
            assert data["actions_for_you"] == ["No actions needed."]

    def test_submitted_contract_shows_review_action(self):
        """Overview suggests review action for delegator when contract is submitted."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(Path(tmp))

            # Create, claim, and submit a contract
            _call_sync(
                "conpact_create",
                _root=root,
                caller_id="claude-code",
                assignee="codex",
                objective="Implement feature X",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[{"path": "file.py", "purpose": "Main file"}],
                constraints=["Python 3.11+"],
                acceptance_criteria=["pytest passes"],
            )
            cid = json.loads(
                _call_sync("conpact_check", _root=root, agent_id="codex").content[0].text
            )["contracts"][0]["id"]
            _call_sync("conpact_claim", _root=root, caller_id="codex", contract_id=cid)
            _call_sync(
                "conpact_submit",
                _root=root,
                caller_id="codex",
                contract_id=cid,
                summary="Done",
                files_changed=["file.py"],
            )

            # claude-code's overview should suggest review
            result = _call_sync("conpact_overview", _root=root, agent_id="claude-code")
            data = json.loads(result.content[0].text)
            assert any("awaiting review" in a and "conpact_review" in a
                       for a in data["actions_for_you"])

    def test_revision_needed_shows_action_for_assignee(self):
        """Overview suggests revision action for implementer."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_project(Path(tmp))

            # Full lifecycle to revision_needed
            _call_sync(
                "conpact_create",
                _root=root,
                caller_id="claude-code",
                assignee="codex",
                objective="Implement feature X",
                do_items=["Create file.py"],
                do_not_items=[],
                references=[{"path": "file.py", "purpose": "Main file"}],
                constraints=["Python 3.11+"],
                acceptance_criteria=["pytest passes"],
            )
            cid = json.loads(
                _call_sync("conpact_check", _root=root, agent_id="codex").content[0].text
            )["contracts"][0]["id"]
            _call_sync("conpact_claim", _root=root, caller_id="codex", contract_id=cid)
            _call_sync(
                "conpact_submit",
                _root=root,
                caller_id="codex",
                contract_id=cid,
                summary="Done",
                files_changed=["file.py"],
            )
            _call_sync(
                "conpact_review",
                _root=root,
                caller_id="claude-code",
                contract_id=cid,
                review_status="revision_needed",
                feedback="Missing tests",
            )

            result = _call_sync("conpact_overview", _root=root, agent_id="codex")
            data = json.loads(result.content[0].text)
            assert any("revision" in a.lower() and "conpact_submit" in a
                       for a in data["actions_for_you"])
