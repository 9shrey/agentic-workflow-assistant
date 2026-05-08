"""Tool registry that dispatches to mock or real tools based on GOOGLE_API_ENABLED."""

from app.config import settings
from app.schemas.tool_schemas import (
    CalendarEventInput,
    CalendarEventOutput,
    DraftEmailInput,
    DraftEmailOutput,
    EmailSearchInput,
    EmailSearchOutput,
    SummarizeThreadInput,
    SummarizeThreadOutput,
)
from app.tools.mock_tools import (
    mock_create_calendar_event,
    mock_draft_email,
    mock_read_contact_memory,
    mock_search_email,
    mock_summarize_thread,
    mock_write_contact_memory,
)
from sqlalchemy.orm import Session
from typing import Optional


_USE_MOCK = not settings.google_api_enabled


def search_email(input_data: EmailSearchInput, db: Session) -> EmailSearchOutput:
    if _USE_MOCK:
        return mock_search_email(input_data, db)
    raise NotImplementedError("Real Gmail search not yet implemented")


def summarize_thread(input_data: SummarizeThreadInput, db: Session) -> SummarizeThreadOutput:
    if _USE_MOCK:
        return mock_summarize_thread(input_data, db)
    raise NotImplementedError("Real summarize not yet implemented")


def draft_email(input_data: DraftEmailInput, db: Session) -> DraftEmailOutput:
    if _USE_MOCK:
        return mock_draft_email(input_data, db)
    raise NotImplementedError("Real Gmail draft not yet implemented")


def create_calendar_event(input_data: CalendarEventInput, db: Session) -> CalendarEventOutput:
    if _USE_MOCK:
        return mock_create_calendar_event(input_data, db)
    raise NotImplementedError("Real Calendar event not yet implemented")


def read_contact_memory(key: str, db: Session) -> Optional[dict]:
    return mock_read_contact_memory(key, db)


def write_contact_memory(
    key: str, value: str, category: str, metadata_json: Optional[dict], db: Session
) -> dict:
    return mock_write_contact_memory(key, value, category, metadata_json, db)
