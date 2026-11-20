
from phase_1.main import analyze_question, client

from phase_2.schema_context import get_schema_context
from phase_2.schema_grounding import find_relevant_tables

from phase_3.sql_generator import generate_sql
from phase_3.sql_validator import validate_sql
from phase_3.query_executor import execute_query
from phase_3.result_processor import process_result


# Load approved schema and relationships
filter_schema, relationship_map = get_schema_context()


def test_phase_3(question):

    print("\n" + "=" * 50)
    print("QUESTION:", question)
    print("=" * 50)

    # ==========================================
    # PHASE 1: QUESTION ANALYSIS
    # ==========================================

    print("\n--- PHASE 1: ANALYSIS ---")

    analysis = analyze_question(question)

    print(analysis.model_dump_json(indent=2))

    if analysis.intent != "retrieve_records":
        print("Cannot proceed: Intent requires clarification.")
        return

    # ==========================================
    # PHASE 2: SCHEMA GROUNDING
    # ==========================================

    print("\n--- PHASE 2: GROUNDING ---")

    grounding = find_relevant_tables(
        question,
        analysis,
        filter_schema,
        relationship_map,
        client
    )

    print(grounding.model_dump_json(indent=2))

    if grounding.status != "success":
        print("Grounding unsuccessful.")
        return

    # ==========================================
    # PHASE 3A: SQL GENERATION
    # ==========================================

    print("\n--- PHASE 3A: SQL GENERATION ---")

    sql, params = generate_sql(
        analysis,
        grounding
    )

    print("Generated SQL:\n", sql)
    print("Parameters:", params)

    # ==========================================
    # PHASE 3B: SQL VALIDATION
    # ==========================================

    print("\n--- PHASE 3B: SQL VALIDATION ---")

    validation = validate_sql(
        sql,
        grounding
    )

    print("Validation:", validation)

    if not validation["valid"]:
        print("SQL validation failed.")
        return

    # ==========================================
    # PHASE 3C: QUERY EXECUTION
    # ==========================================

    print("\n--- PHASE 3C: QUERY EXECUTION ---")

    execution_result = execute_query(
        sql,
        params,
        grounding
    )

    print("Execution Result:", execution_result)

    if not execution_result.get("success"):
        print("Query execution failed.")
        return

    # ==========================================
    # PHASE 3D: RESULT PROCESSING
    # ==========================================

    print("\n--- PHASE 3D: RESULT PROCESSING ---")

    final_result = process_result(
        execution_result
    )

    print("Processed Result:", final_result)

    print("\nPHASE 3 TEST PASSED!")


# ==========================================
# APPLICATION ENTRY POINT
# ==========================================

if __name__ == "__main__":

    questions = [
        "Show all users",
        "Show users from Madhya Pradesh",
        "Show users with their city",
        "Show random 10 users"
    ]

    for question in questions:

        try:
            test_phase_3(question)

        except Exception as error:
            print("\nTEST FAILED:", repr(error))
