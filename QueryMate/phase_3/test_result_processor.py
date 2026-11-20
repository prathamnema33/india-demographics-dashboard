from phase_3.result_processor import process_result

sample_result = {
    "success": False,
    "count": 3,
    "data": [
    ]
}

result = process_result(sample_result)

print(result)
