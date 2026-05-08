"""Node implementations for the LangGraph workflow.

Each node is a pure function that takes AgentState and returns a partial update.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.agent.planner import PlanStepType, WorkflowPlan, create_plan
from app.agent.state import AgentState
from app.schemas.tool_schemas import (
    CalendarEventInput,
    DraftEmailInput,
    EmailSearchInput,
    PendingInvoice,
    SummarizeThreadInput,
)
from app.tools.tool_registry import (
    create_calendar_event,
    draft_email,
    read_contact_memory,
    search_email,
    summarize_thread,
)
from app.services.audit_service import AuditService


def planner_node(state: AgentState, db: Session) -> dict:
    """Generate a structured plan from the user request."""
    audit = AuditService(db)
    audit.log_call(
        workflow_id=state.workflow_id,
        tool_name="planner",
        input_payload={"user_request": state.user_request},
    )

    plan: WorkflowPlan = create_plan(state.user_request)
    state.plan = plan
    state.status = "planning_complete"

    audit.log_call(
        workflow_id=state.workflow_id,
        tool_name="planner",
        input_payload={"plan": plan.model_dump()},
    )

    return {
        "plan": plan,
        "status": "planning_complete",
        "current_step_index": 0,
    }


def search_email_node(state: AgentState, db: Session) -> dict:
    """Search email threads for invoice/payment-related messages."""
    audit = AuditService(db)
    plan_step = state.plan.steps[state.current_step_index] if state.plan else None
    config = plan_step.config if plan_step else {}

    input_data = EmailSearchInput(
        query=config.get("query", "invoice payment billing overdue"),
        max_results=config.get("max_results", 20),
    )

    audit_id, start_time = audit.log_call_start(
        workflow_id=state.workflow_id,
        tool_name="search_email",
        input_payload=input_data.model_dump(),
    )

    try:
        result = search_email(input_data, db)
        audit.log_call_complete(
            audit_id=audit_id,
            output_payload=result.model_dump(),
            started_at=start_time,
        )
        # Filter to payment-related only for invoice workflow
        payment_threads = [
            t for t in result.threads if t.is_payment_related
        ]
        return {
            "search_results": payment_threads,
            "completed_tool_calls": state.completed_tool_calls + ["search_email"],
        }
    except Exception as e:
        audit.log_call_complete(
            audit_id=audit_id,
            error_message=str(e),
            started_at=start_time,
        )
        state.add_error("search_email", str(e))
        return {"search_results": []}


def summarize_threads_node(state: AgentState, db: Session) -> dict:
    """Summarize each found email thread."""
    audit = AuditService(db)
    summaries = []

    for thread in state.search_results:
        audit_id, start_time = audit.log_call_start(
            workflow_id=state.workflow_id,
            tool_name="summarize_thread",
            input_payload={"thread_id": thread.thread_id},
        )
        try:
            input_data = SummarizeThreadInput(
                thread_id=thread.thread_id,
                thread_content=thread.snippet,
            )
            result = summarize_thread(input_data, db)
            audit.log_call_complete(
                audit_id=audit_id,
                output_payload=result.model_dump(),
                started_at=start_time,
            )
            summaries.append(result)
        except Exception as e:
            audit.log_call_complete(
                audit_id=audit_id,
                error_message=str(e),
                started_at=start_time,
            )
            state.add_error(f"summarize_{thread.thread_id}", str(e))

    return {
        "summaries": summaries,
        "completed_tool_calls": state.completed_tool_calls + ["summarize_threads"],
    }


def extract_invoice_node(state: AgentState, db: Session) -> dict:
    """Extract pending invoice details from summaries."""
    invoices = []
    for summary in state.summaries:
        details = summary.invoice_details
        if details and details.get("vendor"):
            invoices.append(
                PendingInvoice(
                    vendor=details.get("vendor", "Unknown"),
                    vendor_email=details.get("vendor_email", ""),
                    amount=details.get("amount"),
                    invoice_number=details.get("invoice_number"),
                    due_date=details.get("due_date"),
                    thread_id=summary.thread_id,
                    urgency="high" if details.get("days_overdue", 0) > 14 else "medium",
                    notes=summary.summary,
                )
            )
    return {
        "pending_invoices": invoices,
        "completed_tool_calls": state.completed_tool_calls + ["extract_invoices"],
    }


def draft_email_node(state: AgentState, db: Session) -> dict:
    """Generate reminder email drafts for each pending invoice."""
    audit = AuditService(db)
    drafts = []

    for invoice in state.pending_invoices:
        # Check contact memory for tone preferences
        memory_key = f"vendor:{invoice.vendor.lower().replace(' ', '_')}"
        memory = read_contact_memory(memory_key, db)

        tone = "professional and courteous"
        if memory and memory.get("metadata_json", {}).get("tone"):
            tone = memory["metadata_json"]["tone"]

        urgency_note = ""
        if invoice.urgency == "high":
            urgency_note = "This invoice is past due. "

        body = (
            f"Dear {invoice.vendor},\n\n"
            f""  # empty line
            f"Subject: {invoice.invoice_number or 'Outstanding Invoice'} - Payment Reminder\n\n"
            f"{urgency_note}We are writing to follow up on "
            f"{'invoice ' + invoice.invoice_number if invoice.invoice_number else 'the outstanding invoice'}"
            f"{' for ' + invoice.amount if invoice.amount else ''}.\n\n"
            f"Please confirm the status of this payment at your earliest convenience.\n\n"
            f"Thank you,\n"
            f"Billing Department"
        )

        input_data = DraftEmailInput(
            to=invoice.vendor_email,
            subject=f"Reminder: {invoice.invoice_number or 'Outstanding Invoice'}",
            body=body,
            thread_id=invoice.thread_id,
        )

        audit_id, start_time = audit.log_call_start(
            workflow_id=state.workflow_id,
            tool_name="draft_email",
            input_payload=input_data.model_dump(),
        )

        result = draft_email(input_data, db)
        audit.log_call_complete(
            audit_id=audit_id,
            output_payload=result.model_dump(),
            started_at=start_time,
        )

        drafts.append(result)

    return {
        "proposed_email_drafts": drafts,
        "completed_tool_calls": state.completed_tool_calls + ["draft_emails"],
    }


def propose_calendar_node(state: AgentState, db: Session) -> dict:
    """Propose calendar follow-up events for each pending invoice."""
    events = []

    for invoice in state.pending_invoices:
        if invoice.urgency == "high":
            # Schedule a 30-min follow-up for high-urgency invoices
            event_input = CalendarEventInput(
                summary=f"Follow-up: {invoice.vendor} - {invoice.invoice_number or 'Invoice'}",
                description=(
                    f"Follow up on {invoice.invoice_number or 'outstanding invoice'} "
                    f"{'for ' + invoice.amount if invoice.amount else ''}. "
                    f"{invoice.notes[:200]}"
                ),
                start_time="2026-05-08T10:00:00Z",
                end_time="2026-05-08T10:30:00Z",
                attendees=[invoice.vendor_email] if invoice.vendor_email else [],
            )
            result = create_calendar_event(event_input, db)
            events.append(result)

    return {
        "proposed_calendar_events": events,
        "completed_tool_calls": state.completed_tool_calls + ["propose_calendar"],
    }


def approval_checkpoint_node(state: AgentState, db: Session) -> dict:
    """Create approval records and pause for human approval."""
    approvals = []

    for draft in state.proposed_email_drafts:
        approvals.append({
            "workflow_id": state.workflow_id,
            "approval_type": "gmail_draft",
            "proposed_action": f"Create Gmail draft to {draft.to}",
            "proposed_payload": draft.model_dump(mode="json"),
        })

    for event in state.proposed_calendar_events:
        approvals.append({
            "workflow_id": state.workflow_id,
            "approval_type": "calendar_event",
            "proposed_action": f"Create calendar event: {event.summary}",
            "proposed_payload": event.model_dump(mode="json"),
        })

    return {
        "pending_approvals": approvals,
        "approval_status": "awaiting_approval",
        "status": "awaiting_approval",
    }


def execute_approved_actions_node(state: AgentState, db: Session) -> dict:
    """Execute actions that have been approved.

    This is a special node that processes approved items. In a real system,
    this would be called after the human approves, but for the mock MVP,
    it simply marks approved actions ready.
    """
    audit = AuditService(db)

    approved_ids = set()
    for approval_data in state.pending_approvals:
        if approval_data.get("status") == "approved":
            approved_ids.add(approval_data.get("approval_type"))

    if "gmail_draft" in approved_ids:
        for draft in state.proposed_email_drafts:
            audit.log_call(
                workflow_id=state.workflow_id,
                tool_name="execute_gmail_draft",
                input_payload=draft.model_dump(),
                output_payload={"status": "draft_created", "draft_id": draft.draft_id},
            )
            state.approved_drafts.append(draft)

    if "calendar_event" in approved_ids:
        for event in state.proposed_calendar_events:
            audit.log_call(
                workflow_id=state.workflow_id,
                tool_name="execute_calendar_event",
                input_payload=event.model_dump(),
                output_payload={"status": "event_created", "event_id": event.event_id},
            )
            state.approved_events.append(event)

    return {
        "completed_tool_calls": state.completed_tool_calls + ["execute_approved"],
        "approval_status": "approved_actions_executed",
    }


def final_summary_node(state: AgentState, db: Session) -> dict:
    """Generate a final summary of actions taken."""
    audit = AuditService(db)

    total_invoices = len(state.pending_invoices)
    total_drafts = len(state.proposed_email_drafts)
    total_events = len(state.proposed_calendar_events)
    total_errors = len(state.errors)
    total_approved = len(state.approved_drafts) + len(state.approved_events)

    summary_parts = [
        f"Workflow Complete: {state.workflow_id}",
        f"",
        f"Summary:",
        f"- {total_invoices} pending invoices found",
        f"- {total_drafts} reminder email drafts generated",
        f"- {total_events} calendar follow-ups proposed",
        f"- {total_errors} errors encountered",
        f"",
    ]

    if state.pending_approvals:
        pending_count = sum(
            1 for a in state.pending_approvals if a.get("status") == "pending"
        )
        summary_parts.append(f"Approvals: {pending_count} action(s) awaiting human approval")
    else:
        summary_parts.append("All proposed actions have been processed.")

    if total_approved > 0:
        summary_parts.append(f"{total_approved} approved actions were executed.")

    if state.pending_invoices:
        summary_parts.append("")
        summary_parts.append("Pending Invoices:")
        for inv in state.pending_invoices:
            summary_parts.append(
                f"  - {inv.vendor}: {inv.invoice_number or 'N/A'} "
                f"({inv.amount or 'Unknown amount'}) [{inv.urgency} urgency]"
            )

    final_response = "\n".join(summary_parts)

    audit.log_call(
        workflow_id=state.workflow_id,
        tool_name="final_summary",
        output_payload={"summary": final_response},
    )

    return {
        "final_response": final_response,
        "status": "completed",
    }
