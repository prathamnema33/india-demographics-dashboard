from phase_3.sql_generator import generate_sql
from phase_3.query_executor import execute_query
from phase_1.schema import QuestionAnalysis
from phase_2.schema_grounding import Grounding


analysis = QuestionAnalysis(
    intent="retrieve_records",
    entity=["users"],
    filters=[],
    limit=5
)

grounding = Grounding(
    main_table="user_detail",
    required_tables=["user_detail"],
    selected_columns=[
        "user_detail.first_name",
        "user_detail.last_name",
        "user_detail.age",
        "user_detail.gender"
    ],
    field_mapping=[],
    joins=[],
    status="success"
)


# Generate SQL
sql, params = generate_sql(analysis, grounding)

print("Generated SQL:", sql)
print("Parameters:", params)


# Execute SQL
result = execute_query(sql, params, grounding)

print("\nExecution Result:")
print(result)
