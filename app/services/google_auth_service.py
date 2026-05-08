"""Google OAuth2 service for Gmail and Calendar API access.

Handles token generation, refresh, and credential management.
Only used when GOOGLE_API_ENABLED=true.
"""

import os
import pickle
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import settings

# Minimal scopes for MVP
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",   # Read email threads
    "https://www.googleapis.com/auth/gmail.compose",     # Create drafts (NEVER send)
    "https://www.googleapis.com/auth/calendar.events",   # Create calendar events
]


def _build_client_config() -> dict:
    """Build the OAuth client config from environment variables."""
    return {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [settings.google_redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_credentials() -> Optional[Credentials]:
    """Get stored Google OAuth credentials or initiate OAuth flow.

    Returns None if Google APIs are not enabled or if credentials
    are not available and interactive auth cannot proceed.
    """
    if not settings.google_api_enabled:
        return None

    creds = None
    token_path = settings.google_token_path

    if os.path.exists(token_path):
        with open(token_path, "rb") as token_file:
            creds = pickle.load(token_file)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if os.path.exists(token_path):
                os.remove(token_path)

    return creds


def initiate_oauth_flow(port: int = 8000) -> Optional[Credentials]:
    """Initiate interactive OAuth flow (for CLI setup).

    Opens browser for user authentication and saves token.
    """
    if not settings.google_api_enabled:
        return None

    client_config = _build_client_config()
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=port)

    token_path = settings.google_token_path
    with open(token_path, "wb") as token_file:
        pickle.dump(creds, token_file)

    return creds


def get_gmail_service():
    """Get a Gmail API service instance."""
    creds = get_credentials()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


def get_calendar_service():
    """Get a Calendar API service instance."""
    creds = get_credentials()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=creds)
