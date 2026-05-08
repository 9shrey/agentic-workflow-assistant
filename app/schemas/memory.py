"""Pydantic schemas for contact memory."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1)
    category: str = Field(default="general", max_length=64)
    metadata_json: Optional[dict] = None


class MemoryUpdate(BaseModel):
    value: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=64)
    metadata_json: Optional[dict] = None


class MemoryOut(BaseModel):
    id: str
    key: str
    value: Optional[str] = None
    category: str
    metadata_json: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class AuditLogOut(BaseModel):
    id: str
    workflow_id: str
    tool_name: str
    input_payload: Optional[dict] = None
    output_payload: Optional[dict] = None
    status: str
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
