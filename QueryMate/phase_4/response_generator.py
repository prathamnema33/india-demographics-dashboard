
def generate_response(processed_result, max_display=10):

    # Validate display limit
    if not isinstance(max_display, int) or max_display < 1:
        max_display = 10

    status = processed_result.get("status")

    # Case 1: Query failed
    if status == "error":
        return (
            "Sorry, I couldn't retrieve the requested information."
        )

    # Case 2: No records found
    if status == "empty":
        return (
            "No matching records were found in the database."
        )

    records = processed_result.get("records", [])
    total_records = processed_result.get("total_records", 0)

    # Case 3: No records available
    if not records:
        return "No matching records were found."

    response = [
        f"I found {total_records} matching records."
    ]

    # Display only limited records
    display_records = records[:max_display]

    # Display records in a compact table. Keep aliases intact so percentage
    # precision and ranking positions remain visible to the user.
    keys = list(display_records[0].keys())
    headers = [key.replace("_", " ").title() for key in keys]
    response.append("\n| " + " | ".join(headers) + " |")
    response.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for record in display_records:
        values = []
        for key in keys:
            value = record.get(key)
            if value is None:
                value = "Not available"
            else:
                value = str(value)
                if len(value) > 100:
                    value = value[:97] + "..."
            values.append(value)
        response.append("| " + " | ".join(values) + " |")

    page = processed_result.get("page")
    if page:
        response.append(f"\nPage {page}.")

    # Show remaining record count
    if total_records > len(display_records):
        response.append(
            f"\nShowing {len(display_records)} of {total_records} records."
        )

    return "\n".join(response)
