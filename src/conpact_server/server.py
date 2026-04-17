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
    get_project_path,
    is_initialized,
    validate_project_root,
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
        description="[delegator] When you want to delegate a task to another agent instead of implementing it yourself. 'objective' should be one sentence with concrete deliverables. 'do_items' lists what to do; 'do_not_items' what NOT to do. 'references' pairs each file path with a one-line purpose. 'acceptance_criteria' must be executable (e.g., 'test X passes'). The assignee will discover this contract via conpact_check or conpact_overview.",
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
        description="[implementer] Call at session start to discover contracts assigned to you. Returns contracts with status 'assigned' (new tasks), 'revision_needed' (rework requested), and 'in_progress' (crash recovery). Prefer conpact_overview for a full project picture.",
        inputSchema={
            "type": "object",
            "required": ["agent_id"],
            "properties": {
                "agent_id": {"type": "string", "description": "Your agent ID"}
            },
        },
    ),
    Tool(
        name="conpact_overview",
        description="[any] Call this first at session start or when you need a full project status. Returns all active contracts, registered agents, and personalized action suggestions for your role. This is the recommended entry point — most workflows start here.",
        inputSchema={
            "type": "object",
            "required": ["agent_id"],
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Your agent ID, used to generate personalized action suggestions",
                }
            },
        },
    ),
    Tool(
        name="conpact_claim",
        description="[implementer] After discovering an assigned contract (via conpact_check or conpact_overview), call this to start working. Transitions status from 'assigned' to 'in_progress'. You must be the assignee.",
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
        description="[implementer] While working on a claimed contract, call this to report progress or blockers. Setting 'next_check_in' tells the delegator when to expect an update and prevents premature reassignment.",
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
        description="[implementer] After finishing implementation and passing verification (conpact_verify), call this to submit your work for review. This is the last step before handing back to the delegator.",
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
        description="[delegator] When an implementer submits work (you'll see this in conpact_overview), review the changes and approve or request revisions. Only the original delegator (the 'from' field) can review.",
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
        description="[delegator] When a contract needs to be abandoned or cancelled (e.g., no longer relevant, blocked indefinitely). For normal completion, use conpact_review with status 'approved' instead.",
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
        description="[any] Call when you need full contract details (delegation spec, progress, result, review feedback). Usually called after conpact_overview identifies a contract you need to act on.",
        inputSchema={
            "type": "object",
            "required": ["contract_id"],
            "properties": {"contract_id": {"type": "string"}},
        },
    ),
    Tool(
        name="conpact_list",
        description="[any] Call when you need to find contracts by specific criteria (status, assignee, delegator). For a general status check, prefer conpact_overview.",
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
        description="[delegator] When an assigned or in-progress contract has been stale for 30+ minutes and next_check_in has expired. Transfers the contract to a different agent.",
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
        description="[any] While working on or reviewing a contract, record notable decisions, blockers, or discoveries to create a shared audit trail. For routine progress updates, use conpact_update_progress instead.",
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
        description="[any] Call periodically (e.g., every few minutes during active work) to indicate you are still online. Prevents the fault detector from marking your contracts as stale. Must be registered first.",
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
        description="[implementer] Before submitting (conpact_submit), run this to execute the verification commands defined in the contract's acceptance criteria. Also callable by the delegator to independently check results.",
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
        elif name == "conpact_overview":
            return _handle_overview(arguments)
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


def _require_initialized(root: Path) -> CallToolResult | None:
    """Returns an error result if project is not initialized, None otherwise."""
    try:
        validate_project_root(root)
    except ValueError as e:
        return _error(str(e))
    return None


def _handle_init(args: dict) -> CallToolResult:
    root = _get_root(args)
    agents_dir = get_agents_dir(root)
    project_path = get_project_path(root)

    if agents_dir.is_dir() and project_path.exists():
        return _ok("ConPact already initialized")

    agents_dir.mkdir(parents=True, exist_ok=True)
    (get_contracts_dir(root)).mkdir(parents=True, exist_ok=True)
    (get_archive_dir(root)).mkdir(parents=True, exist_ok=True)
    registry = get_registry_path(root)
    if not registry.exists():
        registry.write_text(
            json.dumps({"updated_at": _now_iso(), "agents": []}), encoding="utf-8"
        )
    project_path.write_text(
        json.dumps({
            "root": str(root.resolve()),
            "initialized_at": _now_iso(),
        }),
        encoding="utf-8",
    )
    return _ok("ConPact initialized")


def _handle_register(args: dict) -> CallToolResult:
    root = _get_root(args)
    err = _require_initialized(root)
    if err:
        return err
    entry = register_agent(
        root=root,
        agent_id=args["agent_id"],
        role=args.get("role"),
        capabilities=args.get("capabilities", []),
    )
    return _ok(entry)


def _handle_create(args: dict) -> CallToolResult:
    root = _get_root(args)
    err = _require_initialized(root)
    if err:
        return err
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
    err = _require_initialized(root)
    if err:
        return err
    agent_id = args["agent_id"]
    contracts = find_contracts_by_assignee(root, agent_id)
    liveness = get_agent_liveness(root, agent_id)
    return _ok({"contracts": contracts, "agent_liveness": liveness})


def _handle_overview(args: dict) -> CallToolResult:
    root = _get_root(args)
    err = _require_initialized(root)
    if err:
        return err
    agent_id = args["agent_id"]

    # Collect all active contracts
    contracts_dir = get_contracts_dir(root)
    all_contracts = []
    if contracts_dir.exists():
        for f in contracts_dir.glob("*.json"):
            if f.name == "project.json":
                continue
            try:
                c = json.loads(f.read_text(encoding="utf-8"))
                all_contracts.append({
                    "id": c.get("id", ""),
                    "status": c.get("status", ""),
                    "from": c.get("from", ""),
                    "assignee": c.get("assignee", ""),
                    "objective": c.get("delegation", {}).get("objective", ""),
                    "updated_at": c.get("updated_at", ""),
                })
            except (json.JSONDecodeError, KeyError):
                pass

    # Collect registered agents
    agents = list_agents(root)
    agent_summaries = []
    for a in agents:
        active = [c for c in all_contracts if c["assignee"] == a["id"] or c["from"] == a["id"]]
        agent_summaries.append({
            "id": a.get("id", ""),
            "role": a.get("role", ""),
            "status": a.get("status", "unknown"),
            "last_heartbeat": a.get("last_heartbeat"),
            "active_contracts": len(active),
        })

    # Generate personalized action suggestions
    actions = []
    blocking = []

    for c in all_contracts:
        if c["status"] == "assigned" and c["assignee"] == agent_id:
            actions.append(
                f"You have an assigned contract [{c['id']}]. "
                f"→ conpact_read('{c['id']}') then conpact_claim('{c['id']}', caller_id='{agent_id}')"
            )
        elif c["status"] == "revision_needed" and c["assignee"] == agent_id:
            actions.append(
                f"You have a contract needing revision [{c['id']}]. "
                f"→ conpact_read('{c['id']}') to see feedback, fix the issues, then conpact_submit('{c['id']}', ...)"
            )
        elif c["status"] == "submitted" and c["from"] == agent_id:
            actions.append(
                f"You have a contract awaiting review [{c['id']}, status: submitted]. "
                f"→ conpact_read('{c['id']}') then review and conpact_review('{c['id']}', ...)"
            )
            blocking.append({"agent": agent_id, "reason": f"contract {c['id']} needs review"})
        elif c["status"] == "in_progress" and c["from"] == agent_id:
            blocking.append({"agent": c["assignee"], "reason": f"contract {c['id']} is in progress"})

    if not actions:
        actions.append("No actions needed.")

    return _ok({
        "project_root": str(root.resolve()),
        "contracts": all_contracts,
        "agents": agent_summaries,
        "actions_for_you": actions,
        "blocking_on": blocking,
    })


def _handle_claim(args: dict) -> CallToolResult:
    root = _get_root(args)
    err = _require_initialized(root)
    if err:
        return err
    contract = claim_contract(
        root=root, caller_id=args["caller_id"], contract_id=args["contract_id"]
    )
    return _ok(contract)


def _handle_update_progress(args: dict) -> CallToolResult:
    root = _get_root(args)
    err = _require_initialized(root)
    if err:
        return err
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
    err = _require_initialized(root)
    if err:
        return err
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
    err = _require_initialized(root)
    if err:
        return err
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
    err = _require_initialized(root)
    if err:
        return err
    contract = close_contract(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
        reason=args["reason"],
    )
    return _ok(contract)


def _handle_read(args: dict) -> CallToolResult:
    root = _get_root(args)
    err = _require_initialized(root)
    if err:
        return err
    _, contract = find_contract_by_id(root, args["contract_id"])
    return _ok(contract)


def _handle_list(args: dict) -> CallToolResult:
    root = _get_root(args)
    err = _require_initialized(root)
    if err:
        return err
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
    err = _require_initialized(root)
    if err:
        return err
    contract = reassign_contract(
        root=root,
        caller_id=args["caller_id"],
        contract_id=args["contract_id"],
        new_assignee=args["new_assignee"],
    )
    return _ok(contract)


def _handle_log(args: dict) -> CallToolResult:
    root = _get_root(args)
    err = _require_initialized(root)
    if err:
        return err
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
    err = _require_initialized(root)
    if err:
        return err
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
    err = _require_initialized(root)
    if err:
        return err
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
