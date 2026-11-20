from phase_1.main import analyze_question
from main import run_querymate
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid
import re
from phase_0.query_corrector import (
    prepare_location_confirmation,
    load_location_vocabulary
)

locations = load_location_vocabulary()
sessions = {}
app = FastAPI()


# Request models
class ReplyRequest(BaseModel):
    reply: str


class QuestionRequest(BaseModel):
    question: str|None=None
    reply: str|None=None
    page: int = 1
    page_size: int = 50



# Reusable session validation
def get_valid_session(session_id):
    session_data = sessions.get(session_id)

    if session_data is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    return session_data


@app.get("/")
def home():
    return {
        "message": "QueryMate API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "Healthy"
    }


@app.get("/create-session")
def create_session():
    session_id = str(uuid.uuid4())

    sessions[session_id] = {
        "question": None,
        "pending_state": None,
        "pending_data": None
    }

    return {
        "session_id": session_id,
        "status": "Session created"
    }


def run_session_query(session_data, question, page=1, page_size=50):
    """Run the central pipeline and retain context for a clarification reply."""

    result = run_querymate(
        question,
        page=page,
        page_size=page_size,
    )
    if result.get("status") == "clarification_required":
        session_data["pending_state"] = "query_clarification"
        session_data["pending_data"] = {"question": question}
    else:
        session_data["pending_state"] = None
        session_data["pending_data"] = None
    return result


@app.get("/session/{session_id}")
def get_session(session_id):
    return get_valid_session(session_id)


@app.post("/ask")
def ask_question(request: QuestionRequest):
    return {
        "received_question": request.question,
        "status": "Question received successfully"
    }



@app.post("/ask/{session_id}")
def ask_session(session_id, request: QuestionRequest):

    session_data = get_valid_session(session_id)

    # Preserve the original request when Phase 1 asks for more detail, then
    # feed the answer back through the same QueryMate pipeline on this session.
    if session_data["pending_state"] == "query_clarification":
        if not request.reply or not request.reply.strip():
            raise HTTPException(
                status_code=400,
                detail="Please answer the clarification question.",
            )
        question = (
            f"{session_data['pending_data']['question']}\n"
            f"The user clarified: {request.reply.strip()}"
        )
        return run_session_query(
            session_data,
            question,
            page=request.page,
            page_size=request.page_size,
        )

    # 1. Handle pending spelling confirmation first.
    if session_data["pending_state"] == "confirmation_required":

        if not request.reply:
            raise HTTPException(
                status_code=400,
                detail="Please provide Yes or No."
            )

        answer = request.reply.strip().lower()

        if answer in ("yes", "y"):
            question = session_data["pending_data"]["suggested_question"]

        elif answer in ("no", "n"):
            question = session_data["pending_data"]["original_question"]

        else:
            raise HTTPException(
                status_code=400,
                detail="Please answer Yes or No."
            )

        session_data["question"] = question
        return run_session_query(
            session_data,
            question,
            page=request.page,
            page_size=request.page_size,
        )

    # 1B. Handle an ambiguous location selection. The choice is local to
    # Phase 0 and is not sent as database SQL or as an unconstrained filter.
    if session_data["pending_state"] == "clarification_required":
        if not request.reply:
            raise HTTPException(
                status_code=400,
                detail="Please select a location number.",
            )

        pending = session_data["pending_data"]
        choices = pending["choices"]
        reply = request.reply.strip()
        if reply not in choices:
            raise HTTPException(
                status_code=400,
                detail="Please choose one of the listed location numbers.",
            )

        question = re.sub(
            re.escape(pending["ambiguous_location"]),
            choices[reply],
            pending["original_question"],
            count=1,
            flags=re.IGNORECASE,
        )
        session_data["question"] = question
        return run_session_query(
            session_data,
            question,
            page=request.page,
            page_size=request.page_size,
        )

    # 2. Handle a new question
    question = (request.question or "").strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty"
        )

    # 3. Continue with your existing Phase 0 logic here

    pending = prepare_location_confirmation(
        question,
        locations
    )
    print("PHASE 0 OUTPUT:", pending)

    # Case 1: Ambiguous location
    if pending["status"] == "clarification_required":

        ambiguous = pending["ambiguous_matches"][0]

        choices = {
            str(index): candidate["name"]
            for index, candidate in enumerate(
                ambiguous["candidates"],
                start=1
            )
        }

        session_data["pending_state"] = "clarification_required"

        session_data["pending_data"] = {
            "original_question": pending["original_question"],
            "ambiguous_location": ambiguous["original"],
            "choices": choices
        }

        return {
            "status": "clarification_required",
            "message": f"Which location did you mean: {ambiguous['original']}?",
            "options": [
                {
                    "number": number,
                    "location": location
                }
                for number, location in choices.items()
            ]
        }

    # Case 2: Spelling correction
    elif pending["status"] == "confirmation_required":

        session_data["pending_state"] = "confirmation_required"

        session_data["pending_data"] = {
            "original_question": pending["original_question"],
            "suggested_question": pending["suggested_question"]
        }

        return {
            "status": "confirmation_required",
            "message": pending["confirmation_question"]
        }

    # Case 3: No correction required
    elif pending["status"] == "no_correction_needed":
        session_data["question"] = question
        return run_session_query(
            session_data,
            question,
            page=request.page,
            page_size=request.page_size,
        )

    # Case 4: Unknown location
    elif pending["status"] == "location_not_found":

        return {
            "status": "location_not_found",
            "message": "I couldn't identify that location. Please check the spelling and try again.",
            "locations": pending["not_found_locations"]
        }

    return {
        "status": "error",
        "message": f"Unexpected status: {pending['status']}"
    }
