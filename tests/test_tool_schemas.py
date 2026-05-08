"""Tests for Pydantic tool schemas - valid and invalid inputs."""

import pytest
from pydantic import ValidationError

from app.schemas.tool_schemas import (
    CalendarEventInput,
    DraftEmailInput,
    EmailSearchInput,
    PendingInvoice,
)
from app.schemas.requests import WorkflowStartRequest
from app.schemas.memory import MemoryCreate, MemoryUpdate


class TestEmailSearchInput:
    def test_valid_input(self):
        inp = EmailSearchInput(query="invoice pending payment", max_results=10)
        assert inp.query == "invoice pending payment"
        assert inp.max_results == 10
        assert inp.days_back == 30

    def test_defaults(self):
        inp = EmailSearchInput(query="invoice")
        assert inp.max_results == 20
        assert inp.days_back == 30

    def test_empty_query_fails(self):
        with pytest.raises(ValidationError):
            EmailSearchInput(query="   ")

    def test_too_many_results_fails(self):
        with pytest.raises(ValidationError):
            EmailSearchInput(query="invoice", max_results=101)

    def test_days_back_too_large_fails(self):
        with pytest.raises(ValidationError):
            EmailSearchInput(query="invoice", days_back=400)


class TestDraftEmailInput:
    def test_valid_input(self):
        inp = DraftEmailInput(to="test@example.com", subject="Reminder", body="Please pay invoice")
        assert inp.to == "test@example.com"

    def test_missing_subject_fails(self):
        with pytest.raises(ValidationError):
            DraftEmailInput(to="test@example.com", body="Please pay invoice")

    def test_empty_body_fails(self):
        with pytest.raises(ValidationError):
            DraftEmailInput(to="test@example.com", subject="Reminder", body="")


class TestCalendarEventInput:
    def test_valid_input(self):
        inp = CalendarEventInput(
            summary="Follow-up: Invoice #123",
            start_time="2026-05-10T10:00:00Z",
            end_time="2026-05-10T10:30:00Z",
            attendees=["billing@acme.example.com"],
        )
        assert inp.summary == "Follow-up: Invoice #123"
        assert len(inp.attendees) == 1

    def test_missing_times_fails(self):
        with pytest.raises(ValidationError):
            CalendarEventInput(summary="test", start_time="2026-05-10T10:00:00Z")


class TestPendingInvoice:
    def test_valid_minimal(self):
        inv = PendingInvoice(
            vendor="Acme Corp",
            vendor_email="billing@acme.example.com",
            thread_id="thread-1",
        )
        assert inv.urgency == "medium"

    def test_valid_full(self):
        inv = PendingInvoice(
            vendor="Globex",
            vendor_email="ap@globex.example.com",
            amount="$5,000",
            invoice_number="INV-2026-0042",
            due_date="2026-05-15",
            thread_id="thread-2",
            urgency="high",
            notes="Overdue by 14 days",
        )
        assert inv.amount == "$5,000"
        assert inv.urgency == "high"


class TestWorkflowStartRequest:
    def test_valid(self):
        req = WorkflowStartRequest(
            user_request="Find all pending invoices, draft reminder emails, and schedule follow-ups."
        )
        assert req.user_request

    def test_empty_request_fails(self):
        with pytest.raises(ValidationError):
            WorkflowStartRequest(user_request="")

    def test_too_long_request_fails(self):
        with pytest.raises(ValidationError):
            WorkflowStartRequest(user_request="x" * 2001)


class TestMemorySchemas:
    def test_memory_create_valid(self):
        m = MemoryCreate(key="test_key", value="test_value", category="vendor")
        assert m.key == "test_key"
        assert m.value == "test_value"
        assert m.category == "vendor"

    def test_memory_create_missing_value_fails(self):
        with pytest.raises(ValidationError):
            MemoryCreate(key="test_key")

    def test_memory_update_partial(self):
        m = MemoryUpdate(value="new_value")
        assert m.value == "new_value"
        assert m.category is None
