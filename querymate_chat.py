"""Conversation handling shared by the Dash callback and focused unit tests."""

import logging
from typing import Any

from querymate_client import (
    QueryMateAPIError,
    QueryMateSessionExpired,
    create_session,
    send_message,
)


logger = logging.getLogger(__name__)
MAX_CHAT_MESSAGES = 100


def handle_chat_message(
    text_value: str,
    history: list[dict[str, Any]] | None,
    session_data: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Send a question/reply, maintain ordered history, and sanitize failures."""

    text_value = (text_value or "").strip()
    messages = list(history) if isinstance(history, list) else []
    if not text_value:
        return messages, dict(session_data or {})

    # Keep the user's entry even if the API is down so history remains honest
    # and the message can be retried by the user.
    messages.append({"role": "user", "text": text_value})
    session_data = dict(session_data or {})
    is_reply = bool(session_data.get("awaiting_reply"))
    session_id = session_data.get("session_id")

    try:
        if not session_id:
            session_id = create_session()

        try:
            response = send_message(
                session_id,
                text_value,
                is_reply=is_reply,
            )
        except QueryMateSessionExpired:
            if is_reply:
                # The confirmation/clarification context was held in memory by
                # FastAPI. Never send a bare "yes" as a new query after restart.
                session_id = create_session()
                session_data = {
                    "session_id": session_id,
                    "awaiting_reply": False,
                }
                messages.append({
                    "role": "assistant",
                    "text": (
                        "This chat session expired before the clarification "
                        "could be completed. Please send your original question again."
                    ),
                })
                return messages[-MAX_CHAT_MESSAGES:], session_data

            # A normal question can be replayed once in a new server session.
            session_id = create_session()
            response = send_message(
                session_id,
                text_value,
                is_reply=False,
            )

        status = str(response.get("status", "error"))
        backend_message = response.get("message")
        if not isinstance(backend_message, str) or not backend_message.strip():
            backend_message = (
                "I couldn't identify that location. Please check the spelling and try again."
                if status == "location_not_found"
                else "QueryMate returned no message. Please try again."
            )

        records = response.get("records")
        options = response.get("options")
        messages.append({
            "role": "assistant",
            "text": backend_message,
            "records": records if isinstance(records, list) else [],
            "options": options if isinstance(options, list) else [],
            "status": status,
        })

        session_data = {
            "session_id": session_id,
            "awaiting_reply": status in {
                "confirmation_required",
                "clarification_required",
            },
        }
    except QueryMateAPIError as error:
        messages.append({"role": "assistant", "text": str(error)})
        session_data = {
            "session_id": session_id,
            "awaiting_reply": False,
        }
    except Exception:
        logger.exception("Unexpected error while sending a QueryMate chat message")
        messages.append({
            "role": "assistant",
            "text": "Something went wrong while contacting QueryMate. Please try again.",
        })
        session_data = {
            "session_id": session_id,
            "awaiting_reply": False,
        }

    return messages[-MAX_CHAT_MESSAGES:], session_data
