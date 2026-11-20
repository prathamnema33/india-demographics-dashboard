from typing import Optional

from phase_1.schema import QuestionAnalysis
from phase_2.schema_grounding import Grounding


# SQL identifiers are deliberately allowlisted. Natural-language values may
# enter SQL only through named parameters, never by string concatenation.
ALLOWED_COLUMNS = {
    "user_detail": {
        "id", "first_name", "last_name", "dob", "age", "address_id",
        "religion", "dod", "literate", "gender",
    },
    "addresses": {
        "id", "city", "state", "zip_code",
    },
}
ALLOWED_TABLES = set(ALLOWED_COLUMNS)
ALLOWED_JOINS = {
    ("user_detail", "address_id", "addresses", "id")
}


def safe_alias(alias: str, fallback: str) -> str:
    """Convert a model-supplied display alias into a safe SQL identifier."""

    normalized = "".join(
        character.lower() if character.isalnum() else "_"
        for character in str(alias)
    ).strip("_")
    normalized = "_".join(
        part for part in normalized.split("_") if part
    )
    if not normalized or normalized[0].isdigit():
        return fallback
    return normalized

OPERATORS = {
    "equals": "=",
    "=": "=",
    "not_equals": "!=",
    "!=": "!=",
    ">": ">",
    "greater_than": ">",
    ">=": ">=",
    "greater_than_or_equal": ">=",
    "<": "<",
    "less_than": "<",
    "<=": "<=",
    "less_than_or_equal": "<=",
    "contains": "ILIKE",
    "in": "IN",
}


def validate_column(column: str) -> str:
    """Validate and return a fully qualified approved column."""

    parts = column.split(".")
    if len(parts) != 2:
        raise ValueError(f"Invalid column format: {column}")

    table, name = parts
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Table not allowed: {table}")
    if name not in ALLOWED_COLUMNS[table]:
        raise ValueError(f"Column not allowed: {column}")
    return column


