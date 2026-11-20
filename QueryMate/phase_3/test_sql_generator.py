
from phase_1.schema import QuestionAnalysis
from phase_2.schema_grounding import Grounding
from phase_3.sql_generator import generate_sql


analysis = QuestionAnalysis.model_validate({
    "intent": "retrieve_records",
    "entity": ["users"],
    "filters": [
        {
            "field": "state",
            "operator": "equals",
            "value": "Karnataka"
        },
        {
            "field": "gender",
            "operator": "equals",
            "value": "male"
        }
    ],
    "sort": {
        "field": None,
        "order": "random"
    },
    "limit": 10,
    "clarification_question": None
})


grounding = Grounding.model_validate({
    "main_table": "user_detail",
    "required_tables": [
        "user_detail",
        "addresses"
    ],
    "selected_columns": [
        "user_detail.first_name",
        "user_detail.last_name",
        "user_detail.age",
        "user_detail.gender"
    ],
    "field_mapping": [
        {
            "source_field": "state",
            "mapped_column": "addresses.state"
        },
        {
            "source_field": "gender",
            "mapped_column": "user_detail.gender"
        }
    ],
    "joins": [
        {
            "left_table": "user_detail",
            "left_column": "address_id",
            "right_table": "addresses",
            "right_column": "id"
        }
    ],
    "status": "success",
    "clarification_question": None
})


sql, params = generate_sql(analysis, grounding)

print("\nGenerated SQL:")
print(sql)

print("\nParameters:")
print(params)
