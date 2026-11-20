
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import sqlglot
from sqlglot import exp

from phase_2.database import engine
from phase_3.sql_validator import validate_sql


MAX_FETCH_LIMIT = 500


def execute_query(sql, params, grounding, page=1, page_size=50):

    # 1. Validate SQL before execution
    validation = validate_sql(sql, grounding)

    if not validation["valid"]:
        return {
            "success": False,
            "error": validation["reason"],
            "count": 0,
            "fetched_count": 0,
            "data": []
        }

    try:
        with engine.connect() as connection:

            with connection.begin():

                # 2. Start read-only transaction
                connection.exec_driver_sql(
                    "SET TRANSACTION READ ONLY"
                )

                # 3. Set query timeout
                connection.exec_driver_sql(
                    "SET LOCAL statement_timeout = '5000ms'"
                )

                # 4. Generate a separate count query. LIMIT and OFFSET are removed
                # before counting so totals describe the complete result set, not
                # only the requested page. Wrapping grouped/window output avoids
                # changing its meaning and also handles each output row once.
                sql_for_count = sql.strip().rstrip(";")
                count_uses_driver_parameters = False
                try:
                    count_tree = sqlglot.parse_one(
                        sql_for_count,
                        read="postgres",
                    )
                    count_tree.set("limit", None)
                    count_tree.set("offset", None)
                    sql_for_count = count_tree.sql(dialect="postgres")
                    count_uses_driver_parameters = True
                except Exception:
                    # The validator has already approved the SQL, so a count
                    # fallback is only needed for parser-version edge cases.
                    sql_for_count = sql_for_count

                count_params = dict(params)
                count_params.pop("limit", None)
                count_params.pop("offset", None)

                count_sql = f"""
                    SELECT COUNT(*)
                    FROM ({sql_for_count}) AS querymate_count
                """

                if count_uses_driver_parameters:
                    # SQLGlot renders PostgreSQL binds as psycopg's %(name)s;
                    # execute them through the DBAPI instead of text(), which
                    # expects SQLAlchemy's :name bind syntax.
                    count_result = connection.exec_driver_sql(
                        count_sql,
                        count_params,
                    )
                else:
                    count_result = connection.execute(
                        text(count_sql),
                        count_params,
                    )

                total_count = count_result.scalar_one()

                # 5. Fetch only a bounded page. The analysis limit is honored,
                # but page size is always clamped to 500 for memory safety.
                bounded_page_size = max(
                    1,
                    min(int(page_size), MAX_FETCH_LIMIT),
                )
                bounded_page = max(1, int(page))
                offset = (bounded_page - 1) * bounded_page_size

                page_sql = sql.rstrip().rstrip(";")
                page_params = dict(params)
                page_uses_driver_parameters = False
                try:
                    page_tree = sqlglot.parse_one(
                        page_sql,
                        read="postgres",
                    )
                    page_tree.set("limit", None)
                    page_tree.set("offset", None)
                    page_sql = page_tree.sql(dialect="postgres")
                    page_uses_driver_parameters = True
                except Exception:
                    # Validator-approved SQL normally parses here. If a parser
                    # edge case occurs, execute the original bounded query only
                    # when it already contains its own LIMIT.
                    pass

                page_params["limit"] = bounded_page_size
                page_params["offset"] = offset

                if page_uses_driver_parameters:
                    page_sql += "\nLIMIT %(limit)s"
                    page_sql += "\nOFFSET %(offset)s"
                    result = connection.exec_driver_sql(
                        page_sql,
                        page_params,
                    )
                else:
                    page_sql += "\nLIMIT :limit"
                    page_sql += "\nOFFSET :offset"
                    result = connection.execute(
                        text(page_sql),
                        page_params,
                    )

                records = result.mappings().fetchmany(
                    MAX_FETCH_LIMIT
                )

                data = [dict(record) for record in records]

                return {
                    "success": True,
                    "count": total_count,
                    "fetched_count": len(data),
                    "data": data,
                    "has_more": offset + len(data) < total_count,
                    "page": bounded_page,
                    "page_size": bounded_page_size,
                    "offset": offset,
                }

    except SQLAlchemyError as error:

        print("\nDATABASE ERROR:", repr(error))

        return {
            "success": False,
            "error": "Database query failed.",
            "count": 0,
            "fetched_count": 0,
            "data": []
        }

    except Exception as error:

        print("\nPROCESSING ERROR:", repr(error))

        return {
            "success": False,
            "error": "Query processing failed.",
            "count": 0,
            "fetched_count": 0,
            "data": []
        }
