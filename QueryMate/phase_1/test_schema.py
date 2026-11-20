
from phase_1.schema import QuestionAnalysis

data = {
    "intent": "retrieve_records",
    "entity": "people",
    "filters": {
        "state": "Madhya Pradesh",
        "dod": None
    },
    "sort": {
        "field": "age",
        "order": "descending"
    },
    "limit": 5
}

result = QuestionAnalysis.model_validate(data)

print(result.model_dump())
