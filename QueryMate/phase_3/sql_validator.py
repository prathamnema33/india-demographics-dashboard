import sqlglot
from sqlglot import exp

from phase_3.sql_parser import parse_sql
from phase_3.sql_generator import (
    ALLOWED_COLUMNS,
    ALLOWED_TABLES,
    ALLOWED_JOINS,
)


# This allowlist is intentionally narrower than SQL/PostgreSQL. It permits
# only operations used by QueryMate; sqlglot parsing alone is not sufficient
# because parsing a function does not establish that it is safe.
ALLOWED_FUNCTIONS = {
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "ROW_NUMBER",
    "RANK",
    "DENSE_RANK",
    "NTILE",
    "LOWER",
    "TRIM",
    "RANDOM",
    "RAND",
    "NULLIF",
    "EXTRACT",
    "COALESCE",
}

CALCULATED_ALIASES = {
    "population",
    "percentage",
    "rank_position",
    "count",
    "total",
    "average_age",
    "average",
}


def validate_sql(sql: str, grounding):
    """Validate a generated SELECT with SQLGlot before database execution."""

    parsed_result = parse_sql(sql)
    if not parsed_result["valid"]:
        return {"valid": False, "reason": parsed_result["error"]}

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as error:
        return {"valid": False, "reason": f"SQL parsing failed: {error}"}

    # Multiple statements and every non-SELECT statement are rejected before
    # AST detail checks, so write/DDL text cannot reach PostgreSQL.
    if len(statements) != 1 or statements[0] is None:
        return {
            "valid": False,
            "reason": "Multiple SQL statements are not allowed.",
        }

    tree = statements[0]
    if not isinstance(tree, exp.Select):
        return {"valid": False, "reason": "Only SELECT queries are allowed."}

    if (
        tree.args.get("with") is not None
        or tree.args.get("with_") is not None
        or tree.find(exp.CTE) is not None
    ):
        return {"valid": False, "reason": "CTEs are not allowed."}
    if tree.find(exp.Subquery):
        return {"valid": False, "reason": "Subqueries are not allowed."}
    if tree.find(exp.SetOperation):
        return {"valid": False, "reason": "Set operations are not allowed."}
    if tree.args.get("into") is not None:
        return {"valid": False, "reason": "SELECT INTO is not allowed."}
    if tree.args.get("locks"):
        return {
            "valid": False,
            "reason": "SQL locking clauses are not allowed.",
        }

    # Reject wildcard projections, but COUNT(*) is a supported aggregate.
    for projection in tree.expressions:
        if isinstance(projection, exp.Star) or isinstance(
            projection,
            exp.Column,
        ) and isinstance(projection.this, exp.Star):
            return {
                "valid": False,
                "reason": "Wildcard or table wildcard SELECT is not allowed.",
            }

    # Validate every function against an explicit allowlist. Argument shape is
    # checked by node-specific rules below.
    for function in tree.find_all(exp.Func):
        function_name = function.sql_name().upper()
        if function_name in {"AND", "OR"}:
            continue
        if function_name not in ALLOWED_FUNCTIONS:
            return {
                "valid": False,
                "reason": f"Unauthorized SQL function: {function_name}",
            }

    # NTILE arguments must be literal integers, never expressions or parameters.
    # PostgreSQL constructs window rank functions as exp.Func; reject NTILE
    # calls without a literal bucket count by checking their SQL text.
    for function in tree.find_all(exp.Func):
        if function.sql_name().upper() == "NTILE":
            bucket_node = (
                function.args.get("this")
                if hasattr(function, "args")
                else None
            )
            if not isinstance(bucket_node, exp.Literal):
                bucket_node = (
                    function.expressions[0]
                    if getattr(function, "expressions", None)
                    else None
                )
            if not isinstance(bucket_node, exp.Literal):
                return {
                    "valid": False,
                    "reason": "NTILE requires a literal bucket count.",
                }
            buckets = bucket_node.to_py()
            if not isinstance(buckets, int) or not 2 <= buckets <= 100:
                return {
                    "valid": False,
                    "reason": "NTILE bucket count is outside the approved range.",
                }

    # Validate table identifiers. Aliases are rejected so a column cannot be
    # disguised behind an unapproved table alias.
    table_nodes = list(tree.find_all(exp.Table))
    actual_tables: set[str] = set()
    for table in table_nodes:
        if table.db or table.catalog:
            return {
                "valid": False,
                "reason": "Schema-qualified tables are not allowed.",
            }
        if table.alias:
            return {
                "valid": False,
                "reason": "Table aliases are not allowed.",
            }
        if table.name not in ALLOWED_TABLES:
            return {
                "valid": False,
                "reason": f"Unauthorized table: {table.name}",
            }
        actual_tables.add(table.name)

    approved_tables = set(grounding.required_tables)
    if not actual_tables.issubset(approved_tables):
        return {
            "valid": False,
            "reason": "SQL uses tables not approved by grounding.",
        }
    if grounding.main_table not in actual_tables:
        return {
            "valid": False,
            "reason": "Main table does not match grounding.",
        }

    approved_column_names = {
        name
        for table in ALLOWED_COLUMNS
        for name in ALLOWED_COLUMNS[table]
    }

    # Every real column reference must be qualified, belong to an approved table,
    # and name an approved column. Unqualified names are accepted only for
    # generated calculated aliases, never for arbitrary SQL expressions.
    for column in tree.find_all(exp.Column):
        if not column.table:
            if column.name not in CALCULATED_ALIASES:
                return {
                    "valid": False,
                    "reason": f"Unapproved unqualified column: {column.name}",
                }
            continue
        if column.table not in ALLOWED_TABLES:
            return {
                "valid": False,
                "reason": f"Unauthorized table: {column.table}",
            }
        if column.name not in ALLOWED_COLUMNS[column.table]:
            return {
                "valid": False,
                "reason": f"Unauthorized column: {column.table}.{column.name}",
            }

    # Validate joins are exact approved relationships, not merely approved tables.
    actual_joins: set[tuple[str, str, str, str]] = set()
    for join in tree.find_all(exp.Join):
        on_condition = join.args.get("on")
        if not isinstance(on_condition, exp.EQ):
            return {
                "valid": False,
                "reason": "JOIN must use one approved equality condition.",
            }
        left = on_condition.this
        right = on_condition.expression
        if not (
            isinstance(left, exp.Column)
            and isinstance(right, exp.Column)
        ):
            return {
                "valid": False,
                "reason": "Invalid JOIN condition.",
            }
        join_key = (left.table, left.name, right.table, right.name)
        reverse_key = (right.table, right.name, left.table, left.name)
        if join_key in ALLOWED_JOINS:
            actual_joins.add(join_key)
        elif reverse_key in ALLOWED_JOINS:
            actual_joins.add(reverse_key)
        else:
            return {
                "valid": False,
                "reason": "Unauthorized JOIN relationship.",
            }

    expected_joins: set[tuple[str, str, str, str]] = set()
    for join in grounding.joins:
        key = (
            join.left_table,
            join.left_column,
            join.right_table,
            join.right_column,
        )
        reverse_key = (
            join.right_table,
            join.right_column,
            join.left_table,
            join.left_column,
        )
        if key in ALLOWED_JOINS:
            expected_joins.add(key)
        elif reverse_key in ALLOWED_JOINS:
            expected_joins.add(reverse_key)
        else:
            return {
                "valid": False,
                "reason": "Grounding contains an unauthorized JOIN.",
            }
    if actual_joins != expected_joins:
        return {
            "valid": False,
            "reason": "SQL JOINs do not match grounding.",
        }

    # Window specifications are validated implicitly by the generated AST:
    # only allowlisted window functions and approved partition/order columns
    # have survived the checks above.
    for window in tree.find_all(exp.Window):
        for partition in window.args.get("partition_by") or []:
            if isinstance(partition, exp.Column):
                if (
                    not partition.table
                    or partition.table not in ALLOWED_TABLES
                    or partition.name not in ALLOWED_COLUMNS[partition.table]
                ):
                    return {
                        "valid": False,
                        "reason": "Unauthorized PARTITION BY column.",
                    }

    # Reject unsupported expression types that could escape the allowlisted
    # function and identifier checks.
    unsupported_types = (
        exp.Command,
        exp.DDL,
        exp.DML,
        exp.Insert,
        exp.Update,
        exp.Delete,
    )
    for unsupported_type in unsupported_types:
        if tree.find(unsupported_type):
            return {
                "valid": False,
                "reason": "Unsupported or write SQL expression detected.",
            }

    return {"valid": True, "reason": "SQL passed validation."}
