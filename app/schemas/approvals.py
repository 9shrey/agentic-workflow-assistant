"""Pydantic schemas for approval flow."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ApprovalCreate(BaseModel):
    workflow_id: str = Field(..., min_length=1)
    approval_type: str = Field(..., min_length=1, max_length=64)
    proposed_action: str = Field(..., min_length=1, max_length=128)
    proposed_payload: Optional[dict] = None


class ApprovalUpdate(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")


class ApprovalOut(BaseModel):
    id: str
    workflow_id: str
    approval_type: str
    proposed_action: str
    proposed_payload: Optional[dict] = None
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None
