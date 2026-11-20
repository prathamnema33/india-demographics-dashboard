
from phase_1.main import analyze_question, client
from phase_2.schema_context import get_schema_context
from phase_2.schema_grounding import find_relevant_tables
from phase_3.sql_generator import generate_sql
from phase_3.query_executor import execute_query

filter_schema, relationship_map = get_schema_context()


def test_executor(question):

    print("\nQuestion:", question)

    # Phase 1: Understand question
    analysis = analyze_question(question)

    # Phase 2: Grounding
    grounding = find_relevant_tables(
        question,
        analysis,
        filter_schema,
        relationship_map,
        client
    )

    if grounding.status != "success":
        print("Grounding failed:", grounding)
        return

    # Phase 3A: Generate SQL
    sql, params = generate_sql(analysis, grounding)

    print("Generated SQL:", sql)

    # Phase 3B: Execute query
    result = execute_query(sql, params, grounding)

    print("\nExecution Result:")
    print("Success:", result["success"])
    print("Total records:", result["count"])
    print("Fetched records:", result["fetched_count"])
    print("Has more:", result.get("has_more"))

    if result["success"]:
        print("First record:", result["data"][:1])
    else:
        print("Error:", result["error"])

    # Resource protection checks
    assert result["success"], "Query execution failed!"
    assert result["fetched_count"] <= 500, "Fetch limit exceeded!"

    print("TEST PASSED!")


if __name__ == "__main__":

    questions = [
        "Show random 10 users",
        "Show all users",
        "Show users from Madhya Pradesh"
    ]

    for question in questions:
        try:
            test_executor(question)
        except Exception as error:
            print("TEST FAILED:", repr(error))
