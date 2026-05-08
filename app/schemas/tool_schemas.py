"""Pydantic schemas for tool inputs and outputs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class EmailSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(default=20, ge=1, le=100)
    days_back: int = Field(default=30, ge=1, le=365)

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query must not be empty")
        return v.strip()


class EmailThreadSummary(BaseModel):
    thread_id: str
    subject: str
    sender: str
    snippet: str
    extracted_details: dict = Field(default_factory=dict)
    is_payment_related: bool = False
    date: Optional[datetime] = None


class EmailSearchOutput(BaseModel):
    threads: list[EmailThreadSummary] = Field(default_factory=list)
    total_found: int = 0


class SummarizeThreadInput(BaseModel):
    thread_id: str
    thread_content: str = Field(..., min_length=1)


class SummarizeThreadOutput(BaseModel):
    thread_id: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    invoice_details: dict = Field(default_factory=dict)
    suggested_action: str = ""


class DraftEmailInput(BaseModel):
    to: str = Field(..., min_length=3)
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    thread_id: Optional[str] = None


class DraftEmailOutput(BaseModel):
    draft_id: str
    to: str
    subject: str
    body_preview: str
    created_at: str


class CalendarEventInput(BaseModel):
    summary: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    start_time: str = Field(..., description="ISO 8601 datetime string")
    end_time: str = Field(..., description="ISO 8601 datetime string")
    attendees: list[str] = Field(default_factory=list)
    timezone: str = "UTC"


class CalendarEventOutput(BaseModel):
    event_id: str
    summary: str
    start_time: str
    end_time: str
    attendees: list[str] = Field(default_factory=list)


class PendingInvoice(BaseModel):
    vendor: str
    vendor_email: str
    amount: Optional[str] = None
    invoice_number: Optional[str] = None
    due_date: Optional[str] = None
    thread_id: str
    urgency: str = "medium"
    notes: str = ""
