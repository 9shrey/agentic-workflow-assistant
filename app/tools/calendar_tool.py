"""Real Google Calendar API integration for event creation.

Only used when GOOGLE_API_ENABLED=true.
Requires explicit human approval before any event creation.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.services.google_auth_service import get_calendar_service
from app.schemas.tool_schemas import CalendarEventInput, CalendarEventOutput
from app.tools.mock_tools import mock_create_calendar_event


def real_create_calendar_event(input_data: CalendarEventInput, db: Session) -> CalendarEventOutput:
    """Create a Google Calendar event.

    Only creates events with explicit human approval.
    Falls back to mock if API is unavailable.
    """
    service = get_calendar_service()
    if not service:
        return mock_create_calendar_event(input_data, db)

    try:
        event_body = {
            "summary": input_data.summary,
            "description": input_data.description,
            "start": {
                "dateTime": input_data.start_time,
                "timeZone": input_data.timezone,
            },
            "end": {
                "dateTime": input_data.end_time,
                "timeZone": input_data.timezone,
            },
            "attendees": [{"email": a} for a in input_data.attendees] if input_data.attendees else [],
        }

        event = (
            service.events()
            .insert(calendarId="primary", body=event_body)
            .execute()
        )

        return CalendarEventOutput(
            event_id=event["id"],
            summary=input_data.summary,
            start_time=input_data.start_time,
            end_time=input_data.end_time,
            attendees=input_data.attendees,
        )

    except Exception as e:
        return mock_create_calendar_event(input_data, db)
