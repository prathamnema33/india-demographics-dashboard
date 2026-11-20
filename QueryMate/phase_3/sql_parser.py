
# import sqlglot
# from sqlglot import exp


# def parse_sql(sql: str):

#     try:
#         parsed = sqlglot.parse(sql, read="postgres")

#         # Only one SQL statement is allowed.
#         if len(parsed) != 1 or parsed[0] is None:
#             raise ValueError("Only one SQL statement is allowed.")

#         statement = parsed[0]

#         # Check statement type.
#         if not isinstance(statement, exp.Select):
#             raise ValueError("Only SELECT queries are supported.")

#         # Extract tables.
#         tables = [
#             table.name
#             for table in statement.find_all(exp.Table)
#         ]

#         # Extract columns.
#         columns = [
#             column.sql(dialect="postgres")
#             for column in statement.find_all(exp.Column)
#         ]

#         return {
#             "valid": True,
#             "statement_type": "SELECT",
#             "tables": tables,
#             "columns": columns,
#             "parsed_sql": statement.sql(dialect="postgres")
#         }

#     except (sqlglot.errors.ParseError, ValueError) as error:
#         return {
#             "valid": False,
#             "error": str(error)
#         }

import sqlglot
from sqlglot import exp


def parse_sql(sql: str):

    if not isinstance(sql, str) or not sql.strip():
        return {
            "valid": False,
            "error": "SQL query cannot be empty."
        }

    try:
        parsed = sqlglot.parse(sql, read="postgres")

        # 1. Only one SQL statement is allowed.
        if len(parsed) != 1 or parsed[0] is None:
            raise ValueError(
                "Only one SQL statement is allowed."
            )

        statement = parsed[0]

        # 2. Only SELECT statements are supported.
        if not isinstance(statement, exp.Select):
            raise ValueError(
                "Only SELECT queries are supported."
            )

        # 3. Extract tables.
        tables = [
            table.name
            for table in statement.find_all(exp.Table)
        ]

        # 4. Extract columns.
        columns = [
            column.sql(dialect="postgres")
            for column in statement.find_all(exp.Column)
        ]

        return {
            "valid": True,
            "statement_type": "SELECT",
            "tables": tables,
            "columns": columns,
            "parsed_sql": statement.sql(dialect="postgres")
        }

    except (sqlglot.errors.ParseError, ValueError) as error:

        return {
            "valid": False,
            "error": str(error)
        }

    except Exception:

        return {
            "valid": False,
            "error": "Unexpected SQL parsing error."
        }
