
from sqlalchemy import inspect
from phase_2.database import engine, test_connection
import json


def inspect_database():

    if not test_connection():
        return

    inspector = inspect(engine)

    schema_info = {}

    tables = inspector.get_table_names(schema="public")

    for table in tables:

        columns = inspector.get_columns(
            table,
            schema="public"
        )

        primary_key = inspector.get_pk_constraint(
            table,
            schema="public"
        )

        foreign_keys = inspector.get_foreign_keys(
            table,
            schema="public"
        )

        schema_info[table] = {
            "columns": [
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": column["nullable"]
                }
                for column in columns
            ],

            "primary_key": primary_key.get(
                "constrained_columns", []
            ),

            "foreign_keys": [
                {
                    "columns": fk["constrained_columns"],
                    "referenced_table": fk["referred_table"],
                    "referenced_columns": fk["referred_columns"]
                }
                for fk in foreign_keys
            ]
        }

    return schema_info


if __name__ == "__main__":
    inspect_database()
