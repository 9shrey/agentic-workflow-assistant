"""Request schemas for FastAPI endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WorkflowStartRequest(BaseModel):
    user_request: str = Field(
        ..., min_length=1, max_length=2000, description="The user's natural language request"
    )


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    user_request: str
    status: str
    plan: Optional[dict] = None
    final_response: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")


class ApprovalResponse(BaseModel):
    id: str
    workflow_id: str
    approval_type: str
    proposed_action: str
    proposed_payload: Optional[dict] = None
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None
