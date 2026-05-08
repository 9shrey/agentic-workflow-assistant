"""Run a complete demo of the Agentic Workflow Automation Assistant.

This script demonstrates the full mock workflow end-to-end:
1. Start a workflow from user request
2. Show the generated plan
3. Display found invoice threads
4. Show proposed email drafts and calendar events
5. Demonstrate the approval checkpoint
6. Simulate human approval
7. Resume and show final summary
8. Display audit logs
"""

import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, sync_engine
from app.models.workflow_run import WorkflowRun
from app.models.approval import Approval
from app.models.audit_log import AuditLog
from app.models.contact_memory import ContactMemory
from app.agent.state import AgentState
from app.agent.graph import (
    create_initial_state,
    run_workflow,
    resume_workflow_after_approval,
)
from app.services.audit_service import AuditService
from app.services.approval_service import ApprovalService
from sqlalchemy.orm import Session

SEPARATOR = "=" * 70


def print_header(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def p(msg: str = ""):
    """Print safely handling Windows console encoding issues."""
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            print(msg.encode("utf-8", errors="replace").decode("utf-8"))
        except Exception:
            print(str(msg.encode("ascii", errors="replace")))


def main():
    print_header("AGENTIC WORKFLOW AUTOMATION ASSISTANT - DEMO")
    p("Status: Mock Mode (GOOGLE_API_ENABLED=false)")
    p()

    # Initialize database
    init_db()
    db = Session(sync_engine)

    try:
        # Step 1: Define the user request
        user_request = (
            "Find all pending invoices, draft reminder emails, and schedule follow-ups."
        )
        p(f"[USER REQUEST] {user_request}")

        # Step 2: Create workflow
        workflow_id, state = asyncio.run(create_initial_state(user_request, db))
        p(f"\n[WORKFLOW CREATED] ID: {workflow_id}")

        # Step 3: Run workflow (will stop at approval checkpoint)
        p("\n[EXECUTING WORKFLOW...]")
        state = asyncio.run(
            run_workflow(workflow_id, state, db, stop_at_approval=True)
        )

        # Step 4: Show generated plan
        print_header("GENERATED PLAN")
        if state.plan:
            for i, step in enumerate(state.plan.steps):
                flag = " [REQUIRES APPROVAL]" if step.requires_approval else ""
                p(f"  {i+1}. {step.step.value}{flag}")
                p(f"     -> {step.description}")

        # Step 5: Show found invoice threads
        print_header(f"FOUND INVOICE THREADS ({len(state.search_results)})")
        for thread in state.search_results:
            p(f"  [{thread.thread_id}] {thread.subject[:60]}")
            p(f"      From: {thread.sender}")
            p(f"      Snippet: {thread.snippet[:80]}...")
            p()

        # Step 6: Show pending invoices
        print_header(f"PENDING INVOICES ({len(state.pending_invoices)})")
        for invoice in state.pending_invoices:
            urgency_label = f"[{invoice.urgency.upper()}]"
            p(f"  {urgency_label} {invoice.vendor}")
            p(f"      Invoice: {invoice.invoice_number or 'N/A'}")
            p(f"      Amount: {invoice.amount or 'Unknown'}")
            p(f"      Due: {invoice.due_date or 'Unknown'}")
            p(f"      Email: {invoice.vendor_email}")
            p()

        # Step 7: Show proposed email drafts
        print_header(f"PROPOSED EMAIL DRAFTS ({len(state.proposed_email_drafts)})")
        for draft in state.proposed_email_drafts:
            p(f"  Draft ID: {draft.draft_id}")
            p(f"  To: {draft.to}")
            p(f"  Subject: {draft.subject}")
            p(f"  Preview: {draft.body_preview}")
            p()

        # Step 8: Show proposed calendar events
        print_header(f"PROPOSED CALENDAR EVENTS ({len(state.proposed_calendar_events)})")
        for event in state.proposed_calendar_events:
            p(f"  Event ID: {event.event_id}")
            p(f"  Summary: {event.summary}")
            p(f"  Time: {event.start_time} - {event.end_time}")
            p(f"  Attendees: {', '.join(event.attendees) if event.attendees else 'None'}")
            p()

        # Step 9: Show pending approvals
        print_header("PENDING APPROVALS")
        approvals_db = (
            db.query(Approval)
            .filter(Approval.workflow_id == workflow_id)
            .all()
        )
        for approval in approvals_db:
            p(f"  [{approval.id}] {approval.approval_type}")
            p(f"      Action: {approval.proposed_action}")
            p(f"      Status: {approval.status}")

        # Step 10: Simulate human approval
        print_header("SIMULATING HUMAN APPROVAL")
        approval_svc = ApprovalService(db)
        count = approval_svc.approve_all_for_workflow(workflow_id)
        p(f"  Approved {count} action(s)")

        # Step 11: Resume workflow after approval
        p("\n[RESUMING WORKFLOW AFTER APPROVAL...]")
        state = resume_workflow_after_approval(workflow_id, state, db, approved=True)

        # Step 12: Show final summary
        print_header("FINAL SUMMARY")
        p(state.final_response)
        p()

        # Step 13: Show audit logs
        print_header("AUDIT LOGS")
        audit_svc = AuditService(db)
        logs = audit_svc.get_logs_for_workflow(workflow_id)
        p(f"  Total tool calls logged: {len(logs)}\n")
        for log_entry in logs:
            status_icon = "[OK]" if log_entry.status == "success" else "[FAIL]"
            p(f"  {status_icon} {log_entry.tool_name}")
            if log_entry.duration_ms:
                p(f"       Duration: {log_entry.duration_ms:.1f}ms")
            if log_entry.error_message:
                p(f"       Error: {log_entry.error_message}")
            if log_entry.output_payload and "draft_id" in str(log_entry.output_payload):
                p(f"       Output: {str(log_entry.output_payload)[:80]}")
        p()

        # Step 14: Clean summary
        print_header("DEMO COMPLETE")
        p("  Summary:")
        p(f"  - Workflow ID: {workflow_id}")
        p(f"  - Status: {state.status}")
        p(f"  - Invoices found: {len(state.pending_invoices)}")
        p(f"  - Drafts proposed: {len(state.proposed_email_drafts)}")
        p(f"  - Events proposed: {len(state.proposed_calendar_events)}")
        p(f"  - Actions approved: {len(state.approved_drafts) + len(state.approved_events)}")
        p(f"  - Approval required: YES (enforced)")
        p(f"  - Audit log entries: {len(logs)}")
        p(f"  - Errors: {len(state.errors)}")
        p()

    finally:
        db.close()


if __name__ == "__main__":
    main()
