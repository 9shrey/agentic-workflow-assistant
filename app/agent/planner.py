"""Deterministic planner that converts user requests into structured multi-step plans.

No LLM required. Uses keyword matching for deterministic step generation.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PlanStepType(str, Enum):
    SEARCH_EMAIL_THREADS = "search_email_threads"
    SUMMARIZE_THREADS = "summarize_threads"
    EXTRACT_PENDING_INVOICES = "extract_pending_invoices"
    DRAFT_REMINDER_EMAILS = "draft_reminder_emails"
    PROPOSE_CALENDAR_FOLLOWUPS = "propose_calendar_followups"
    REQUEST_APPROVAL = "request_approval"
    CREATE_GMAIL_DRAFTS = "create_gmail_drafts"
    CREATE_CALENDAR_FOLLOWUPS = "create_calendar_followups"
    FINAL_SUMMARY = "final_summary"


class PlanStep(BaseModel):
    step: PlanStepType
    description: str
    tool_name: Optional[str] = None
    requires_approval: bool = False
    config: dict = Field(default_factory=dict)


class WorkflowPlan(BaseModel):
    user_request: str
    steps: list[PlanStep]
    estimated_total_steps: int


INVOICE_REQUEST_KEYWORDS = [
    "invoice", "payment", "overdue", "past due", "reminder",
    "follow-up", "followup", "draft", "billing", "vendor",
]

CALENDAR_KEYWORDS = [
    "schedule", "calendar", "follow-up", "followup", "meeting",
]

DRAFT_KEYWORDS = [
    "draft", "email", "reminder", "compose", "write",
]


def _contains_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def create_plan(user_request: str) -> WorkflowPlan:
    """Generate a deterministic plan based on keyword analysis of the user request.

    This is designed to work without any LLM API calls, making it ideal for
    testing and deterministic behavior in production.
    """
    steps: list[PlanStep] = []
    has_invoice = _contains_keywords(user_request, INVOICE_REQUEST_KEYWORDS)
    has_calendar = _contains_keywords(user_request, CALENDAR_KEYWORDS)
    has_draft = _contains_keywords(user_request, DRAFT_KEYWORDS)

    if not has_invoice and not has_calendar and not has_draft:
        return WorkflowPlan(
            user_request=user_request,
            steps=[
                PlanStep(
                    step=PlanStepType.SEARCH_EMAIL_THREADS,
                    description="Search email threads for relevant messages",
                    tool_name="search_email",
                ),
                PlanStep(
                    step=PlanStepType.FINAL_SUMMARY,
                    description="Generate final summary of findings",
                    config={},
                ),
            ],
            estimated_total_steps=2,
        )

    # Step 1: Search for relevant email threads
    search_query = "invoice OR payment OR billing OR overdue"
    steps.append(
        PlanStep(
            step=PlanStepType.SEARCH_EMAIL_THREADS,
            description="Search email threads for pending invoice/payment-related emails",
            tool_name="search_email",
            config={"query": search_query, "max_results": 20},
        )
    )

    # Step 2: Summarize found threads
    steps.append(
        PlanStep(
            step=PlanStepType.SUMMARIZE_THREADS,
            description="Summarize each relevant email thread to extract context",
            tool_name="summarize_thread",
        )
    )

    # Step 3: Extract pending invoices
    steps.append(
        PlanStep(
            step=PlanStepType.EXTRACT_PENDING_INVOICES,
            description="Extract invoice details from summarized threads",
        )
    )

    # Step 4: Draft reminder emails
    steps.append(
        PlanStep(
            step=PlanStepType.DRAFT_REMINDER_EMAILS,
            description="Generate reminder email drafts for each pending invoice",
            tool_name="draft_email",
        )
    )

    # Step 5: Propose calendar follow-ups
    if has_calendar:
        steps.append(
            PlanStep(
                step=PlanStepType.PROPOSE_CALENDAR_FOLLOWUPS,
                description="Propose calendar follow-up events for pending invoices",
                tool_name="create_calendar_event",
            )
        )

    # Step 6: Request human approval
    steps.append(
        PlanStep(
            step=PlanStepType.REQUEST_APPROVAL,
            description="Request human approval for draft emails and calendar events",
            requires_approval=True,
        )
    )

    # Step 7: Execute approved actions (depends on approval)
    steps.append(
        PlanStep(
            step=PlanStepType.CREATE_GMAIL_DRAFTS,
            description="Create Gmail drafts for approved reminder emails",
            tool_name="draft_email",
            requires_approval=True,
        )
    )

    if has_calendar:
        steps.append(
            PlanStep(
                step=PlanStepType.CREATE_CALENDAR_FOLLOWUPS,
                description="Create calendar events for approved follow-ups",
                tool_name="create_calendar_event",
                requires_approval=True,
            )
        )

    # Final step: Summary
    steps.append(
        PlanStep(
            step=PlanStepType.FINAL_SUMMARY,
            description="Generate final summary of actions taken and pending approvals",
        )
    )

    return WorkflowPlan(
        user_request=user_request,
        steps=steps,
        estimated_total_steps=len(steps),
    )
