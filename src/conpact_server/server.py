"""ConPact MCP Server — tool registration and dispatch."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anyio
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
)

from conpact_server.contract import (
    ContractError,
    create_contract,
    claim_contract,
    update_progress,
    submit_contract,
    review_contract,
    close_contract,
    reassign_contract,
    append_log_entry,
    run_verification,
    find_contracts_by_assignee,
    find_contract_by_id,
)
from conpact_server.paths import (
    get_agents_dir,
    get_contracts_dir,
    get_archive_dir,
    get_registry_path,
    is_initialized,
)
from conpact_server.registry import (
    register_agent,
    list_agents,
    heartbeat as registry_heartbeat,
    get_agent_liveness,
)


def _error(msg: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=f"Error: {msg}")], isError=True
    )


def _ok(data: Any) -> CallToolResult:
    text = (
        json.dumps(data, indent=2, ensure_ascii=False)
        if not isinstance(data, str)
        else data
    )
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Tool definitions
TOOLS = [
    Tool(
        name="conpact_init",
        description="Initialize ConPact multi-agent coordination for the current project. Creates the .agents/ directory with contracts/ and registry.json. Run this once per project when you want to enable multi-agent collaboration. No-op if already initialized.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="conpact_register",
        description="Register your agent identity in the ConPact registry. Other agents use this to discover who is available. Call once when starting in a ConPact-enabled project. Registration is advisory.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Unique identifier (e.g., 'claude-code')",
                },
                "role": {"type": "string", "description": "Role description"},
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Capability tags",
                },
            },
            "required": ["agent_id"],
        },
    ),
    Tool(
        name="conpact_create",
        description="Create a ConPact contract to delegate a task to another agent. 'objective' should be one sentence with concrete deliverables. 'do_items' lists what to do; 'do_not_items' what NOT to do. 'references' pairs each file path with a one-line purpose. 'acceptance_criteria' must be executable (e.g., 'test X passes').",
        inputSchema={
            "type": "object",
            "required": [
                "caller_id",
                "assignee",
                "objective",
                "do_items",
                "do_not_items",
                "references",
                "constraints",
                "acceptance_criteria",
            ],
            "properties": {
                "caller_id": {"type": "string", "description": "Your agent ID"},
                "assignee": {
                    "type": "string",
                    "description": "Agent ID of the assignee",
                },
                "objective": {
                    "type": "string",
                    "description": "One-sentence goal + deliverables",
                },
                "background": {"type": "string", "description": "Why this task exists"},
                "do_items": {"type": "array", "items": {"type": "string"}},
                "do_not_items": {"type": "array", "items": {"type": "string"}},
                "references": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "purpose": {"type": "string"},
                        },
                        "required": ["path", "purpose"],
                    },
                },
                "constraints": {"type": "array", "items": {"type": "string"}},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                "suggested_steps": {"type": "array", "items": {"type": "string"}},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "verification": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Verification commands (e.g., ['pytest tests/', 'ruff check src/'])",
                },
            },
        },
    ),
    Tool(
        name="conpact_check",
        description="Check for contracts assigned to you. Returns 'assigned' (new), 'revision_needed' (rework), and 'in_progress' (crash recovery). Call at session start and after completing tasks.",
        inputSchema={
            "type": "object",
            "required": ["agent_id"],
            "properties": {
                "agent_id": {"type": "string", "description": "Your agent ID"}
            },
        },
    ),
    Tool(
        name="conpact_claim",
        description="Claim an assigned contract and start working. Transitions 'assigned' to 'in_progress'. Fails if already claimed. Always call before starting work.",
        inputSchema={
            "type": "object",
            "required": ["caller_id", "contract_id"],
            "properties": {
                "caller_id": {"type": "string", "description": "Your agent ID"},
                "contract_id": {
                    "type": "string",
                    "description": "The contract ID to claim",
                },
            },
        },
    ),
    Tool(
        name="conpact_update_progress",
        description="Update progress on your contract. Merges provided fields; omitted fields preserved. Setting 'next_check_in' prevents premature reassignment.",
        inputSchema={
            "type": "object",
            "required": ["caller_id", "contract_id"],
            "properties": {
                "caller_id": {"type": "string"},
                "contract_id": {"type": "string"},
                "progress": {"type": "string"},
                "blockers": {"type": "array", "items": {"type": "string"}},
                "next_check_in": {
                    "type": "string",
                    "description": "ISO 8601 timestamp",
                },
            },
        },
    ),
    Tool(
        name="conpact_submit",
        description="Submit completed work. 'summary' is what you did, 'files_changed' which files you modified. The delegator will review.",
        inputSchema={
            "type": "object",
            "required": ["caller_id", "contract_id", "summary", "files_changed"],
            "properties": {
                "caller_id": {"type": "string"},
                "contract_id": {"type": "string"},
                "summary": {"type": "string"},
                "files_changed": {"type": "array", "items": {"type": "string"}},
                "verification": {"type": "string"},
                "verification_passed": {
                    "type": "boolean",
                    "description": "Whether verification commands passed",
                },
                "notes": {"type": "string"},
            },
        },
    ),
    Tool(
        name="conpact_review",
        description="Review a submitted contract. 'approved' archives it; 'revision_needed' sends it back. Only the delegator can review.",
        inputSchema={
            "type": "object",
            "required": ["caller_id", "contract_id", "review_status"],
            "properties": {
                "caller_id": {"type": "string"},
                "contract_id": {"type": "string"},
                "review_status": {
                    "type": "string",
                    "enum": ["approved", "revision_needed"],
                },
                "feedback": {"type": "string"},
                "requested_changes": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    Tool(
        name="conpact_close",
        description="Force-close a contract regardless of status. Only the delegator can close. Provide a reason.",
        inputSchema={
            "type": "object",
            "required": ["caller_id", "contract_id", "reason"],
            "properties": {
                "caller_id": {"type": "string"},
                "contract_id": {"type": "string"},
                "reason": {"type": "string"},
            },
        },
    ),
    Tool(
        name="conpact_read",
        description="Read the full details of a specific contract — delegation, diligence, result, discernment.",
        inputSchema={
            "type": "object",
            "required": ["contract_id"],
            "properties": {"contract_id": {"type": "string"}},
        },
    ),
    Tool(
        name="conpact_list",
        description="List contracts with optional filters. Use to get an overview of work in the project.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "assignee": {"type": "string"},
                "from": {"type": "string"},
                "include_archived": {"type": "boolean"},
            },
        },
    ),
    Tool(
        name="conpact_reassign",
        description="Reassign a stale contract. Requires 30+ min inactivity AND next_check_in expired. Only the delegator can reassign.",
        inputSchema={
            "type": "object",
            "required": ["caller_id", "contract_id", "new_assignee"],
            "properties": {
                "caller_id": {"type": "string"},
                "contract_id": {"type": "string"},
                "new_assignee": {"type": "string"},
            },
        },
    ),
    Tool(
        name="conpact_log",
        description="Append an immutable log entry to a contract. Creates a shared audit trail for decisions, discoveries, blockers, and progress notes. Any contract participant (assignee or delegator) can append. Entries are append-only.",
        inputSchema={
            "type": "object",
            "required": ["caller_id", "contract_id", "type", "message"],
            "properties": {
                "caller_id": {"type": "string", "description": "Your agent ID"},
                "contract_id": {"type": "string", "description": "The contract ID"},
                "type": {
                    "type": "string",
                    "enum": ["info", "decision", "blocker", "discovery"],
                    "description": "Entry type",
                },
                "message": {"type": "string", "description": "Log message content"},
                "metadata": {
                    "type": "object",
                    "description": "Optional structured metadata",
                },
            },
        },
    ),
    Tool(
        name="conpact_heartbeat",
        description="Report agent liveness. Call periodically to indicate you are still active. Must be registered first.",
        inputSchema={
            "type": "object",
            "required": ["agent_id"],
            "properties": {
                "agent_id": {"type": "string", "description": "Your agent ID"},
                "current_status": {
                    "type": "string",
                    "enum": ["available", "busy"],
                    "description": "Optional: update your status in the registry",
                },
            },
        },
    ),
    Tool(
        name="conpact_verify",
        description="Run verification commands defined in a contract's delegation. Captures command output, exit codes, and pass/fail status. Does not change contract status. Any participant can run verification at any time.",
        inputSchema={
            "type": "object",
            "required": ["caller_id", "contract_id"],
            "properties": {
                "caller_id": {"type": "string", "description": "Your agent ID"},
                "contract_id": {
                    "type": "string",
                    "description": "The contract ID to verify",
                },
            },
        },
    ),
]


# Create the MCP server instance
server = Server("conpact")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> CallToolResult:
    arguments = dict(arguments or {})
    try:
        if name == "conpact_init":
            return _handle_init(arguments)
        elif name == "conpact_register":
            return _handle_register(arguments)
        elif name == "conpact_create":
            return _handle_create(arguments)
        elif name == "conpact_check":
            return _handle_check(arguments)
        elif name == "conpact_claim":
            return _handle_claim(arguments)
        elif name == "conpact_update_progress":
            return _handle_update_progress(arguments)
        elif name == "conpact_submit":
            return _handle_submit(arguments)
        elif name == "conpact_review":
            return _handle_review(arguments)
        elif name == "conpact_close":
            return _handle_close(arguments)
        elif name == "conpact_read":
            return _handle_read(arguments)
        elif name == "conpact_list":
            return _handle_list(arguments)
        elif name == "conpact_reassign":
            return _handle_reassign(arguments)
        elif name == "conpact_log":
            return _handle_log(arguments)
        elif name == "conpact_heartbeat":
            return _handle_heartbeat(arguments)
        elif name == "conpact_verify":
            return _handle_verify(arguments)
        else:
            return _error(f"Unknown tool: {name}")
    except ContractError as e:
        return _error(str(e))
    except Exception as e:
        return _error(f"Unexpected error: {e}")


def _get_root(arguments: dict) -> Path:
    """Extract project root from arguments. Falls back to CWD."""
    root = arguments.pop("_root", None) or os.getcwd()
    return Path(root)


def _handle_init(args: dict) -> CallToolResult:
    root = _get_root(args)
    agents_dir = get_agents_dir(root)
    if agents_dir.is_dir():
        return _ok("ConPact already initialized")
    agents_dir.mkdir(parents=True)
    (get_contracts_dir(root)).mkdir(parents=True)
    (get_archive_dir(root)).mkdir(parents=True)
    registry = get_registry_path(root)
    registry.write_text(
        json.dumps({"updated_at": _now_iso(), "agents": []}), encoding="utf-8"
    )
    return _ok("ConPact initialized")


def _handle_register(args: dict) -> CallToolResult:
    root = _get_root(args)
    entry = register_agent(
        root=root,
        agent_id=args["agent_id"],
        role=args.get("role"),
        capabilities=args.get("capabilities", []),
    )
    return _ok(entry)


def _handle_create(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = create_contract(
        root=root,
        caller_id=args["caller_id"],
        assignee=args["assignee"],
        objective=args["objective"],
        background=args.get("background"),
        do_items=args["do_items"],
        do_not_items=args["do_not_items"],
        references=args["references"],
        constraints=args["constraints"],
        acceptance_criteria=args["acceptance_criteria"],
        suggested_steps=args.get("suggested_steps"),
        priority=args.get("priority", "medium"),
        verification=args.get("verification"),
    )
    return _ok(contract)


def _handle_check(args: dict) -> CallToolResult:
    root = _get_root(args)
    agent_id = args["agent_id"]
    contracts = find_contracts_by_assignee(root, agent_id)
    liveness = get_agent_liveness(root, agent_id)
    return _ok({"contracts": contracts, "agent_liveness": liveness})


def _handle_claim(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = claim_contract(
        root=root, caller_id=args["caller_id"], contract_id=args["contract_id"]
    )
    return _ok(contract)


def _handle_update_progress(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = update_progress(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
        progress=args.get("progress"),
        blockers=args.get("blockers"),
        next_check_in=args.get("next_check_in"),
    )
    return _ok(contract)


def _handle_submit(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = submit_contract(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
        summary=args["summary"],
        files_changed=args["files_changed"],
        verification=args.get("verification"),
        verification_passed=args.get("verification_passed"),
        notes=args.get("notes"),
    )
    return _ok(contract)


def _handle_review(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = review_contract(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
        review_status=args["review_status"],
        feedback=args.get("feedback"),
        requested_changes=args.get("requested_changes"),
    )
    return _ok(contract)


def _handle_close(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = close_contract(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
        reason=args["reason"],
    )
    return _ok(contract)


def _handle_read(args: dict) -> CallToolResult:
    root = _get_root(args)
    _, contract = find_contract_by_id(root, args["contract_id"])
    return _ok(contract)


def _handle_list(args: dict) -> CallToolResult:
    root = _get_root(args)
    contracts_dir = get_contracts_dir(root)
    results = []
    search_dirs = [contracts_dir]
    if args.get("include_archived"):
        search_dirs.append(get_archive_dir(root))

    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            try:
                c = json.loads(f.read_text(encoding="utf-8"))
                if args.get("status") and c.get("status") != args["status"]:
                    continue
                if args.get("assignee") and c.get("assignee") != args["assignee"]:
                    continue
                if args.get("from") and c.get("from") != args["from"]:
                    continue
                results.append(c)
            except (json.JSONDecodeError, KeyError):
                pass
    return _ok(results)


def _handle_reassign(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = reassign_contract(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
        new_assignee=args["new_assignee"],
    )
    return _ok(contract)


def _handle_log(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = append_log_entry(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
        entry_type=args["type"],
        message=args["message"],
        metadata=args.get("metadata"),
    )
    return _ok(contract)


def _handle_heartbeat(args: dict) -> CallToolResult:
    root = _get_root(args)
    try:
        entry = registry_heartbeat(
            root=root,
            agent_id=args["agent_id"],
            current_status=args.get("current_status"),
        )
        return _ok(entry)
    except ValueError as e:
        return _error(str(e))


def _handle_verify(args: dict) -> CallToolResult:
    root = _get_root(args)
    contract = run_verification(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
    )
    results = contract.get("verification_results", [])
    commands = contract.get("delegation", {}).get("verification") or []
    latest = results[-len(commands) :] if commands else []
    return _ok(
        {
            "contract_id": contract["id"],
            "status": contract["status"],
            "latest_results": latest,
            "all_passed": all(r["passed"] for r in latest) if latest else False,
        }
    )


def run() -> None:
    """Run the ConPact MCP server (stdio transport)."""

    async def main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="conpact",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    anyio.run(main)
