
from phase_2.schema_grounding import Grounding, JoinDetails
from phase_3.sql_validator import validate_sql


# ------------------------------------------
# TEST GROUNDING
# ------------------------------------------

basic_grounding = Grounding(
    main_table="user_detail",
    required_tables=["user_detail"],
    selected_columns=["user_detail.id"],
    field_mapping=[],
    joins=[],
    status="success"
)


join_grounding = Grounding(
    main_table="user_detail",
    required_tables=["user_detail", "addresses"],
    selected_columns=["user_detail.id"],
    field_mapping=[],
    joins=[
        JoinDetails(
            left_table="user_detail",
            left_column="address_id",
            right_table="addresses",
            right_column="id"
        )
    ],
    status="success"
)


# ------------------------------------------
# SECURITY TEST CASES
# ------------------------------------------

test_cases = [

    {
        "name": "Valid SELECT",
        "sql": """
            SELECT user_detail.id
            FROM user_detail
        """,
        "grounding": basic_grounding,
        "expected": True
    },

    {
        "name": "Unauthorized Table",
        "sql": """
            SELECT secret_table.id
            FROM secret_table
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Unauthorized Column",
        "sql": """
            SELECT user_detail.password
            FROM user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "DELETE Command",
        "sql": """
            DELETE FROM user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "UPDATE Command",
        "sql": """
            UPDATE user_detail
            SET age = 25
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "DROP Command",
        "sql": """
            DROP TABLE user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Multiple SQL Statements",
        "sql": """
            SELECT user_detail.id FROM user_detail;
            DROP TABLE user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Unauthorized JOIN",
        "sql": """
            SELECT user_detail.id
            FROM user_detail
            JOIN addresses
            ON user_detail.id = addresses.city
        """,
        "grounding": join_grounding,
        "expected": False
    },

    {
        "name": "Valid JOIN",
        "sql": """
            SELECT user_detail.id
            FROM user_detail
            JOIN addresses
            ON user_detail.address_id = addresses.id
        """,
        "grounding": join_grounding,
        "expected": True
    }
]


# ------------------------------------------
# RUN SECURITY TESTS
# ------------------------------------------

if __name__ == "__main__":

    passed = 0
    failed = 0

    print("\n========== QUERYMATE SECURITY TESTS ==========\n")

    for test in test_cases:

        result = validate_sql(
            test["sql"],
            test["grounding"]
        )

        actual = result["valid"]
        expected = test["expected"]

        success = actual == expected

        if success:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        print(f"[{status}] {test['name']}")
        print("Reason:", result["reason"])
        print("-" * 50)

    print("\n========== FINAL REPORT ==========")
    print("Passed:", passed)
    print("Failed:", failed)
    print("Total:", len(test_cases))


# ------------------------------------------
# ADVANCED SECURITY TEST CASES
# ------------------------------------------

advanced_test_cases = [

    {
        "name": "Table Alias",
        "sql": """
            SELECT u.id
            FROM user_detail AS u
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Schema Qualified Table",
        "sql": """
            SELECT user_detail.id
            FROM public.user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Wildcard SELECT",
        "sql": """
            SELECT *
            FROM user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Table Wildcard SELECT",
        "sql": """
            SELECT user_detail.*
            FROM user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Unauthorized PG_SLEEP Function",
        "sql": """
            SELECT PG_SLEEP(10)
            FROM user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Unauthorized NOW Function",
        "sql": """
            SELECT NOW()
            FROM user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "Subquery",
        "sql": """
            SELECT user_detail.id
            FROM user_detail
            WHERE user_detail.id IN (
                SELECT user_detail.id
                FROM user_detail
            )
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "CTE",
        "sql": """
            WITH user_data AS (
                SELECT user_detail.id
                FROM user_detail
            )
            SELECT user_detail.id
            FROM user_detail
        """,
        "grounding": basic_grounding,
        "expected": False
    },

    {
        "name": "FOR UPDATE Lock",
        "sql": """
            SELECT user_detail.id
            FROM user_detail
            FOR UPDATE
        """,
        "grounding": basic_grounding,
        "expected": False
    }
]


# ------------------------------------------
# RUN ADVANCED SECURITY TESTS
# ------------------------------------------

def run_advanced_tests():

    passed = 0
    failed = 0

    print("\n========== ADVANCED SECURITY TESTS ==========\n")

    for test in advanced_test_cases:

        try:

            result = validate_sql(
                test["sql"],
                test["grounding"]
            )

            actual = result["valid"]
            expected = test["expected"]

            if actual == expected:
                passed += 1
                status = "PASS"
            else:
                failed += 1
                status = "FAIL"

            print(f"[{status}] {test['name']}")
            print("Expected valid:", expected)
            print("Actual valid:", actual)
            print("Reason:", result["reason"])
            print("-" * 50)

        except Exception as error:

            failed += 1

            print(f"[FAIL] {test['name']}")
            print("Exception:", repr(error))
            print("-" * 50)

    print("\n========== ADVANCED SECURITY REPORT ==========")
    print("Passed:", passed)
    print("Failed:", failed)
    print("Total:", len(advanced_test_cases))
    

# ------------------------------------------
# FUNCTION BYPASS TESTS
# ------------------------------------------

function_test_cases = [

    {
        "name": "Unauthorized VERSION",
        "sql": """
            SELECT VERSION()
            FROM user_detail
        """
    },

    {
        "name": "Unauthorized CURRENT_DATABASE",
        "sql": """
            SELECT CURRENT_DATABASE()
            FROM user_detail
        """
    },

    {
        "name": "Unauthorized GENERATE_SERIES",
        "sql": """
            SELECT GENERATE_SERIES(1, 10)
            FROM user_detail
        """
    },

    {
        "name": "Unauthorized PG_READ_FILE",
        "sql": """
            SELECT PG_READ_FILE('/etc/passwd')
            FROM user_detail
        """
    },

    {
        "name": "Unauthorized CURRENT_TIMESTAMP",
        "sql": """
            SELECT CURRENT_TIMESTAMP
            FROM user_detail
        """
    }
]


def run_function_tests():

    print("\n========== FUNCTION BYPASS TESTS ==========\n")

    passed = 0
    failed = 0

    for test in function_test_cases:

        try:

            result = validate_sql(
                test["sql"],
                basic_grounding
            )

            if not result["valid"]:
                passed += 1
                print(f"[PASS] {test['name']}")

            else:
                failed += 1
                print(f"[FAIL] {test['name']}")

            print("Reason:", result["reason"])
            print("-" * 50)

        except Exception as error:

            failed += 1
            print(f"[ERROR] {test['name']}")
            print(repr(error))

    print("\n========== FUNCTION TEST REPORT ==========")
    print("Passed:", passed)
    print("Failed:", failed)
    print("Total:", len(function_test_cases))


if __name__ == "__main__":
    run_function_tests()