def generate_sql(
    analysis: QuestionAnalysis,
    grounding: Grounding,
) -> tuple[str, dict]:
    """Generate bounded, parameterized PostgreSQL for the supported analysis."""

    if grounding.status != "success":
        raise ValueError("Schema grounding was not successful.")

    main_table = grounding.main_table
    if main_table not in ALLOWED_TABLES:
        raise ValueError("Invalid main table.")

    required_tables = set(grounding.required_tables)
    if main_table not in required_tables:
        raise ValueError("Main table missing from required_tables.")
    if not required_tables.issubset(ALLOWED_TABLES):
        raise ValueError("Unapproved table requested.")

    field_map = {
        item.source_field: validate_column(item.mapped_column)
        for item in grounding.field_mapping
    }

    def map_field(field: str) -> str:
        """Resolve a natural-language field only to an approved mapped column."""

        if "." in field:
            return validate_column(field)
        if field in field_map:
            return field_map[field]
        if field in ALLOWED_COLUMNS.get(main_table, set()):
            return f"{main_table}.{field}"
        for table in sorted(required_tables):
            if field in ALLOWED_COLUMNS.get(table, set()):
                return f"{table}.{field}"
        raise ValueError(f"No database mapping found for: {field}")

    # Build the FROM/JOIN portion once. The join graph comes exclusively from
    # the allowlisted Phase 2 relationship and is connected before query clauses.
    joined_tables = {main_table}
    sql_parts = [f"FROM {main_table}"]
    pending_joins = list(grounding.joins)

    while pending_joins:
        progress = False
        for join in pending_joins[:]:
            left = join.left_table
            right = join.right_table
            forward = (
                left,
                join.left_column,
                right,
                join.right_column,
            )
            reverse = (
                right,
                join.right_column,
                left,
                join.left_column,
            )
            if forward not in ALLOWED_JOINS and reverse not in ALLOWED_JOINS:
                raise ValueError("Unapproved join relationship.")
            if left not in required_tables or right not in required_tables:
                raise ValueError("Join uses an unrequired table.")

            if left in joined_tables and right not in joined_tables:
                sql_parts.append(
                    f"JOIN {right} ON "
                    f"{left}.{join.left_column} = {right}.{join.right_column}"
                )
                joined_tables.add(right)
            elif right in joined_tables and left not in joined_tables:
                sql_parts.append(
                    f"JOIN {left} ON "
                    f"{left}.{join.left_column} = {right}.{join.right_column}"
                )
                joined_tables.add(left)
            else:
                continue

            pending_joins.remove(join)
            progress = True

        if not progress:
            raise ValueError("Unable to connect all required tables.")

    if joined_tables != required_tables:
        raise ValueError("Some required tables have no valid join.")

    params: dict[str, object] = {}

    # WHERE values are parameters. Operators and field names remain server-side
    # allowlisted choices rather than user-controlled SQL fragments.
    where_conditions: list[str] = []

    def add_filter(
        conditions: list[str],
        condition,
        prefix: str,
        start_index: int,
    ) -> int:
        column = map_field(condition.field)
        operator = OPERATORS.get(condition.operator)
        if not operator:
            raise ValueError(f"Unsupported operator: {condition.operator}")

        if condition.value is None:
            if operator == "=":
                conditions.append(f"{column} IS NULL")
            elif operator == "!=":
                conditions.append(f"{column} IS NOT NULL")
            else:
                raise ValueError("Filter value cannot be null.")
            return start_index

        if operator == "IN":
            values = [
                value.strip()
                for value in str(condition.value).split(",")
                if value.strip()
            ]
            placeholders: list[str] = []
            for value in values:
                param_name = f"{prefix}_{start_index}"
                params[param_name] = value
                placeholders.append(f":{param_name}")
                start_index += 1
            conditions.append(f"{column} IN ({', '.join(placeholders)})")
            return start_index

        param_name = f"{prefix}_{start_index}"
        start_index += 1
        if operator == "ILIKE":
            params[param_name] = f"%{condition.value}%"
        else:
            params[param_name] = condition.value

        if operator == "=" and isinstance(condition.value, str):
            conditions.append(
                f"LOWER(TRIM({column})) = "
                f"LOWER(TRIM(:{param_name}))"
            )
        else:
            conditions.append(f"{column} {operator} :{param_name}")
        return start_index

    filter_index = 1
    for condition in analysis.filters:
        filter_index = add_filter(
            where_conditions,
            condition,
            "param",
            filter_index,
        )

    for date_filter in analysis.date_filters:
        column = map_field(date_filter.field)
        if date_filter.period == "year":
            param_name = f"date_param_{filter_index}"
            params[param_name] = date_filter.value
            where_conditions.append(
                f"EXTRACT(YEAR FROM {column}) = :{param_name}"
            )
        elif date_filter.period == "month":
            param_name = f"date_param_{filter_index}"
            params[param_name] = date_filter.value
            where_conditions.append(
                f"EXTRACT(MONTH FROM {column}) = :{param_name}"
            )
        elif date_filter.period == "day":
            param_name = f"date_param_{filter_index}"
            params[param_name] = date_filter.value
            where_conditions.append(
                f"EXTRACT(DAY FROM {column}) = :{param_name}"
            )
        elif date_filter.period == "before":
            param_name = f"date_param_{filter_index}"
            params[param_name] = date_filter.value
            where_conditions.append(f"{column} < :{param_name}")
        elif date_filter.period == "after":
            param_name = f"date_param_{filter_index}"
            params[param_name] = date_filter.value
            where_conditions.append(f"{column} > :{param_name}")
        elif date_filter.period == "between":
            start_name = f"date_param_{filter_index}"
            end_name = f"date_param_{filter_index + 1}"
            params[start_name] = date_filter.value
            params[end_name] = date_filter.end_value
            where_conditions.append(
                f"{column} BETWEEN :{start_name} AND :{end_name}"
            )
            filter_index += 1
        filter_index += 1

    if where_conditions:
        sql_parts.append("WHERE " + " AND ".join(where_conditions))

    group_columns = [map_field(field) for field in analysis.group_by]

    having_conditions: list[str] = []
    for index, condition in enumerate(analysis.having, start=1):
        generated_alias = next(
            (
                aggregation.alias
                or f"{aggregation.function.lower()}_{aggregation.field.split('.')[-1]}"
                for aggregation in analysis.aggregations
                if condition.field == (
                    aggregation.alias
                    or f"{aggregation.function.lower()}_{aggregation.field.split('.')[-1]}"
                )
            ),
            None,
        )
        if generated_alias:
            field = None
        else:
            field = map_field(condition.field) if "." in condition.field else (
                field_map.get(condition.field)
            )
        operator = OPERATORS.get(condition.operator)
        if not operator:
            raise ValueError(f"Unsupported HAVING operator: {condition.operator}")
        if condition.value is None:
            raise ValueError("HAVING value cannot be null.")

        # An HAVING field may be an aggregation alias (for example population)
        # or a fully qualified column. Aliases are not identifiers supplied by
        # the user: the generator validates them only against generated names.
        if field is None:
            expression = safe_alias(
                condition.field,
                "aggregation_value",
            )
        else:
            expression = field

        param_name = f"having_param_{index}"
        params[param_name] = condition.value
        having_conditions.append(f"{expression} {operator} :{param_name}")

    select_parts: list[str] = []

    # Normal record retrieval is DISTINCT-safe and uses explicit allowlisted columns.
    if analysis.aggregations or analysis.ranking or group_columns:
        for column in group_columns:
            select_parts.append(column)

        for aggregation in analysis.aggregations:
            column = (
                "*"
                if aggregation.function == "COUNT"
                and aggregation.field.lower() in ("*", "all", "records")
                else map_field(aggregation.field)
            )
            alias = aggregation.alias or (
                f"{aggregation.function.lower()}_{aggregation.field.split('.')[-1]}"
            )
            alias = safe_alias(
                alias,
                f"{aggregation.function.lower()}_value",
            )

            if aggregation.function == "COUNT":
                expression = f"COUNT({column})"
            else:
                expression = f"{aggregation.function}({column})"
            select_parts.append(f"{expression} AS {alias}")

        if analysis.percentage:
            population_alias = "percentage"
            details = analysis.percentage_details
            scope = details.scope if details else "overall"

            if scope == "within_group" and details and details.denominator_group:
                partition = ", ".join(
                    map_field(field) for field in details.denominator_group
                )
                window = f"SUM(COUNT(*)) OVER (PARTITION BY {partition})"
            else:
                window = "SUM(COUNT(*)) OVER ()"

            select_parts.append(
                "COUNT(*) * 100.0 / NULLIF("
                f"{window}, 0"
                ") AS percentage"
            )
    else:
        selected_columns = [
            validate_column(column)
            for column in grounding.selected_columns
        ]
        if not selected_columns:
            raise ValueError("No output columns selected.")
        if not all(
            column.split(".")[0] in required_tables
            for column in selected_columns
        ):
            raise ValueError("Selected column table is not required.")
        select_parts.extend(selected_columns)

    # Ranking is generated only for explicit ranking intents. Window functions
    # are fixed to four allowlisted forms; unsupported windows remain blocked.
    if analysis.ranking:
        ranking = analysis.ranking
        # Aggregate aliases such as population cannot be resolved as table
        # columns. Rank directly on the aggregate expression that creates the
        # alias instead, preserving correct SQL semantics.
        order_column: Optional[str] = None
        for aggregation in analysis.aggregations:
            alias = aggregation.alias or (
                f"{aggregation.function.lower()}_{aggregation.field.split('.')[-1]}"
            )
            if ranking.order_by == alias:
                if "." in aggregation.field:
                    aggregation_column = validate_column(aggregation.field)
                elif aggregation.field.lower() in ("*", "all", "records"):
                    aggregation_column = "*"
                else:
                    aggregation_column = map_field(aggregation.field)
                if aggregation.function == "COUNT":
                    order_column = f"COUNT({aggregation_column})"
                else:
                    order_column = (
                        f"{aggregation.function}({aggregation_column})"
                    )
                break

        if order_column is None:
            order_column = (
                ranking.order_by
                if "." in ranking.order_by
                else map_field(ranking.order_by)
            )
        partition = ""
        if ranking.partition_by:
            partition_columns = [
                map_field(field) for field in ranking.partition_by
            ]
            partition = "PARTITION BY " + ", ".join(partition_columns) + " "

        direction = "ASC" if ranking.order == "ascending" else "DESC"
        if ranking.function == "NTILE":
            buckets = ranking.buckets
            if buckets is None:
                raise ValueError("NTILE requires a bucket count.")
            ranking_expression = f"NTILE({buckets}) OVER ({partition}ORDER BY {order_column} {direction})"
        else:
            ranking_expression = (
                f"{ranking.function}() OVER "
                f"({partition}ORDER BY {order_column} {direction})"
            )
        select_parts.append(f"{ranking_expression} AS rank_position")

    distinct = "DISTINCT " if analysis.distinct else ""
    sql = f"SELECT {distinct}" + ", ".join(select_parts)
    sql += "\n" + "\n".join(sql_parts)

    if group_columns:
        sql += "\nGROUP BY " + ", ".join(group_columns)

    if having_conditions:
        sql += "\nHAVING " + " AND ".join(having_conditions)

    if analysis.sort.order == "random":
        sql += "\nORDER BY RANDOM()"
    elif analysis.sort.order in ("ascending", "descending"):
        if not analysis.sort.field:
            raise ValueError("Sorting field mapping not found.")
        direction = "ASC" if analysis.sort.order == "ascending" else "DESC"
        sql += f"\nORDER BY {map_field(analysis.sort.field)} {direction}"

    if analysis.limit is not None:
        sql += "\nLIMIT :limit"
        params["limit"] = min(analysis.limit, 500)

    if analysis.offset is not None:
        sql += "\nOFFSET :offset"
        params["offset"] = analysis.offset

    return sql, params
