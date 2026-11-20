"""Server-side HTTP client for the QueryMate FastAPI service."""

import os
from typing import Any

import requests


API_BASE_URL = os.getenv(
    "QUERYMATE_API_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

try:
    API_TIMEOUT_SECONDS = float(
        os.getenv("QUERYMATE_API_TIMEOUT_SECONDS", "30")
    )
except ValueError:
    API_TIMEOUT_SECONDS = 30.0


class QueryMateAPIError(Exception):
    """A safe, user-displayable API communication error."""


class QueryMateSessionExpired(QueryMateAPIError):
    """Raised when the in-memory FastAPI session no longer exists."""


def _request_json(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """Send one bounded HTTP request and normalize API errors for the UI."""

    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            timeout=API_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.Timeout as error:
        raise QueryMateAPIError(
            "QueryMate took too long to respond. Please try again."
        ) from error
    except requests.ConnectionError as error:
        raise QueryMateAPIError(
            "QueryMate is unavailable right now. Please check that the API is running."
        ) from error
    except requests.RequestException as error:
        raise QueryMateAPIError(
            "I couldn't connect to QueryMate. Please try again."
        ) from error

    if response.status_code == 404:
        raise QueryMateSessionExpired(
            "This chat session has expired. Please start a new question."
        )
    if response.status_code == 422:
        raise QueryMateAPIError(
            "I couldn't read that request. Please rephrase your message."
        )
    if response.status_code >= 500:
        raise QueryMateAPIError(
            "QueryMate had a server problem. Please try again in a moment."
        )
    if not response.ok:
        raise QueryMateAPIError(
            "QueryMate couldn't process that request. Please try again."
        )

    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError) as error:
        raise QueryMateAPIError(
            "QueryMate returned an unreadable response. Please try again."
        ) from error

    if not isinstance(payload, dict):
        raise QueryMateAPIError(
            "QueryMate returned an unexpected response. Please try again."
        )
    return payload


def create_session() -> str:
    """Create a server-side conversation and return its opaque session ID."""

    payload = _request_json("GET", "/create-session")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise QueryMateAPIError(
            "QueryMate couldn't start a chat session. Please try again."
        )
    return session_id


def send_message(session_id: str, text: str, is_reply: bool = False) -> dict[str, Any]:
    """Send a question or confirmation reply using the active session."""

    key = "reply" if is_reply else "question"
    return _request_json(
        "POST",
        f"/ask/{session_id}",
        json={key: text},
    )
