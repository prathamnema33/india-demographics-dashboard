import unittest

from phase_1.schema import QuestionAnalysis
from phase_2.schema_grounding import Grounding, FieldMapping, JoinDetails
from phase_3.sql_generator import generate_sql
from phase_3.sql_validator import validate_sql


def grounding() -> Grounding:
    return Grounding(
        main_table="user_detail",
        required_tables=["user_detail", "addresses"],
        selected_columns=[
            "user_detail.first_name",
            "user_detail.last_name",
            "user_detail.age",
            "addresses.state",
        ],
        field_mapping=[
            FieldMapping(source_field="state", mapped_column="addresses.state"),
            FieldMapping(source_field="gender", mapped_column="user_detail.gender"),
            FieldMapping(source_field="religion", mapped_column="user_detail.religion"),
            FieldMapping(source_field="age", mapped_column="user_detail.age"),
            FieldMapping(source_field="literate", mapped_column="user_detail.literate"),
            FieldMapping(source_field="population", mapped_column="user_detail.id"),
        ],
        joins=[
            JoinDetails(
                left_table="user_detail",
                left_column="address_id",
                right_table="addresses",
                right_column="id",
            )
        ],
        status="success",
    )


class Phase3AnalyticsSQLTests(unittest.TestCase):
    def generate(self, payload: dict) -> tuple[str, dict]:
        analysis = QuestionAnalysis.model_validate(payload)
        sql, params = generate_sql(analysis, grounding())
        validation = validate_sql(sql, grounding())
        self.assertTrue(validation["valid"], validation["reason"])
        return sql, params

    def test_count(self):
        sql, _ = self.generate({
            "intent": "count_records",
            "entity": ["users"],
            "aggregations": [{"function": "COUNT", "field": "id", "alias": "population"}],
        })
        self.assertIn("COUNT(user_detail.id)", sql)

    def test_human_language_alias_is_sanitized(self):
        sql, _ = self.generate({
            "intent": "aggregate_records",
            "entity": ["users"],
            "aggregations": [
                {
                    "function": "COUNT",
                    "field": "id",
                    "alias": "Number of People",
                }
            ],
            "group_by": ["religion"],
        })
        self.assertIn("AS number_of_people", sql)

    def test_avg_min_max_and_sum(self):
        for function in ("SUM", "AVG", "MIN", "MAX"):
            with self.subTest(function=function):
                sql, _ = self.generate({
                    "intent": "aggregate_records",
                    "entity": ["users"],
                    "aggregations": [
                        {"function": function, "field": "age", "alias": f"{function.lower()}_age"}
                    ],
                })
                self.assertIn(f"{function}(user_detail.age)", sql)

    def test_group_by_and_having(self):
        sql, params = self.generate({
            "intent": "aggregate_records",
            "entity": ["states"],
            "aggregations": [{"function": "COUNT", "field": "id", "alias": "population"}],
            "group_by": ["state"],
            "having": [{"field": "population", "operator": ">", "value": "1000"}],
        })
        self.assertIn("GROUP BY addresses.state", sql)
        self.assertIn("HAVING population >", sql)
        self.assertEqual(params["having_param_1"], "1000")

    def test_multiple_filters_and_in(self):
        sql, params = self.generate({
            "intent": "retrieve_records",
            "entity": ["users"],
            "filters": [
                {"field": "gender", "operator": "equals", "value": "female"},
                {"field": "state", "operator": "in", "value": "Karnataka, Kerala"},
            ],
        })
        self.assertIn("LOWER(TRIM(user_detail.gender))", sql)
        self.assertIn("addresses.state IN", sql)
        self.assertEqual(params["param_2"], "Karnataka")

    def test_percentage_overall(self):
        sql, _ = self.generate({
            "intent": "aggregate_records",
            "entity": ["users"],
            "percentage": True,
            "percentage_details": {"enabled": True, "scope": "overall"},
            "aggregations": [{"function": "COUNT", "field": "id", "alias": "population"}],
            "group_by": ["religion"],
        })
        self.assertIn("SUM(COUNT(*)) OVER ()", sql)
        self.assertIn("AS percentage", sql)

    def test_percentage_within_state(self):
        sql, _ = self.generate({
            "intent": "aggregate_records",
            "entity": ["users"],
            "percentage": True,
            "percentage_details": {
                "enabled": True,
                "scope": "within_group",
                "denominator_group": ["state"],
            },
            "aggregations": [{"function": "COUNT", "field": "id", "alias": "population"}],
            "group_by": ["state"],
        })
        self.assertIn("PARTITION BY addresses.state", sql)

    def test_rank_and_partition(self):
        sql, _ = self.generate({
            "intent": "rank_records",
            "entity": ["states"],
            "aggregations": [{"function": "COUNT", "field": "id", "alias": "population"}],
            "group_by": ["state"],
            "ranking": {
                "function": "RANK",
                "order_by": "population",
                "order": "descending",
                "partition_by": ["state"],
            },
        })
        self.assertIn("RANK()", sql)
        self.assertIn("PARTITION BY addresses.state", sql)
        self.assertIn("AS rank_position", sql)

    def test_dense_rank_and_ntile(self):
        for payload in (
            {
                "intent": "rank_records",
                "entity": ["users"],
                "ranking": {
                    "function": "DENSE_RANK",
                    "order_by": "age",
                    "order": "descending",
                },
            },
            {
                "intent": "rank_records",
                "entity": ["users"],
                "ranking": {
                    "function": "NTILE",
                    "order_by": "age",
                    "order": "ascending",
                    "buckets": 4,
                },
            },
        ):
            sql, _ = self.generate(payload)
            self.assertIn("OVER", sql)

    def test_distinct_limit_offset_and_sort(self):
        sql, params = self.generate({
            "intent": "retrieve_records",
            "entity": ["users"],
            "distinct": True,
            "sort": {"field": "age", "order": "descending"},
            "limit": 10,
            "offset": 20,
        })
        self.assertIn("SELECT DISTINCT", sql)
        self.assertIn("LIMIT :limit", sql)
        self.assertIn("OFFSET :offset", sql)
        self.assertEqual(params["limit"], 10)
        self.assertEqual(params["offset"], 20)

    def test_delete_is_rejected(self):
        result = validate_sql(
            "DELETE FROM user_detail",
            grounding(),
        )
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
