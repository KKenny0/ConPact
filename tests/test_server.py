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
    return tmp


class TestListTools:
    def test_returns_12_tools(self):
        result = asyncio.run(handle_list_tools()) if False else None
        import asyncio
        tools = asyncio.run(handle_list_tools())
        assert len(tools) == 12
        names = [t.name for t in tools]
        assert "conpact_init" in names
        assert "conpact_reassign" in names


class TestInitTool:
    def test_init_creates_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = _call_sync("conpact_init", _root=root)
            assert not result.isError
            assert (root / ".agents" / "contracts").is_dir()
            assert (root / ".agents" / "registry.json").exists()

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

            # Create
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
            )
            assert not result.isError
            contract = json.loads(result.content[0].text)
            assert contract["status"] == "assigned"
            cid = contract["id"]

            # Check
            result = _call_sync("conpact_check", _root=root, agent_id="codex")
            assert not result.isError
            contracts = json.loads(result.content[0].text)
            assert len(contracts) == 1

            # Claim
            result = _call_sync("conpact_claim", _root=root, caller_id="codex", contract_id=cid)
            assert not result.isError

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
            )
            assert not result.isError
            contract = json.loads(result.content[0].text)
            assert contract["status"] == "submitted"

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
