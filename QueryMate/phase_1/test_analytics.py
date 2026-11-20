import unittest

from pydantic import ValidationError

from phase_1.schema import QuestionAnalysis


class Phase1AnalyticsTests(unittest.TestCase):
    def analyze(self, payload: dict) -> QuestionAnalysis:
        """Validate a Phase 1 structure in the same way Gemini responses are validated."""

        return QuestionAnalysis.model_validate(payload)

    def test_total_user_count(self):
        result = self.analyze({
            "intent": "count_records",
            "entity": ["users"],
            "aggregations": [
                {"function": "COUNT", "field": "id", "alias": "user_count"}
            ],
        })

        self.assertEqual(result.intent, "count_records")
        self.assertEqual(result.aggregations[0].function, "COUNT")
        self.assertEqual(result.aggregations[0].field, "id")

    def test_average_age(self):
        result = self.analyze({
            "intent": "aggregate_records",
            "entity": ["users"],
            "aggregations": [
                {"function": "AVG", "field": "age", "alias": "average_age"}
            ],
        })

        self.assertEqual(result.aggregations[0].function, "AVG")
        self.assertEqual(result.aggregations[0].field, "age")

    def test_religion_wise_distribution(self):
        result = self.analyze({
            "intent": "aggregate_records",
            "entity": ["users"],
            "aggregations": [
                {"function": "COUNT", "field": "id", "alias": "population"}
            ],
            "group_by": ["religion"],
        })

        self.assertEqual(result.group_by, ["religion"])

    def test_religion_wise_percentage(self):
        result = self.analyze({
            "intent": "aggregate_records",
            "entity": ["users"],
            "percentage": True,
            "percentage_details": {
                "enabled": True,
                "scope": "overall",
            },
            "group_by": ["religion"],
        })

        self.assertTrue(result.percentage)
        self.assertEqual(result.percentage_details.scope, "overall")

    def test_literacy_percentage_by_state(self):
        result = self.analyze({
            "intent": "aggregate_records",
            "entity": ["users"],
            "percentage": True,
            "percentage_details": {
                "enabled": True,
                "scope": "within_group",
                "denominator_field": "id",
                "denominator_group": ["state"],
            },
            "group_by": ["state"],
        })

        self.assertEqual(result.percentage_details.denominator_group, ["state"])

    def test_rank_states_by_population(self):
        result = self.analyze({
            "intent": "rank_records",
            "entity": ["states"],
            "group_by": ["state"],
            "ranking": {
                "function": "RANK",
                "order_by": "population",
                "order": "descending",
            },
        })

        self.assertEqual(result.ranking.function, "RANK")
        self.assertEqual(result.ranking.order_by, "population")

    def test_rank_religions_within_each_state(self):
        result = self.analyze({
            "intent": "rank_records",
            "entity": ["religions"],
            "group_by": ["state", "religion"],
            "ranking": {
                "function": "DENSE_RANK",
                "order_by": "population",
                "order": "descending",
                "partition_by": ["state"],
            },
        })

        self.assertEqual(result.ranking.partition_by, ["state"])

    def test_ntile_age_segmentation(self):
        result = self.analyze({
            "intent": "rank_records",
            "entity": ["users"],
            "ranking": {
                "function": "NTILE",
                "order_by": "age",
                "order": "ascending",
                "buckets": 4,
            },
        })

        self.assertEqual(result.ranking.function, "NTILE")
        self.assertEqual(result.ranking.buckets, 4)

    def test_ambiguous_percentage_requires_clarification(self):
        result = self.analyze({
            "intent": "clarification_required",
            "entity": ["users"],
            "percentage": True,
            "clarification_question": "Do you mean within each state or overall?",
            "clarification_reason": "ambiguous_percentage_denominator",
        })

        self.assertEqual(result.intent, "clarification_required")
        self.assertEqual(
            result.clarification_reason,
            "ambiguous_percentage_denominator",
        )

    def test_having_is_separate_from_where(self):
        result = self.analyze({
            "intent": "aggregate_records",
            "entity": ["states"],
            "filters": [
                {"field": "gender", "operator": "equals", "value": "female"}
            ],
            "group_by": ["state"],
            "having": [
                {"field": "population", "operator": ">", "value": "1000"}
            ],
        })

        self.assertEqual(result.filters[0].field, "gender")
        self.assertEqual(result.having[0].operator, ">")

    def test_supported_ranking_functions(self):
        for function in ("ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE"):
            with self.subTest(function=function):
                result = self.analyze({
                    "intent": "rank_records",
                    "entity": ["users"],
                    "ranking": {
                        "function": function,
                        "order_by": "age",
                        "order": "descending",
                        "buckets": 4 if function == "NTILE" else None,
                    },
                })
                self.assertEqual(result.ranking.function, function)

    def test_invalid_ranking_function_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.analyze({
                "intent": "rank_records",
                "entity": ["users"],
                "ranking": {
                    "function": "PERCENT_RANK",
                    "order_by": "age",
                    "order": "descending",
                },
            })

    def test_distinct_pagination_and_sort(self):
        result = self.analyze({
            "intent": "retrieve_records",
            "entity": ["users"],
            "distinct": True,
            "sort": {"field": "age", "order": "descending"},
            "limit": 10,
            "offset": 20,
        })

        self.assertTrue(result.distinct)
        self.assertEqual(result.sort.field, "age")
        self.assertEqual(result.limit, 10)
        self.assertEqual(result.offset, 20)

    def test_date_filters_are_structured(self):
        result = self.analyze({
            "intent": "retrieve_records",
            "entity": ["users"],
            "date_filters": [
                {
                    "field": "dob",
                    "period": "between",
                    "value": "1990-01-01",
                    "end_value": "1999-12-31",
                }
            ],
        })

        self.assertEqual(result.date_filters[0].field, "dob")
        self.assertEqual(result.date_filters[0].period, "between")


if __name__ == "__main__":
    unittest.main()
