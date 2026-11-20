
import re

from phase_0.query_corrector import (
    load_location_vocabulary,
    prepare_location_confirmation,
    confirm_location_correction
)

from phase_1.main import analyze_question, client

from phase_2.schema_context import get_schema_context

from phase_2.schema_grounding import find_relevant_tables

from phase_3.sql_generator import generate_sql
from phase_3.query_executor import execute_query
from phase_3.result_processor import process_result

from phase_4.response_generator import generate_response


# --------------------------------------------------
# PHASE 0: LOCATION SPELLING CORRECTION (CLI ONLY)
# --------------------------------------------------

def get_confirmed_question(question, locations):

    pending = prepare_location_confirmation(
        question,
        locations
    )

    if pending["status"] == "no_correction_needed":
        return question

    suggested_question = question

    for item in reversed(pending["suggestions"]):

        suggested_question = (
            suggested_question[:item["start"]]
            + item["suggested"]
            + suggested_question[item["end"]:]
        )

    if pending["status"] == "clarification_required":

        print("\n========== LOCATION CLARIFICATION ==========")

        for item in pending["ambiguous_matches"]:

            print(f"\nUncertain location: {item['original']}")
            print("Possible matches:")

            for index, candidate in enumerate(
                item["candidates"],
                start=1
            ):
                print(
                    f"{index}. {candidate['name']} "
                    f"({candidate['type']}) "
                    f"- Score: {candidate['confidence']}"
                )

            while True:

                choice = input(
                    "\nSelect the correct location number "
                    "(or 0 to cancel): "
                ).strip()

                if choice == "0":
                    return None

                if choice.isdigit():

                    choice = int(choice)

                    if 1 <= choice <= len(item["candidates"]):

                        selected = item["candidates"][choice - 1]

                        suggested_question = re.sub(
                            re.escape(item["original"]),
                            selected["name"],
                            suggested_question,
                            count=1,
                            flags=re.IGNORECASE
                        )

                        break

                print("Invalid selection. Try again.")

    if suggested_question == question:
        return question

    print("\nOriginal question:", question)
    print("Suggested question:", suggested_question)

    confirmation = {
        "original_question": question,
        "suggested_question": suggested_question
    }

    while True:

        answer = input(
            "\nWould you like to correct the spelling? (Yes/No): "
        )

        result = confirm_location_correction(
            confirmation,
            answer
        )

        if result["status"] == "invalid_answer":
            print(result["message"])
            continue

        if result["status"] in ("corrected", "rejected"):
            return result["question"]


# --------------------------------------------------
# MAIN QUERYMATE PIPELINE (API + CLI COMPATIBLE)
# --------------------------------------------------

def run_querymate(question, page=1, page_size=50):

    try:

        question = question.strip()

        if not question:
            return {
                "status": "error",
                "message": "Please enter a valid question."
            }

        # ==========================================
        # PHASE 1: QUESTION ANALYSIS
        # ==========================================

        analysis = analyze_question(question)

        if analysis.intent == "clarification_required":
            return {
                "status": "clarification_required",
                "message": analysis.clarification_question
            }

        # ==========================================
        # PHASE 2: SCHEMA GROUNDING
        # ==========================================
        # Load only the approved schema context immediately before grounding.
        # This avoids unnecessary metadata inspection for invalid or
        # clarification-only questions.
        filter_schema, relationship_map = get_schema_context()

        grounding = find_relevant_tables(
            question,
            analysis,
            filter_schema,
            relationship_map,
            client
        )

        if grounding.status != "success":
            return {
                "status": grounding.status,
                "message": grounding.clarification_question
            }

        # ==========================================
        # PHASE 3A: SQL GENERATION
        # ==========================================

        sql, params = generate_sql(
            analysis,
            grounding
        )

        # ==========================================
        # PHASE 3B: VALIDATION + EXECUTION
        # ==========================================

        execution_result = execute_query(
            sql,
            params,
            grounding,
            page=page,
            page_size=page_size,
        )

        # ==========================================
        # PHASE 3C: RESULT PROCESSING
        # ==========================================

        final_result = process_result(
            execution_result
        )

        # ==========================================
        # PHASE 4: RESPONSE GENERATION
        # ==========================================

        response = generate_response(final_result)

        return {
            "status": final_result["status"],
            "message": response,
            "total_records": final_result["total_records"],
            "fetched_records": final_result["fetched_records"],
            "page": final_result.get("page", page),
            "page_size": final_result.get("page_size", page_size),
            "has_more": final_result.get("has_more", False),
            "records": final_result["records"]
        }

    except ValueError as error:

        print("QUERYMATE VALIDATION ERROR:", repr(error))

        return {
            "status": "error",
            "message": "I couldn't process this request."
        }

    except Exception as error:

        print("QUERYMATE INTERNAL ERROR:", repr(error))

        return {
            "status": "error",
            "message": "Something went wrong while processing your request."
        }


# --------------------------------------------------
# APPLICATION ENTRY POINT (CLI ONLY)
# --------------------------------------------------

if __name__ == "__main__":

    print("======= QueryMate =======")

    try:

        print("\nLoading geographical vocabulary...")

        locations = load_location_vocabulary()

        print(
            f"Loaded {len(locations)} geographical locations."
        )

        question = input("\nAsk QueryMate: ").strip()

        if not question:
            print("Please enter a valid question.")

        else:

            confirmed_question = get_confirmed_question(
                question,
                locations
            )

            if confirmed_question is None:
                print("\nQueryMate stopped.")

            else:

                result = run_querymate(confirmed_question)

                print("\n======= QueryMate Response =======")
                print(result["message"])

    except Exception as error:

        print("\nQueryMate initialization failed.")
        print("INTERNAL ERROR:", repr(error))
