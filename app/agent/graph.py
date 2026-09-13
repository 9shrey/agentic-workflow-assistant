"""LangGraph workflow graph assembly and execution orchestration.

The workflow is a compiled LangGraph :class:`~langgraph.graph.StateGraph`:

* Every agent step is registered as a node with ``add_node``.
* :func:`app.agent.router.router` supplies the conditional edges. It is a pure
  ``AgentState -> str`` function and already returns LangGraph's ``END``
  sentinel (``"__end__"``) verbatim, so it is wired in unchanged.
* The approval checkpoint pauses the graph with LangGraph's ``interrupt()``
  primitive rather than returning early from a hand-rolled loop.
* A ``SqliteSaver`` checkpointer persists graph state, so a run interrupted in
  one HTTP request can be resumed by a later one via ``Command(resume=...)``.

``AgentState`` is used directly as the graph's state schema, so every node
signature stays ``(AgentState, Session) -> dict`` and remains independently
unit-testable without constructing a graph.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy.orm import Session

from app.agent.state import AgentState
from app.agent.nodes import (
    planner_node,
    search_email_node,
    summarize_threads_node,
    extract_invoice_node,
    draft_email_node,
    propose_calendar_node,
    approval_checkpoint_node,
    execute_approved_actions_node,
    final_summary_node,
)
from app.agent.router import router
from app.config import settings
from app.models.workflow_run import WorkflowRun
from app.models.approval import Approval
from app.services.audit_service import AuditService

NODE_FUNCTIONS = {
    "planner_node": planner_node,
    "search_email_node": search_email_node,
    "summarize_threads_node": summarize_threads_node,
    "extract_invoice_node": extract_invoice_node,
    "draft_email_node": draft_email_node,
    "propose_calendar_node": propose_calendar_node,
    "approval_checkpoint_node": approval_checkpoint_node,
    "execute_approved_actions_node": execute_approved_actions_node,
    "final_summary_node": final_summary_node,
}

ORDERED_NODES = [
    "planner_node",
    "search_email_node",
    "summarize_threads_node",
    "extract_invoice_node",
    "draft_email_node",
    "propose_calendar_node",
    "approval_checkpoint_node",
    "execute_approved_actions_node",
    "final_summary_node",
]

APPROVAL_NODE = "approval_checkpoint_node"

# Every node routes through `router`, so each one needs the full target set.
_ROUTE_TARGETS = [n for n in ORDERED_NODES if n != "planner_node"] + [END]


# --------------------------------------------------------------------------
# Checkpointer
# --------------------------------------------------------------------------

def _checkpoint_path() -> str:
    """Derive the checkpoint DB path from the configured application database."""
    url = settings.database_url
    if url.startswith("sqlite"):
        _, _, raw_path = url.partition(":///")
        if raw_path and raw_path != ":memory:":
            path = Path(raw_path)
            return str(path.with_name(f"{path.stem}_checkpoints.db"))
    return "./workflow_checkpoints.db"


def _build_serializer() -> JsonPlusSerializer:
    """Serializer with an explicit allowlist of the types we checkpoint.

    LangGraph's default is permissive (any type, with a deprecation warning).
    Deserialising arbitrary types out of the checkpoint DB is a code-execution
    risk if that DB is ever writable by anything else, so the domain models are
    named explicitly instead. This also keeps the workflow working unchanged
    when LangGraph switches the default to strict.
    """
    from app.agent.planner import PlanStep, PlanStepType, WorkflowPlan
    from app.schemas.tool_schemas import (
        CalendarEventOutput,
        DraftEmailOutput,
        EmailThreadSummary,
        PendingInvoice,
        SummarizeThreadOutput,
    )

    return JsonPlusSerializer(
        allowed_msgpack_modules=(
            AgentState,
            PlanStep,
            PlanStepType,
            WorkflowPlan,
            CalendarEventOutput,
            DraftEmailOutput,
            EmailThreadSummary,
            PendingInvoice,
            SummarizeThreadOutput,
        )
    )


_checkpointer: Optional[SqliteSaver] = None


def get_checkpointer() -> SqliteSaver:
    """Return the process-wide LangGraph checkpointer, creating it on first use."""
    global _checkpointer
    if _checkpointer is None:
        conn = sqlite3.connect(_checkpoint_path(), check_same_thread=False)
        _checkpointer = SqliteSaver(conn, serde=_build_serializer())
        _checkpointer.setup()
    return _checkpointer


# --------------------------------------------------------------------------
# State helpers
# --------------------------------------------------------------------------

def _advance_index(state: AgentState) -> int:
    """Advance the plan pointer, clamped to the length of the plan."""
    if state.plan and state.current_step_index < len(state.plan.steps):
        return state.current_step_index + 1
    return state.current_step_index


def _coerce_state(values: Any) -> AgentState:
    """Normalise whatever the graph returned back into an AgentState."""
    if isinstance(values, AgentState):
        return values
    data = dict(values)
    data.pop("__interrupt__", None)
    return AgentState.model_validate(data)


def _load_persisted_state(workflow_id: str, db: Session) -> Optional[AgentState]:
    """Rehydrate the agent state from the WorkflowRun record."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()
    if run and run.agent_state:
        return AgentState.model_validate(run.agent_state)
    return None


