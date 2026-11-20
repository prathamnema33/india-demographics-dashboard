
def process_result(execution_result):

    # 1. Validate execution result
    if not isinstance(execution_result, dict):
        return {
            "status": "error",
            "total_records": 0,
            "fetched_records": 0,
            "records": [],
            "page": 1,
            "page_size": 0,
            "has_more": False,
            "message": "Invalid query execution result."
        }

    # 2. Handle execution failure
    if not execution_result.get("success"):
        return {
            "status": "error",
            "total_records": 0,
            "fetched_records": 0,
            "records": [],
            "page": execution_result.get("page", 1),
            "page_size": execution_result.get("page_size", 0),
            "has_more": execution_result.get("has_more", False),
            "message": execution_result.get(
                "error", "Query execution failed."
            )
        }

    # 3. Extract records
    records = execution_result.get("data", [])

    if not isinstance(records, list):
        return {
            "status": "error",
            "total_records": 0,
            "fetched_records": 0,
            "records": [],
            "page": 1,
            "page_size": 0,
            "has_more": False,
            "message": "Invalid records format."
        }

    total_records = execution_result.get(
        "count", len(records)
    )

    # 4. Handle empty results
    if total_records == 0:
        return {
            "status": "empty",
            "total_records": 0,
            "fetched_records": 0,
            "records": [],
            "page": execution_result.get("page", 1),
            "page_size": execution_result.get("page_size", 0),
            "has_more": False,
            "message": "No matching records found."
        }

    # 5. Successful result
    return {
        "status": "success",
        "total_records": total_records,
        "fetched_records": len(records),
        "records": records,
        "page": execution_result.get("page", 1),
        "page_size": execution_result.get("page_size", len(records)),
        "offset": execution_result.get("offset", 0),
        "has_more": execution_result.get("has_more", False),
        "message": None
    }
