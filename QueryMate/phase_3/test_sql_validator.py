from phase_3.sql_validator import validate_sql
from phase_2.schema_grounding import Grounding

grounding = Grounding(
    main_table="user_detail",
    required_tables=["user_detail", "addresses"],
    selected_columns=[
        "user_detail.first_name",
        "user_detail.last_name",
        "user_detail.age",
        "user_detail.gender"
    ],
    field_mapping=[],
    joins=[
        {
            "left_table": "user_detail",
            "left_column": "address_id",
            "right_table": "addresses",
            "right_column": "id"
        }
    ],
    status="success"
)
valid_sql = """
SELECT
    user_detail.first_name,
    user_detail.last_name,
    user_detail.age,
    user_detail.gender
FROM user_detail
JOIN addresses
    ON user_detail.address_id = addresses.id
WHERE addresses.state = :state
AND user_detail.gender = :gender
LIMIT :limit
"""
delete_sql = """
DELETE FROM user_detail
WHERE id = 10
"""
unauthorized_table_sql = """
SELECT user_credential.password_hash
FROM user_credential
"""
unauthorized_column_sql = """
SELECT user_detail.password
FROM user_detail
"""

unauthorized_join_sql = """
SELECT user_detail.first_name
FROM user_detail
JOIN user_credential
    ON user_detail.id = user_credential.user_id
"""
subquery_sql = """
SELECT user_detail.first_name,
       user_detail.last_name,
       user_detail.age,
       user_detail.gender
FROM user_detail
WHERE user_detail.id IN (
    SELECT user_detail.id
    FROM user_detail
)
"""
unexpected_function_sql = """
SELECT
    user_detail.first_name,
    user_detail.last_name,
    user_detail.age,
    user_detail.gender,
    PG_SLEEP(5)
FROM user_detail
"""
multiple_statements_sql = """
SELECT user_detail.first_name
FROM user_detail;

DELETE FROM user_detail
WHERE id = 10;
"""
tests = {
    "Valid SELECT": valid_sql,
    "DELETE query": delete_sql,
    "Unauthorized table": unauthorized_table_sql,
    "Unauthorized column": unauthorized_column_sql,
    "Multiple statements": multiple_statements_sql,
    "Unauthorized JOIN": unauthorized_join_sql,
"Subquery": subquery_sql,
"Unexpected function": unexpected_function_sql
}

for test_name, query in tests.items():
    result = validate_sql(query, grounding)

    print(f"\n{test_name}")
    print("-" * 40)
    print(result)