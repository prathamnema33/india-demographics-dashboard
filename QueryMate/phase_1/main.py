
import os
import time
from pathlib import Path
from phase_1.schema import QuestionAnalysis
from phase_1.prompt import SYSTEM_PROMPT
client = None


def get_gemini_client():
    """Initialize Gemini lazily so schema and pipeline tests need no API key."""

    global client
    if client is not None:
        return client

    from dotenv import load_dotenv
    from google import genai

    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Gemini API key not found!")
    client = genai.Client(api_key=api_key)
    return client

# 3. Test Gemini API with automatic retries
def analyze_question(question: str) -> QuestionAnalysis:
    gemini_client = get_gemini_client()
    from google.genai.errors import ServerError

    for attempt in range(3):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=question,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "response_mime_type": "application/json",
                    "response_schema": QuestionAnalysis,
                },
            )
            break
        except ServerError:
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))

    # Validate Gemini's JSON response
    analysis = QuestionAnalysis.model_validate_json(response.text)

    return analysis


if __name__ == "__main__":

    print("===== QueryMate Question Analyzer =====")

    while True:

        question = input("\nAsk QueryMate (or type exit): ")

        if question.lower().strip() == "exit":
            print("QueryMate closed.")
            break

        if not question.strip():
            print("Please enter a question.")
            continue

        try:
            result = analyze_question(question)

            print("\nStructured Analysis:")
            print(result.model_dump_json(indent=2))

        except Exception as e:
            print("\nError:", e)