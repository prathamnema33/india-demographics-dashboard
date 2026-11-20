import unittest

from phase_2.schema_grounding import Grounding
from phase_3.result_processor import process_result
from phase_3.sql_validator import validate_sql
from phase_4.response_generator import generate_response


GROUNDING = Grounding(
    main_table="user_detail",
    required_tables=["user_detail"],
    selected_columns=["user_detail.id"],
    field_mapping=[],
    joins=[],
    status="success",
)


class ResultPaginationTests(unittest.TestCase):
    def test_process_preserves_ranking_percentage_and_pagination(self):
        result = process_result({
            "success": True,
            "count": 101,
            "fetched_count": 2,
            "data": [
                {"rank_position": 1, "state": "Karnataka", "percentage": 25.125},
                {"rank_position": 2, "state": None, "percentage": None},
            ],
            "has_more": True,
            "page": 2,
            "page_size": 50,
            "offset": 50,
        })

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_records"], 101)
        self.assertEqual(result["records"][0]["percentage"], 25.125)
        self.assertTrue(result["has_more"])
        self.assertEqual(result["page"], 2)

    def test_empty_result(self):
        result = process_result({
            "success": True,
            "count": 0,
            "fetched_count": 0,
            "data": [],
            "has_more": False,
        })

        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["records"], [])

    def test_response_uses_aliases_and_handles_null(self):
        response = generate_response({
            "status": "success",
            "total_records": 1,
            "fetched_records": 1,
            "records": [
                {"rank_position": 1, "state": None, "percentage": 12.5}
            ],
            "page": 1,
            "has_more": False,
        })

        self.assertIn("Rank Position", response)
        self.assertIn("Percentage", response)
        self.assertIn("Not available", response)

    def test_security_rejections(self):
        dangerous_queries = [
            "UPDATE user_detail SET age = 20",
            "DROP TABLE user_detail",
            "SELECT * FROM user_detail",
            "SELECT PG_SLEEP(5) FROM user_detail",
            "SELECT user_detail.password FROM user_detail",
            "SELECT user_detail.id FROM secret_table",
            "SELECT user_detail.id FROM public.user_detail",
            "WITH ids AS (SELECT user_detail.id FROM user_detail) "
            "SELECT user_detail.id FROM user_detail",
            "SELECT user_detail.id FROM user_detail; "
            "DELETE FROM user_detail",
            "SELECT user_detail.id FROM user_detail FOR UPDATE",
        ]

        for sql in dangerous_queries:
            with self.subTest(sql=sql):
                result = validate_sql(sql, GROUNDING)
                self.assertFalse(result["valid"], result["reason"])

if __name__ == "__main__":
    unittest.main()
