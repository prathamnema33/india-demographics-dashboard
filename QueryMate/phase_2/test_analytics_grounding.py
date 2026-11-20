import unittest

from phase_2.schema_grounding import (
    Grounding,
    FieldMapping,
    JoinDetails,
    validate_grounding,
)


class Phase2AnalyticsGroundingTests(unittest.TestCase):
    def valid_grounding(self) -> Grounding:
        return Grounding(
            main_table="user_detail",
            required_tables=["user_detail", "addresses"],
            selected_columns=[
                "addresses.state",
                "user_detail.religion",
            ],
            field_mapping=[
                FieldMapping(
                    source_field="state",
                    mapped_column="addresses.state",
                )
            ],
            joins=[
                JoinDetails(
                    left_table="user_detail",
                    left_column="address_id",
                    right_table="addresses",
                    right_column="id",
                )
            ],
            aggregation_fields=["user_detail.id"],
            grouping_fields=["addresses.state"],
            filtering_fields=["addresses.state"],
            status="success",
        )

    def test_valid_aggregation_and_grouping_fields(self):
        grounding = self.valid_grounding()
        valid, reason = validate_grounding(grounding)

        self.assertTrue(valid)
        self.assertIn("passed", reason)

    def test_valid_ranking_and_partition_fields(self):
        grounding = self.valid_grounding()
        grounding.ranking_fields = ["user_detail.age"]
        grounding.partition_fields = ["addresses.state"]

        valid, _ = validate_grounding(grounding)

        self.assertTrue(valid)

    def test_invalid_field_is_rejected(self):
        grounding = self.valid_grounding()
        grounding.aggregation_fields = ["user_detail.password"]

        valid, reason = validate_grounding(grounding)

        self.assertFalse(valid)
        self.assertIn("Unauthorized analytical column", reason)

    def test_invalid_table_is_rejected(self):
        grounding = self.valid_grounding()
        grounding.required_tables.append("credentials")

        valid, reason = validate_grounding(grounding)

        self.assertFalse(valid)
        self.assertIn("Unauthorized table", reason)

    def test_invalid_join_is_rejected(self):
        grounding = self.valid_grounding()
        grounding.joins[0].right_column = "city"

        valid, reason = validate_grounding(grounding)

        self.assertFalse(valid)
        self.assertIn("unauthorized join", reason)

    def test_invalid_field_mapping_is_rejected(self):
        grounding = self.valid_grounding()
        grounding.field_mapping[0].mapped_column = "public.users.password"

        valid, reason = validate_grounding(grounding)

        self.assertFalse(valid)
        self.assertIn("Unauthorized field mapping", reason)

    def test_main_table_must_be_required(self):
        grounding = self.valid_grounding()
        grounding.required_tables = ["addresses"]

        valid, reason = validate_grounding(grounding)

        self.assertFalse(valid)
        self.assertIn("Main table", reason)


if __name__ == "__main__":
    unittest.main()