def _persist_state(state: AgentState, db: Session) -> None:
    """Save the current agent state to the workflow run record."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == state.workflow_id).first()
    if run:
        run.status = state.status
        run.plan = state.plan.model_dump(mode="json") if state.plan else None
        run.agent_state = state.model_dump(mode="json")
        run.final_response = state.final_response or None
        run.updated_at = datetime.now(timezone.utc)
        db.commit()


def _create_approval_records(state: AgentState, db: Session) -> None:
    """Create Approval rows from pending_approvals, tagging each with its row id.

    Re-entrant by design: the approval node re-executes from the top when the
    graph resumes, so an existing row is reused rather than duplicated and the
    approval ids stay stable across the pause.
    """
    for approval_data in state.pending_approvals:
        existing = (
            db.query(Approval)
            .filter(
                Approval.workflow_id == state.workflow_id,
                Approval.approval_type == approval_data["approval_type"],
                Approval.proposed_action == approval_data["proposed_action"],
            )
            .first()
        )
        if existing:
            approval_data["approval_id"] = existing.id
            continue

        approval = Approval(
            id=str(uuid.uuid4()),
            workflow_id=state.workflow_id,
            approval_type=approval_data["approval_type"],
            proposed_action=approval_data["proposed_action"],
            proposed_payload=approval_data.get("proposed_payload"),
            status="pending",
        )
        db.add(approval)
        approval_data["approval_id"] = approval.id
    db.commit()


def apply_approval_decisions(
    approvals: list[dict],
    decisions: Union[bool, dict, None],
) -> list[dict]:
    """Stamp a decision onto each approval item.

    ``decisions`` may be a per-item mapping of ``approval_id -> status`` (the
    real path, used by the approval API) or a single bool applied to every item
    (kept for the auto-approve path and for callers that decided in bulk).

    Anything not explicitly approved is treated as **rejected**. An approval
    gate that defaults to "allow" on missing input is not an approval gate.
    """
    resolved = []
    for approval_data in approvals:
        item = dict(approval_data)
        if isinstance(decisions, bool):
            item["status"] = "approved" if decisions else "rejected"
        elif isinstance(decisions, dict):
            decided = decisions.get(item.get("approval_id"))
            item["status"] = decided if decided in ("approved", "rejected") else "rejected"
        else:
            item["status"] = "rejected"
        resolved.append(item)
    return resolved


# --------------------------------------------------------------------------
# Graph assembly
# --------------------------------------------------------------------------

def _build_graph(db: Session, stop_at_approval: bool = True):
    """Assemble and compile the workflow StateGraph.

    ``db`` and ``stop_at_approval`` are bound into the node closures rather than
    passed through ``config["configurable"]``, so no non-serialisable object
    ever reaches the checkpointer.
    """

    def _run_step(name: str, state: AgentState) -> dict:
        """Execute one node, record errors, advance the plan pointer, persist."""
        fn = NODE_FUNCTIONS[name]
        try:
            updates = dict(fn(state, db))
        except Exception as exc:  # a failed step must not kill the whole run
            state.add_error(name, str(exc))
            updates = {"errors": list(state.errors)}

        updates.setdefault("current_step_index", _advance_index(state))
        _persist_state(state.model_copy(update=updates), db)
        return updates

    def _planner(state: AgentState) -> dict:
        if state.plan:
            return {}
        updates = dict(planner_node(state, db))
        updates["current_step_index"] = 0
        _persist_state(state.model_copy(update=updates), db)
        return updates

    def _approval(state: AgentState) -> dict:
        """Human-in-the-loop checkpoint backed by LangGraph's interrupt()."""
        updates = dict(approval_checkpoint_node(state, db))
        approvals = [dict(a) for a in updates.get("pending_approvals", [])]

        # Persist the awaiting state and materialise Approval rows *before*
        # interrupting, so the API can list them while the graph is paused.
        paused = state.model_copy(update={**updates, "pending_approvals": approvals})
        _create_approval_records(paused, db)
        updates["pending_approvals"] = approvals
        _persist_state(state.model_copy(update=updates), db)

        if stop_at_approval:
            # Pauses the graph here. On resume this node re-executes from the
            # top and interrupt() returns the value passed to Command(resume=).
            decisions = interrupt(
                {
                    "workflow_id": state.workflow_id,
                    "pending_approvals": approvals,
                }
            )
        else:
            decisions = True  # auto-approve path, used by tests and the demo

        return {
            "pending_approvals": apply_approval_decisions(approvals, decisions),
            # Left as "awaiting_approval" so the router hands off to the
            # execute node now that every item carries a decision.
            "approval_status": "awaiting_approval",
            "status": "in_progress",
            "current_step_index": _advance_index(state),
        }

    builder = StateGraph(AgentState)
    builder.add_node("planner_node", _planner)
    builder.add_node(APPROVAL_NODE, _approval)
    for node_name in ORDERED_NODES:
        if node_name in ("planner_node", APPROVAL_NODE):
            continue
        builder.add_node(node_name, lambda s, _n=node_name: _run_step(_n, s))

    builder.add_edge(START, "planner_node")
    for node_name in ORDERED_NODES:
        builder.add_conditional_edges(node_name, router, _ROUTE_TARGETS)

    return builder.compile(checkpointer=get_checkpointer())


