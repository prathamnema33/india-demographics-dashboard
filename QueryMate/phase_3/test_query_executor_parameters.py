import unittest
from unittest.mock import MagicMock, patch

from phase_2.schema_grounding import Grounding, JoinDetails
from phase_3.query_executor import execute_query


class QueryExecutorParameterTests(unittest.TestCase):
    def test_postgres_rendered_parameters_use_driver_execution(self):
        connection = MagicMock()
        connection.begin.return_value.__enter__.return_value = None

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        page_result = MagicMock()
        page_result.mappings.return_value.fetchmany.return_value = [{"id": 7}]
        connection.execute.side_effect = [count_result, page_result]
        connection.exec_driver_sql.side_effect = [
            None,
            None,
            count_result,
            page_result,
        ]

        connection_context = MagicMock()
        connection_context.__enter__.return_value = connection
        engine = MagicMock()
        engine.connect.return_value = connection_context

        grounding = Grounding(
            main_table="user_detail",
            required_tables=["user_detail", "addresses"],
            selected_columns=["user_detail.id"],
            field_mapping=[],
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
        sql = """
            SELECT user_detail.id
            FROM user_detail
            JOIN addresses ON user_detail.address_id = addresses.id
            WHERE LOWER(TRIM(addresses.state)) = LOWER(TRIM(:param_1))
        """

        with patch("phase_3.query_executor.engine", engine):
            result = execute_query(
                sql,
                {"param_1": "Madhya Pradesh"},
                grounding,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], [{"id": 7}])
        connection.execute.assert_not_called()

        count_sql, count_params = connection.exec_driver_sql.call_args_list[2].args
        page_sql, page_params = connection.exec_driver_sql.call_args_list[3].args
        self.assertIn("%(param_1)s", count_sql)
        self.assertEqual(count_params, {"param_1": "Madhya Pradesh"})
        self.assertIn("%(param_1)s", page_sql)
        self.assertIn("%(limit)s", page_sql)
        self.assertIn("%(offset)s", page_sql)
        self.assertEqual(page_params["param_1"], "Madhya Pradesh")


if __name__ == "__main__":
    unittest.main()
