import unittest
from unittest.mock import patch

from querymate_chat import handle_chat_message
from querymate_client import QueryMateAPIError, QueryMateSessionExpired


class QueryMateChatTests(unittest.TestCase):
    def test_question_creates_and_reuses_session_for_confirmation(self):
        history = [{"role": "assistant", "text": "Welcome"}]
        with patch("querymate_chat.create_session", return_value="tab-1") as create, patch(
            "querymate_chat.send_message",
            return_value={
                "status": "confirmation_required",
                "message": "Did you mean Madhya Pradesh?",
            },
        ) as send:
            messages, session = handle_chat_message(
                "Show users from Madhya Prdesh",
                history,
                None,
            )

        create.assert_called_once_with()
        send.assert_called_once_with(
            "tab-1",
            "Show users from Madhya Prdesh",
            is_reply=False,
        )
        self.assertEqual(session["session_id"], "tab-1")
        self.assertTrue(session["awaiting_reply"])
        self.assertEqual(messages[-1]["status"], "confirmation_required")

        with patch("querymate_chat.create_session") as create, patch(
            "querymate_chat.send_message",
            return_value={"status": "success", "message": "Done"},
        ) as send:
            messages, session = handle_chat_message(
                "yes",
                messages,
                session,
            )

        create.assert_not_called()
        send.assert_called_once_with("tab-1", "yes", is_reply=True)
        self.assertFalse(session["awaiting_reply"])
        self.assertEqual(messages[-2]["text"], "yes")

    def test_question_retries_once_after_backend_restart(self):
        with patch(
            "querymate_chat.send_message",
            side_effect=[
                QueryMateSessionExpired("expired"),
                {"status": "success", "message": "Results"},
            ],
        ) as send, patch(
            "querymate_chat.create_session",
            return_value="new-session",
        ) as create:
            messages, session = handle_chat_message(
                "Show 10 users",
                [],
                {"session_id": "old-session", "awaiting_reply": False},
            )

        create.assert_called_once_with()
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args.args[0], "new-session")
        self.assertEqual(session["session_id"], "new-session")
        self.assertEqual(messages[-1]["text"], "Results")

    def test_expired_confirmation_does_not_send_yes_as_question(self):
        with patch(
            "querymate_chat.send_message",
            side_effect=QueryMateSessionExpired("expired"),
        ) as send, patch(
            "querymate_chat.create_session",
            return_value="fresh-session",
        ) as create:
            messages, session = handle_chat_message(
                "yes",
                [],
                {"session_id": "old-session", "awaiting_reply": True},
            )

        create.assert_called_once_with()
        send.assert_called_once()
        self.assertEqual(session["session_id"], "fresh-session")
        self.assertFalse(session["awaiting_reply"])
        self.assertIn("original question again", messages[-1]["text"])

    def test_api_errors_are_user_facing_and_history_is_bounded(self):
        history = [
            {"role": "user", "text": str(index)}
            for index in range(100)
        ]
        with patch(
            "querymate_chat.create_session",
            side_effect=QueryMateAPIError("QueryMate is unavailable."),
        ):
            messages, _ = handle_chat_message(
                "Show users",
                history,
                None,
            )

        self.assertEqual(len(messages), 100)
        self.assertEqual(messages[-2]["text"], "Show users")
        self.assertEqual(messages[-1]["text"], "QueryMate is unavailable.")
        self.assertNotIn("Traceback", messages[-1]["text"])

    def test_clarification_status_enables_reply_mode(self):
        with patch("querymate_chat.create_session", return_value="tab-2"), patch(
            "querymate_chat.send_message",
            return_value={
                "status": "clarification_required",
                "message": "Which group do you mean?",
                "options": [{"number": "1", "location": "Choice"}],
            },
        ):
            messages, session = handle_chat_message(
                "Show people",
                [],
                {},
            )

        self.assertTrue(session["awaiting_reply"])
        self.assertEqual(messages[-1]["options"][0]["number"], "1")


if __name__ == "__main__":
    unittest.main()