def build_workflow_graph(db: Session, stop_at_approval: bool = True):
    """Public accessor for the compiled graph (used by tests and tooling)."""
    return _build_graph(db, stop_at_approval=stop_at_approval)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

async def run_workflow(
    workflow_id: str,
    state: AgentState,
    db: Session,
    max_steps: int = 20,
    stop_at_approval: bool = True,
) -> AgentState:
    """Execute the workflow graph until it completes or hits an approval pause.

    Args:
        workflow_id: The ID of the workflow run; used as the LangGraph thread id.
        state: The initial agent state.
        db: Database session.
        max_steps: Upper bound on graph supersteps (LangGraph recursion limit).
        stop_at_approval: If True, pause at approval checkpoints via interrupt().

    Returns:
        The final agent state, or the awaiting-approval state if the graph paused.
    """
    graph = _build_graph(db, stop_at_approval=stop_at_approval)
    config = {
        "configurable": {"thread_id": workflow_id},
        "recursion_limit": max(25, max_steps * 2),
    }

    try:
        result = graph.invoke(state, config)
    except GraphRecursionError:
        # Mirror the previous behaviour: summarise whatever was reached.
        current = _load_persisted_state(workflow_id, db) or state
        current = current.model_copy(update=final_summary_node(current, db))
        _persist_state(current, db)
        return current

    if isinstance(result, dict) and result.get("__interrupt__"):
        # The node's updates are discarded when it interrupts, so read back the
        # awaiting-approval state that the node persisted before pausing.
        persisted = _load_persisted_state(workflow_id, db)
        if persisted is not None:
            return persisted

    return _coerce_state(result)


def resume_workflow_after_approval(
    workflow_id: str,
    state: AgentState,
    db: Session,
    approved: bool = True,
    decisions: Optional[dict] = None,
) -> AgentState:
    """Resume a graph paused at the approval checkpoint.

    Args:
        approved: Blanket decision, applied when ``decisions`` is not supplied.
        decisions: Per-item mapping of ``approval_id -> "approved"|"rejected"``.
            This is the path the approval API uses, so approving one item and
            rejecting another executes only the approved one.
    """
    resume_value: Union[bool, dict] = decisions if decisions is not None else approved

    graph = _build_graph(db, stop_at_approval=True)
    config = {"configurable": {"thread_id": workflow_id}}

    snapshot = graph.get_state(config)
    if snapshot.next:
        result = graph.invoke(Command(resume=resume_value), config)
        resumed = _coerce_state(result)
        _persist_state(resumed, db)
        return resumed

    # No live checkpoint (e.g. a state rehydrated in a fresh process): finish
    # the remaining steps directly so the caller still gets a completed run.
    return _resume_without_checkpoint(state, db, resume_value)


def _resume_without_checkpoint(
    state: AgentState,
    db: Session,
    decisions: Union[bool, dict],
) -> AgentState:
    """Fallback resume path used when no graph checkpoint exists."""
    resolved = apply_approval_decisions(state.pending_approvals, decisions)
    state = state.model_copy(
        update={
            "pending_approvals": resolved,
            "approval_status": "awaiting_approval",
            "status": "in_progress",
        }
    )
    state = state.model_copy(update=execute_approved_actions_node(state, db))
    state = state.model_copy(update=final_summary_node(state, db))
    _persist_state(state, db)
    return state


async def create_initial_state(user_request: str, db: Session) -> tuple[str, AgentState]:
    """Create a new workflow run and initial agent state."""
    workflow_id = str(uuid.uuid4())

    state = AgentState(
        workflow_id=workflow_id,
        user_request=user_request,
        status="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    run = WorkflowRun(
        id=workflow_id,
        user_request=user_request,
        status="pending",
        agent_state=state.model_dump(),
    )
    db.add(run)
    db.commit()

    return workflow_id, state
