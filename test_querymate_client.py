import unittest
from unittest.mock import patch

import requests

import querymate_client
from querymate_client import (
    QueryMateAPIError,
    QueryMateSessionExpired,
    create_session,
    send_message,
)


class FakeResponse:
    def __init__(self, status_code, payload=None, json_error=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class QueryMateClientTests(unittest.TestCase):
    @patch("querymate_client.requests.request")
    def test_create_session(self, request):
        request.return_value = FakeResponse(
            200,
            {"session_id": "session-1", "status": "Session created"},
        )

        result = create_session()

        self.assertEqual(result, "session-1")
        request.assert_called_once_with(
            "GET",
            f"{querymate_client.API_BASE_URL}/create-session",
            timeout=querymate_client.API_TIMEOUT_SECONDS,
        )

    @patch("querymate_client.requests.request")
    def test_question_and_confirmation_use_expected_payload(self, request):
        request.return_value = FakeResponse(200, {"status": "success"})

        send_message("session-1", "Show users")
        send_message("session-1", "yes", is_reply=True)

        self.assertEqual(request.call_args_list[0].kwargs["json"], {
            "question": "Show users"
        })
        self.assertEqual(request.call_args_list[1].kwargs["json"], {
            "reply": "yes"
        })
        self.assertIn("/ask/session-1", request.call_args_list[0].args[1])

    @patch("querymate_client.requests.request")
    def test_expired_session_is_distinguished(self, request):
        request.return_value = FakeResponse(404, {"detail": "Session not found"})

        with self.assertRaises(QueryMateSessionExpired):
            send_message("expired", "Show users")

    @patch("querymate_client.requests.request")
    def test_timeout_and_connection_errors_are_user_friendly(self, request):
        for error in (requests.Timeout(), requests.ConnectionError()):
            request.side_effect = error
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(QueryMateAPIError) as caught:
                    create_session()
                self.assertNotIn("Traceback", str(caught.exception))

    @patch("querymate_client.requests.request")
    def test_http_and_invalid_json_errors_are_sanitized(self, request):
        request.return_value = FakeResponse(422, {"detail": "internal"})
        with self.assertRaisesRegex(QueryMateAPIError, "rephrase"):
            create_session()

        request.return_value = FakeResponse(
            200,
            json_error=ValueError("not JSON"),
        )
        with self.assertRaisesRegex(QueryMateAPIError, "unreadable"):
            create_session()

    @patch("querymate_client.requests.request")
    def test_server_errors_are_sanitized(self, request):
        request.return_value = FakeResponse(500, {"detail": "stack trace"})

        with self.assertRaisesRegex(QueryMateAPIError, "server problem"):
            create_session()


if __name__ == "__main__":
    unittest.main()
