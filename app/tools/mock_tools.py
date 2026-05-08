"""Mock tool implementations for offline development and testing.

All mock tools return realistic demo data. Each tool accepts a session for audit logging.
Switches to real implementations when GOOGLE_API_ENABLED=true.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.contact_memory import ContactMemory
from app.schemas.tool_schemas import (
    CalendarEventInput,
    CalendarEventOutput,
    DraftEmailInput,
    DraftEmailOutput,
    EmailSearchInput,
    EmailSearchOutput,
    EmailThreadSummary,
    PendingInvoice,
    SummarizeThreadInput,
    SummarizeThreadOutput,
)
from app.services.audit_service import AuditService

DEMO_THREADS = [
    {
        "thread_id": "thread-inv-001",
        "subject": "Invoice #INV-2026-0042 - Payment Overdue",
        "sender": "billing@acme.example.com",
        "snippet": "This is a reminder that invoice #INV-2026-0042 for $5,000 is now 14 days past due. Please remit payment at your earliest convenience.",
        "is_payment_related": True,
        "date": "2026-05-01T10:00:00Z",
    },
    {
        "thread_id": "thread-inv-002",
        "subject": "RE: Payment reminder - Globex Inc invoice #GL-2026-018",
        "sender": "ap@globex.example.com",
        "snippet": "Following up on invoice #GL-2026-018 for $12,500. Our records show this is 7 days overdue. Can you provide an update on payment status?",
        "is_payment_related": True,
        "date": "2026-05-03T14:30:00Z",
    },
    {
        "thread_id": "thread-inv-003",
        "subject": "Third Notice: Past Due Invoice #INIT-889 - Initech",
        "sender": "billing@initech.example.com",
        "snippet": "This is our third notice regarding invoice #INIT-889 for $3,200. The invoice is now 21 days overdue. Please contact us immediately to resolve this.",
        "is_payment_related": True,
        "date": "2026-04-25T09:15:00Z",
    },
    {
        "thread_id": "thread-mkt-001",
        "subject": "Weekly Marketing Newsletter - Tips & Tricks",
        "sender": "newsletter@marketing.example.com",
        "snippet": "Check out our latest blog post about optimizing your workflow.",
        "is_payment_related": False,
        "date": "2026-05-05T08:00:00Z",
    },
    {
        "thread_id": "thread-inv-004",
        "subject": "Consulting fees for Q1 2026 - Invoice #CN-2026-099",
        "sender": "billing@consultcorp.example.com",
        "snippet": "Attached is our invoice #CN-2026-099 for Q1 consulting services totaling $8,750. Payment is due within 30 days (net30). Please confirm receipt.",
        "is_payment_related": True,
        "date": "2026-05-02T11:00:00Z",
    },
    {
        "thread_id": "thread-inv-005",
        "subject": "Vendor invoice #V-2026-127 from DataFlow Systems",
        "sender": "accounts@dataflow.example.com",
        "snippet": "Invoice #V-2026-127 for database maintenance services - $2,100. Due date: May 20, 2026. Please process at your earliest convenience.",
        "is_payment_related": True,
        "date": "2026-04-28T16:45:00Z",
    },
]


def mock_search_email(input_data: EmailSearchInput, db: Session) -> EmailSearchOutput:
    """Mock Gmail search: returns demo invoice threads matching the query."""
    query_lower = input_data.query.lower()
    results = []

    for t in DEMO_THREADS:
        combined = f"{t['subject']} {t['snippet']} {t['sender']}".lower()
        if any(word in combined for word in query_lower.split()):
            results.append(
                EmailThreadSummary(
                    thread_id=t["thread_id"],
                    subject=t["subject"],
                    sender=t["sender"],
                    snippet=t["snippet"],
                    is_payment_related=t["is_payment_related"],
                    date=t["date"],
                )
            )

        if len(results) >= input_data.max_results:
            break

    return EmailSearchOutput(threads=results, total_found=len(results))


def mock_summarize_thread(input_data: SummarizeThreadInput, db: Session) -> SummarizeThreadOutput:
    """Mock thread summarizer: returns structured invoice summaries for demo threads."""
    thread_map = {
        "thread-inv-001": {
            "summary": "Acme Corp invoice #INV-2026-0042 for $5,000 is 14 days overdue. This is a first reminder requesting payment.",
            "key_points": ["Amount: $5,000", "14 days overdue", "First reminder sent"],
            "invoice_details": {
                "vendor": "Acme Corp",
                "vendor_email": "billing@acme.example.com",
                "amount": "$5,000",
                "invoice_number": "INV-2026-0042",
                "due_date": "2026-04-16",
                "days_overdue": 14,
            },
            "suggested_action": "Draft polite reminder email and schedule follow-up",
        },
        "thread-inv-002": {
            "summary": "Globex Inc invoice #GL-2026-018 for $12,500 is 7 days overdue. The vendor is requesting a payment status update.",
            "key_points": ["Amount: $12,500", "7 days overdue", "Vendor awaiting payment status"],
            "invoice_details": {
                "vendor": "Globex Inc",
                "vendor_email": "ap@globex.example.com",
                "amount": "$12,500",
                "invoice_number": "GL-2026-018",
                "due_date": "2026-04-26",
                "days_overdue": 7,
            },
            "suggested_action": "Draft status update email and schedule follow-up call",
        },
        "thread-inv-003": {
            "summary": "Initech invoice #INIT-889 for $3,200 is 21 days overdue. Third notice received - urgent action required.",
            "key_points": ["Amount: $3,200", "21 days overdue", "Third notice - URGENT"],
            "invoice_details": {
                "vendor": "Initech",
                "vendor_email": "billing@initech.example.com",
                "amount": "$3,200",
                "invoice_number": "INIT-889",
                "due_date": "2026-04-14",
                "days_overdue": 21,
            },
            "suggested_action": "Immediate action needed: draft urgent response and call vendor",
        },
        "thread-inv-004": {
            "summary": "ConsultCorp invoice #CN-2026-099 for $8,750 in Q1 consulting fees. Not yet due (net30), payment confirmation requested.",
            "key_points": ["Amount: $8,750", "Net30 terms", "Payment confirmation requested"],
            "invoice_details": {
                "vendor": "ConsultCorp",
                "vendor_email": "billing@consultcorp.example.com",
                "amount": "$8,750",
                "invoice_number": "CN-2026-099",
                "due_date": "2026-06-01",
                "days_overdue": 0,
            },
            "suggested_action": "Acknowledge receipt, confirm payment will be processed by due date",
        },
        "thread-inv-005": {
            "summary": "DataFlow Systems invoice #V-2026-127 for $2,100 in database maintenance. Due May 20, 2026. Not yet overdue.",
            "key_points": ["Amount: $2,100", "Due: May 20, 2026", "Database maintenance services"],
            "invoice_details": {
                "vendor": "DataFlow Systems",
                "vendor_email": "accounts@dataflow.example.com",
                "amount": "$2,100",
                "invoice_number": "V-2026-127",
                "due_date": "2026-05-20",
                "days_overdue": 0,
            },
            "suggested_action": "Acknowledge and schedule payment before due date",
        },
    }

    result = thread_map.get(input_data.thread_id)
    if not result:
        return SummarizeThreadOutput(
            thread_id=input_data.thread_id,
            summary="Unable to generate summary for this thread.",
            key_points=[],
            invoice_details={},
            suggested_action="Manual review required",
        )

    return SummarizeThreadOutput(
        thread_id=input_data.thread_id,
        summary=result["summary"],
        key_points=result["key_points"],
        invoice_details=result["invoice_details"],
        suggested_action=result["suggested_action"],
    )


def mock_draft_email(input_data: DraftEmailInput, db: Session) -> DraftEmailOutput:
    """Mock Gmail draft creation: returns a local draft record."""
    draft_id = f"draft-{uuid.uuid4().hex[:8]}"
    return DraftEmailOutput(
        draft_id=draft_id,
        to=input_data.to,
        subject=input_data.subject,
        body_preview=input_data.body[:100] + ("..." if len(input_data.body) > 100 else ""),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def mock_create_calendar_event(input_data: CalendarEventInput, db: Session) -> CalendarEventOutput:
    """Mock Calendar event creation: returns a local event record."""
    event_id = f"event-{uuid.uuid4().hex[:8]}"
    return CalendarEventOutput(
        event_id=event_id,
        summary=input_data.summary,
        start_time=input_data.start_time,
        end_time=input_data.end_time,
        attendees=input_data.attendees,
    )


def mock_read_contact_memory(key: str, db: Session) -> Optional[dict]:
    """Read a contact memory entry by key."""
    entry = db.query(ContactMemory).filter(ContactMemory.key == key).first()
    if entry:
        return {
            "id": entry.id,
            "key": entry.key,
            "value": entry.value,
            "category": entry.category,
            "metadata_json": entry.metadata_json,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }
    return None


def mock_write_contact_memory(
    key: str, value: str, category: str, metadata_json: Optional[dict], db: Session
) -> dict:
    """Write or update a contact memory entry."""
    entry = db.query(ContactMemory).filter(ContactMemory.key == key).first()
    if entry:
        entry.value = value
        entry.category = category
        if metadata_json is not None:
            entry.metadata_json = metadata_json
        entry.updated_at = datetime.now(timezone.utc)
    else:
        entry = ContactMemory(
            id=str(uuid.uuid4()),
            key=key,
            value=value,
            category=category,
            metadata_json=metadata_json,
        )
        db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "id": entry.id,
        "key": entry.key,
        "value": entry.value,
        "category": entry.category,
        "metadata_json": entry.metadata_json,
    }
