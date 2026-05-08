"""Tests for mock tools."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.database import init_db, sync_engine
from app.schemas.tool_schemas import (
    CalendarEventInput,
    DraftEmailInput,
    EmailSearchInput,
    PendingInvoice,
    SummarizeThreadInput,
)
from app.tools.mock_tools import (
    mock_create_calendar_event,
    mock_draft_email,
    mock_read_contact_memory,
    mock_search_email,
    mock_summarize_thread,
    mock_write_contact_memory,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


@pytest.fixture
def db() -> Session:
    with Session(sync_engine) as session:
        yield session
        from app.models.contact_memory import ContactMemory
        session.query(ContactMemory).delete()
        session.commit()


class TestMockEmailSearch:
    def test_search_finds_invoice_threads(self, db: Session):
        result = mock_search_email(
            EmailSearchInput(query="invoice payment", max_results=10), db
        )
        assert result.total_found >= 4
        assert all(t.is_payment_related for t in result.threads)

    def test_search_returns_empty_for_unrelated_query(self, db: Session):
        result = mock_search_email(
            EmailSearchInput(query="lunch menu weather"), db
        )
        assert result.total_found == 0

    def test_search_respects_max_results(self, db: Session):
        result = mock_search_email(
            EmailSearchInput(query="invoice", max_results=2), db
        )
        assert len(result.threads) <= 2

    def test_search_thread_structure(self, db: Session):
        result = mock_search_email(
            EmailSearchInput(query="invoice"), db
        )
        for thread in result.threads:
            assert thread.thread_id
            assert thread.subject
            assert thread.sender
            assert thread.snippet


class TestMockSummarizeThread:
    def test_summarize_invoice_thread(self, db: Session):
        result = mock_summarize_thread(
            SummarizeThreadInput(
                thread_id="thread-inv-001",
                thread_content="Invoice #INV-2026-0042 overdue",
            ),
            db,
        )
        assert "Acme Corp" in result.summary
        assert result.invoice_details["vendor"] == "Acme Corp"
        assert result.invoice_details["amount"] == "$5,000"

    def test_summarize_unknown_thread(self, db: Session):
        result = mock_summarize_thread(
            SummarizeThreadInput(
                thread_id="nonexistent", thread_content="unknown content"
            ),
            db,
        )
        assert "Unable to generate" in result.summary
        assert result.suggested_action == "Manual review required"


class TestMockDraftEmail:
    def test_create_draft(self, db: Session):
        result = mock_draft_email(
            DraftEmailInput(
                to="billing@acme.example.com",
                subject="Reminder: Invoice #INV-2026-0042",
                body="Dear Acme Corp, this is a reminder regarding...",
            ),
            db,
        )
        assert result.draft_id.startswith("draft-")
        assert result.to == "billing@acme.example.com"

    def test_draft_preview_truncation(self, db: Session):
        long_body = "x" * 200
        result = mock_draft_email(
            DraftEmailInput(to="t@t.com", subject="S", body=long_body), db
        )
        assert len(result.body_preview) <= 103


class TestMockCalendarEvent:
    def test_create_event(self, db: Session):
        result = mock_create_calendar_event(
            CalendarEventInput(
                summary="Follow-up: Acme Corp Invoice",
                start_time="2026-05-10T10:00:00Z",
                end_time="2026-05-10T10:30:00Z",
                attendees=["billing@acme.example.com"],
            ),
            db,
        )
        assert result.event_id.startswith("event-")
        assert "Acme Corp" in result.summary

    def test_event_without_attendees(self, db: Session):
        result = mock_create_calendar_event(
            CalendarEventInput(
                summary="Test event",
                start_time="2026-05-10T10:00:00Z",
                end_time="2026-05-10T10:30:00Z",
            ),
            db,
        )
        assert result.attendees == []


class TestMockContactMemory:
    def test_write_and_read_memory(self, db: Session):
        mock_write_contact_memory(
            key="test:vendor",
            value="Test Vendor Inc",
            category="vendor",
            metadata_json={"email": "test@vendor.example.com"},
            db=db,
        )
        result = mock_read_contact_memory("test:vendor", db)
        assert result["key"] == "test:vendor"
        assert result["value"] == "Test Vendor Inc"
        assert result["category"] == "vendor"

    def test_update_existing_memory(self, db: Session):
        mock_write_contact_memory("test:update", "original", "vendor", None, db)
        mock_write_contact_memory("test:update", "updated", "vendor", {"note": "changed"}, db)
        result = mock_read_contact_memory("test:update", db)
        assert result["value"] == "updated"
        assert result["metadata_json"] == {"note": "changed"}

    def test_read_nonexistent(self, db: Session):
        result = mock_read_contact_memory("does_not_exist", db)
        assert result is None
