import unittest
from unittest.mock import patch

# FastAPI's module normally loads the location vocabulary at import. Stubbing
# that DB-backed setup keeps session-contract tests isolated from PostgreSQL.
with patch("phase_0.query_corrector.load_location_vocabulary", return_value=[]):
    from api import api as api_module

from fastapi.testclient import TestClient


class ChatSessionContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api_module.app)

    def new_session(self):
        response = self.client.get("/create-session")
        self.assertEqual(response.status_code, 200)
        return response.json()["session_id"]

    @patch.object(api_module, "prepare_location_confirmation")
    @patch.object(api_module, "run_querymate")
    def test_normal_question_returns_pipeline_result(
        self,
        run_querymate,
        prepare_location_confirmation,
    ):
        session_id = self.new_session()
        prepare_location_confirmation.return_value = {
            "status": "no_correction_needed",
        }
        run_querymate.return_value = {
            "status": "success",
            "message": "Here are the results.",
            "total_records": 1,
            "fetched_records": 1,
            "records": [{"age": 31}],
        }

        response = self.client.post(
            f"/ask/{session_id}",
            json={"question": "Show average age by religion"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["records"], [{"age": 31}])

    @patch.object(api_module, "run_querymate")
    def test_general_clarification_reply_keeps_original_question(
        self,
        run_querymate,
    ):
        session_id = self.new_session()
        run_querymate.side_effect = [
            {
                "status": "clarification_required",
                "message": "Which group do you mean?",
            },
            {
                "status": "success",
                "message": "Here are the results.",
                "records": [],
            },
        ]

        first = self.client.post(
            f"/ask/{session_id}",
            json={"question": "Show people by their group"},
        )
        second = self.client.post(
            f"/ask/{session_id}",
            json={"reply": "People between 20 and 30"},
        )

        self.assertEqual(first.json()["status"], "clarification_required")
        self.assertEqual(second.json()["status"], "success")
        continuation = run_querymate.call_args_list[1].args[0]
        self.assertIn("Show people by their group", continuation)
        self.assertIn("20 and 30", continuation)

    @patch.object(api_module, "prepare_location_confirmation")
    @patch.object(api_module, "run_querymate")
    def test_location_confirmation_reuses_same_session(
        self,
        run_querymate,
        prepare_location_confirmation,
    ):
        session_id = self.new_session()
        prepare_location_confirmation.return_value = {
            "status": "confirmation_required",
            "original_question": "Show users from Madhya Prdesh",
            "suggested_question": "Show users from Madhya Pradesh",
            "confirmation_question": "Did you mean Madhya Pradesh?",
        }
        run_querymate.return_value = {
            "status": "success",
            "message": "Here are the results.",
            "records": [],
        }

        first = self.client.post(
            f"/ask/{session_id}",
            json={"question": "Show users from Madhya Prdesh"},
        )
        second = self.client.post(
            f"/ask/{session_id}",
            json={"reply": "yes"},
        )

        self.assertEqual(first.json()["status"], "confirmation_required")
        self.assertEqual(second.json()["status"], "success")
        self.assertEqual(
            run_querymate.call_args.args[0],
            "Show users from Madhya Pradesh",
        )

    @patch.object(api_module, "prepare_location_confirmation")
    @patch.object(api_module, "run_querymate")
    def test_sessions_keep_pending_state_isolated(
        self,
        run_querymate,
        prepare_location_confirmation,
    ):
        first_session = self.new_session()
        second_session = self.new_session()
        prepare_location_confirmation.return_value = {
            "status": "no_correction_needed",
        }
        run_querymate.return_value = {
            "status": "clarification_required",
            "message": "Please clarify.",
        }

        self.client.post(
            f"/ask/{first_session}",
            json={"question": "Question requiring clarification"},
        )

        first_state = self.client.get(f"/session/{first_session}").json()
        second_state = self.client.get(f"/session/{second_session}").json()
        self.assertEqual(first_state["pending_state"], "query_clarification")
        self.assertIsNone(second_state["pending_state"])


if __name__ == "__main__":
    unittest.main()
