
from phase_4.response_generator import generate_response

sample_result = {
    "status": "success",
    "total_records": 3,
    "records": [
        {
            "first_name": "Kiaan",
            "last_name": "Sheth",
            "age": 36,
            "gender": "Male"
        },
        {
            "first_name": "Jack",
            "last_name": "Lall",
            "age": 39,
            "gender": "Male"
        },
        {
            "first_name": "Varsha",
            "last_name": "Balakrishnan",
            "age": 31,
            "gender": "Female"
        }
    ],
    "message": None
}

response = generate_response(sample_result)

print(response)