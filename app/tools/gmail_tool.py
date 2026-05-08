"""Real Gmail API integration for email search and draft creation.

Only used when GOOGLE_API_ENABLED=true. Falls back to mock tools otherwise.
NEVER sends emails - only creates drafts.
"""

import base64
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.services.google_auth_service import get_gmail_service
from app.schemas.tool_schemas import (
    EmailSearchInput,
    EmailSearchOutput,
    EmailThreadSummary,
    DraftEmailInput,
    DraftEmailOutput,
    SummarizeThreadInput,
    SummarizeThreadOutput,
)
from app.tools.mock_tools import (
    mock_search_email,
    mock_summarize_thread,
    mock_draft_email,
)
from datetime import datetime


def real_search_email(input_data: EmailSearchInput, db: Session) -> EmailSearchOutput:
    """Search Gmail threads using the Gmail API.

    Constructs a Gmail-compatible query string and searches for threads.
    Returns structured thread summaries.
    """
    service = get_gmail_service()
    if not service:
        return mock_search_email(input_data, db)

    query = input_data.query
    max_results = input_data.max_results

    try:
        results = (
            service.users()
            .threads()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        threads = results.get("threads", [])
        output_threads = []

        for t in threads:
            thread_id = t["id"]
            thread_data = (
                service.users().threads().get(userId="me", id=thread_id, format="metadata").execute()
            )
            messages = thread_data.get("messages", [])
            first_msg = messages[0] if messages else {}

            headers = {
                h["name"]: h["value"]
                for h in first_msg.get("payload", {}).get("headers", [])
            }

            snippet = first_msg.get("snippet", "")
            subject = headers.get("Subject", "(no subject)")
            sender = headers.get("From", "unknown")
            date_str = headers.get("Date", "")

            output_threads.append(
                EmailThreadSummary(
                    thread_id=thread_id,
                    subject=subject,
                    sender=sender,
                    snippet=snippet,
                    is_payment_related=_is_payment_related(subject, snippet),
                    date=date_str if date_str else None,
                )
            )

        return EmailSearchOutput(threads=output_threads, total_found=len(output_threads))

    except Exception as e:
        return mock_search_email(input_data, db)


def real_draft_email(input_data: DraftEmailInput, db: Session) -> DraftEmailOutput:
    """Create a Gmail draft (NEVER sends).

    Uses Gmail API drafts.create to create a draft without sending.
    Falls back to mock if API is unavailable.
    """
    service = get_gmail_service()
    if not service:
        return mock_draft_email(input_data, db)

    try:
        message = MIMEText(input_data.body)
        message["to"] = input_data.to
        message["subject"] = input_data.subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        draft_body = {"message": {"raw": raw}}
        if input_data.thread_id:
            draft_body["message"]["threadId"] = input_data.thread_id

        draft = (
            service.users()
            .drafts()
            .create(userId="me", body=draft_body)
            .execute()
        )

        return DraftEmailOutput(
            draft_id=draft["id"],
            to=input_data.to,
            subject=input_data.subject,
            body_preview=input_data.body[:100],
            created_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        return mock_draft_email(input_data, db)


def _is_payment_related(subject: str, snippet: str) -> bool:
    """Heuristic to detect payment/invoice-related emails."""
    combined = f"{subject} {snippet}".lower()
    keywords = ["invoice", "payment", "overdue", "past due", "billing", "due"]
    return any(kw in combined for kw in keywords)
