from phase_1.schema import QuestionAnalysis
from phase_2.ground_prompt import GROUNDING_PROMPT
import time
from typing import Optional, Literal
from pydantic import BaseModel, Field
import json

class FieldMapping(BaseModel):
    source_field: str
    mapped_column: str
class JoinDetails(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str


class Grounding(BaseModel):
    main_table: Optional[str] = None

    required_tables: list[str] = Field(default_factory=list)

    # Columns that should appear in the final output
    selected_columns: list[str] = Field(default_factory=list)

    # Mapping of filters and sorting fields
    field_mapping: list[FieldMapping] = Field(default_factory=list)

    joins: list[JoinDetails] = Field(default_factory=list)

    # Analytical field categories preserve which Phase 1 concepts were grounded.
    aggregation_fields: list[str] = Field(default_factory=list)
    grouping_fields: list[str] = Field(default_factory=list)
    ranking_fields: list[str] = Field(default_factory=list)
    partition_fields: list[str] = Field(default_factory=list)
    filtering_fields: list[str] = Field(default_factory=list)
    sorting_fields: list[str] = Field(default_factory=list)
    date_fields: list[str] = Field(default_factory=list)

    status: Literal[
        "success",
        "clarification_required",
        "not_found"
    ]

    clarification_question: Optional[str] = None


ALLOWED_TABLES = {"user_detail", "addresses"}
ALLOWED_COLUMNS = {
    "user_detail": {
        "id", "first_name", "last_name", "dob", "age", "address_id",
        "religion", "dod", "literate", "gender",
    },
    "addresses": {"id", "city", "state", "zip_code"},
}
ALLOWED_JOINS = {
    ("user_detail", "address_id", "addresses", "id")
}


def validate_grounding(grounding: Grounding) -> tuple[bool, str]:
    """Validate grounded identifiers locally before SQL generation."""

    if grounding.status != "success":
        return True, "Grounding requires clarification or is not found."

    if grounding.main_table not in ALLOWED_TABLES:
        return False, f"Unauthorized main table: {grounding.main_table}"

    if grounding.main_table not in grounding.required_tables:
        return False, "Main table must be included in required_tables."

    if not set(grounding.required_tables).issubset(ALLOWED_TABLES):
        return False, "Unauthorized table: Grounding requested a prohibited table."

    def validate_qualified_column(column: str) -> bool:
        parts = column.split(".")
        if len(parts) != 2:
            return False
        table, name = parts
        return table in ALLOWED_COLUMNS and name in ALLOWED_COLUMNS[table]

    for column in grounding.selected_columns:
        if not validate_qualified_column(column):
            return False, f"Unauthorized selected column: {column}"

    analytical_columns = (
        grounding.aggregation_fields
        + grounding.grouping_fields
        + grounding.ranking_fields
        + grounding.partition_fields
        + grounding.filtering_fields
        + grounding.sorting_fields
        + grounding.date_fields
    )

    for column in analytical_columns:
        if not validate_qualified_column(column):
            return False, f"Unauthorized analytical column: {column}"

    for mapping in grounding.field_mapping:
        if not validate_qualified_column(mapping.mapped_column):
            return False, f"Unauthorized field mapping: {mapping.mapped_column}"

    for join in grounding.joins:
        join_key = (
            join.left_table,
            join.left_column,
            join.right_table,
            join.right_column,
        )
        reverse_key = (
            join.right_table,
            join.right_column,
            join.left_table,
            join.left_column,
        )
        if join_key not in ALLOWED_JOINS and reverse_key not in ALLOWED_JOINS:
            return False, "Grounding contains an unauthorized join."

    return True, "Grounding passed validation."
    
def find_relevant_tables(
    question: str,
    question_analysis: QuestionAnalysis,
    filter_schema: dict,
    relationship_map: list,
    client
):
    if client is None:
        # Some callers pass the old module-level client symbol. Resolve it
        # lazily here so schema grounding never receives a None Gemini client.
        from phase_1.main import get_gemini_client
        client = get_gemini_client()

    # Import Gemini only when a live grounding call is made. Tests and the
    # deterministic allowlist validator do not require API credentials.
    from google.genai.errors import ServerError

    grounding_input = {
        "original_question": question,
        "question_analysis": question_analysis.model_dump(),
        "schema_context": filter_schema,
        "relationship_map": relationship_map,
        
    }
    payload = json.dumps(grounding_input, default=str)

    print("Payload size:", len(payload), "characters")

    for attempt in range(3):
        try:
            response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=json.dumps(grounding_input, default=str),
            config={
                "system_instruction": GROUNDING_PROMPT,
                "response_mime_type": "application/json",
                "response_schema": Grounding,
            },
        )

            result = Grounding.model_validate_json(response.text)
            valid, reason = validate_grounding(result)
            if not valid:
                return Grounding(
                    status="not_found",
                    clarification_question=reason,
                )
            return result

        except ServerError as error:
            if attempt == 2:
                raise

            print(f"Gemini server busy. Retrying... ({attempt + 1}/3)")
            time.sleep(2 ** (attempt + 1))

    return result