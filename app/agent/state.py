"""Typed agent state for the LangGraph workflow."""

from typing import Annotated, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.agent.planner import PlanStep, WorkflowPlan
from app.schemas.tool_schemas import (
    CalendarEventOutput,
    DraftEmailOutput,
    EmailThreadSummary,
    PendingInvoice,
    SummarizeThreadOutput,
)
from app.schemas.approvals import ApprovalOut


class AgentState(BaseModel):
    """Complete agent state that flows through the LangGraph."""

    workflow_id: str = ""
    user_request: str = ""
    status: str = "pending"

    # Planning
    plan: Optional[WorkflowPlan] = None
    current_step_index: int = 0

    # Tool outputs
    search_results: list[EmailThreadSummary] = Field(default_factory=list)
    summaries: list[SummarizeThreadOutput] = Field(default_factory=list)
    pending_invoices: list[PendingInvoice] = Field(default_factory=list)
    proposed_email_drafts: list[DraftEmailOutput] = Field(default_factory=list)
    proposed_calendar_events: list[CalendarEventOutput] = Field(default_factory=list)

    # Approval
    approval_status: str = "not_required"
    pending_approvals: list[dict] = Field(default_factory=list)
    approved_drafts: list[DraftEmailOutput] = Field(default_factory=list)
    approved_events: list[CalendarEventOutput] = Field(default_factory=list)

    # Results
    completed_tool_calls: list[str] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    final_response: str = ""

    # Metadata
    created_at: str = ""
    updated_at: str = ""

    def add_error(self, step_name: str, error_msg: str) -> None:
        self.errors.append({
            "step": step_name,
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
