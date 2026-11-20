
import re

from sqlalchemy import text
from phase_2.database import engine
from rapidfuzz import process, fuzz


# --------------------------------------------------
# STEP 1: LOAD STATE AND DISTRICT VOCABULARY
# --------------------------------------------------

def load_location_vocabulary():

    query = """
        SELECT DISTINCT
            UPPER(TRIM(state_name)) AS location,
            'state' AS location_type
        FROM all_india_pincodes
        WHERE state_name IS NOT NULL
          AND TRIM(state_name) != ''

        UNION

        SELECT DISTINCT
            UPPER(TRIM(district)) AS location,
            'district' AS location_type
        FROM all_india_pincodes
        WHERE district IS NOT NULL
          AND TRIM(district) != ''
    """

    with engine.connect() as connection:
        rows = connection.execute(text(query)).fetchall()

    vocabulary = [
        {
            "name": row.location,
            "type": row.location_type
        }
        for row in rows
    ]

    return vocabulary


# --------------------------------------------------
# STEP 2: FIND SIMILAR LOCATION NAMES
# --------------------------------------------------

def find_location_matches(user_input, vocabulary, limit=5):

    if not user_input or not vocabulary:
        return []

    location_names = [
        location["name"]
        for location in vocabulary
    ]

    matches = process.extract(
        user_input.upper().strip(),
        location_names,
        scorer=fuzz.ratio,
        limit=limit
    )

    results = []

    for name, score, index in matches:

        results.append({
            "name": name,
            "type": vocabulary[index]["type"],
            "confidence": round(score, 2)
        })

    return results


# --------------------------------------------------
# STEP 3: CLASSIFY LOCATION MATCH
# --------------------------------------------------

def classify_location_match(user_input, vocabulary):

    matches = find_location_matches(
        user_input,
        vocabulary,
        limit=5
    )

    if not matches:
        return {
            "status": "not_found",
            "match": None,
            "candidates": []
        }

    best = matches[0]

    exact_matches = [
        location for location in vocabulary
        if location["name"] == user_input.upper().strip()
    ]

    if exact_matches:

        if len(exact_matches) == 1:

            return {
                "status": "exact",
                "match": {
                    "name": exact_matches[0]["name"],
                    "type": exact_matches[0]["type"],
                    "confidence": 100.0
                },
                "candidates": matches
            }

        return {
            "status": "ambiguous",
            "match": None,
            "candidates": matches
        }

    second_score = (
        matches[1]["confidence"]
        if len(matches) > 1 else 0
    )

    margin = best["confidence"] - second_score

    if best["confidence"] >= 80 and margin >= 10:

        return {
            "status": "high_confidence",
            "match": best,
            "candidates": matches
        }

    if best["confidence"] >= 60:

        return {
            "status": "ambiguous",
            "match": None,
            "candidates": matches[:3]
        }

    return {
        "status": "not_found",
        "match": None,
        "candidates": matches[:3]
    }


# --------------------------------------------------
# STEP 4: EXTRACT LOCATION PHRASES
# --------------------------------------------------

def extract_location_phrases(question, vocabulary, max_words=4):

    word_spans = list(
        re.finditer(r"[a-zA-Z]+", question)
    )

    words = [
        match.group()
        for match in word_spans
    ]

    # Words that introduce a geographical location
    location_keywords = {
        "from",
        "in",
        "near",
        "within",
        "around",
        "at"
    }

    # Optional words before a location
    optional_prefix = {
        "the",
        "state",
        "district",
        "city",
        "town",
        "village",
        "of"
    }

    # Words that indicate the location phrase has ended
    clause_breaks = {
        "for",
        "with",
        "who",
        "which",
        "that",
        "having",
        "where",
        "whose",
        "aged",
        "age",
        "born",
        "living",
        "show",
        "find",
        "get",
        "people",
        "users",
        "list",
        "display",
        "count",
        "give"
    }

    # Words that should not be included at the end
    trailing_descriptors = {
        "state",
        "district",
        "city",
        "town",
        "village"
    }

    candidates = []

    def add_candidate(start, end):

        if start >= end:
            return

        phrase = " ".join(words[start:end])

        classification = classify_location_match(
            phrase,
            vocabulary
        )

        candidates.append({
            "phrase": phrase,
            "match": classification["match"],
            "status": classification["status"],
            "candidates": classification["candidates"],
            "start": start,
            "end": end
        })

    # Find location-introducing keywords
    for index, word in enumerate(words):

        if word.lower() not in location_keywords:
            continue

        start = index + 1

        # Skip optional prefixes
        while (
            start < len(words)
            and words[start].lower() in optional_prefix
        ):
            start += 1

        if start >= len(words):
            continue

        segment_start = start
        word_count = 0

        for current in range(start, len(words)):

            current_word = words[current].lower()

            # Stop if another location keyword starts
            # a new geographical phrase
            if current_word in location_keywords:
                break

            # Split multiple locations:
            # MP and UP
            if current_word in {"and", "or"}:

                add_candidate(segment_start, current)

                segment_start = current + 1
                word_count = 0

                while (
                    segment_start < len(words)
                    and words[segment_start].lower() in optional_prefix
                ):
                    segment_start += 1

                continue

            if current_word in clause_breaks:
                break

            if current_word in trailing_descriptors:
                break

            # Check punctuation between words
            if current > segment_start:

                previous_end = word_spans[current - 1].end()
                current_start = word_spans[current].start()

                separator = question[previous_end:current_start]

                if "," in separator or ";" in separator:
                    break

            word_count += 1

            if word_count > max_words:
                break

        # Add final location phrase
        if segment_start < len(words):

            end = min(
                segment_start + max_words,
                len(words)
            )

            # Do not include words beyond the current clause
            for current in range(segment_start, end):

                if words[current].lower() in (
                    location_keywords
                    | clause_breaks
                    | trailing_descriptors
                    | {"and", "or"}
                ):
                    end = current
                    break

            if end > segment_start:
                add_candidate(segment_start, end)

    # Remove duplicate and overlapping candidates.
    # Prefer longer phrases.
    selected = []

    candidates.sort(
        key=lambda item: (
            -(item["end"] - item["start"]),
            item["start"]
        )
    )

    for candidate in candidates:

        overlaps = any(
            candidate["start"] < item["end"]
            and candidate["end"] > item["start"]
            for item in selected
        )

        if not overlaps:
            selected.append(candidate)

    return sorted(
        selected,
        key=lambda item: item["start"]
    )


# --------------------------------------------------
# STEP 5: PREPARE LOCATION CONFIRMATION
# --------------------------------------------------

def prepare_location_confirmation(question, vocabulary):

    matches = extract_location_phrases(
        question,
        vocabulary
    )

    word_spans = list(
        re.finditer(r"[a-zA-Z]+", question)
    )

    suggestions = []
    ambiguous_matches = []
    not_found_locations = []

    for item in matches:

        start_index = item["start"]
        end_index = item["end"]

        original_phrase = question[
            word_spans[start_index].start():
            word_spans[end_index - 1].end()
        ]

        # Case 1: Exact match
        if item["status"] == "exact":
            continue

        # Case 2: Location not found
        if item["status"] == "not_found":

            not_found_locations.append({
                "original": original_phrase,
                "candidates": item["candidates"]
            })

            continue

        # Case 3: Ambiguous match
        if item["status"] == "ambiguous":

            ambiguous_matches.append({
                "original": original_phrase,
                "candidates": item["candidates"]
            })

            continue

        # Case 4: High-confidence match
        correct_name = item["match"]["name"]

        suggestions.append({
            "original": original_phrase,
            "suggested": correct_name,
            "confidence": item["match"]["confidence"],
            "start": word_spans[start_index].start(),
            "end": word_spans[end_index - 1].end()
        })

    # Unknown location takes priority.
    # Stop the complete question if any location is unknown.
    if not_found_locations:

        return {
            "status": "location_not_found",
            "original_question": question,
            "suggested_question": question,
            "not_found_locations": not_found_locations,
            "suggestions": suggestions,
            "ambiguous_matches": [],
            "confirmation_question": None
        }

    # Ambiguous location handling
    if ambiguous_matches:

        return {
            "status": "clarification_required",
            "original_question": question,
            "suggested_question": question,
            "suggestions": suggestions,
            "ambiguous_matches": ambiguous_matches,
            "confirmation_question": None
        }

    # No spelling correction required
    if not suggestions:

        return {
            "status": "no_correction_needed",
            "original_question": question,
            "suggested_question": question,
            "suggestions": [],
            "ambiguous_matches": [],
            "confirmation_question": None
        }

    # Build corrected question
    suggested_question = question

    for item in reversed(suggestions):

        suggested_question = (
            suggested_question[:item["start"]]
            + item["suggested"]
            + suggested_question[item["end"]:]
        )

    confirmation_text = (
        "Possible spelling correction found:\n"
    )

    for item in suggestions:

        confirmation_text += (
            f"\n{item['original']} "
            f"-> {item['suggested']}"
            f" (Score: {item['confidence']})"
        )

    confirmation_text += (
        "\n\nWould you like to correct it?"
    )

    return {
        "status": "confirmation_required",
        "original_question": question,
        "suggested_question": suggested_question,
        "suggestions": suggestions,
        "ambiguous_matches": [],
        "confirmation_question": confirmation_text
    }


# --------------------------------------------------
# STEP 6: APPLY USER CONFIRMATION
# --------------------------------------------------

def confirm_location_correction(pending, user_answer):

    answer = user_answer.strip().lower()

    if answer in ("yes", "y"):

        return {
            "status": "corrected",
            "question": pending["suggested_question"]
        }

    elif answer in ("no", "n"):

        return {
            "status": "rejected",
            "question": pending["original_question"]
        }

    return {
        "status": "invalid_answer",
        "question": None,
        "message": "Please answer Yes or No."
    }


# --------------------------------------------------
# STEP 7: CLI TESTING
# --------------------------------------------------

if __name__ == "__main__":

    print("=" * 45)
    print("       QUERYMATE LOCATION CORRECTOR")
    print("=" * 45)

    try:

        locations = load_location_vocabulary()

        print(
            f"\nLoaded {len(locations)} geographical locations."
        )

        question = input(
            "\nEnter your question: "
        ).strip()

        if not question:

            print("Please enter a valid question.")

        else:

            pending = prepare_location_confirmation(
                question,
                locations
            )

            # Case 1: No correction required
            if pending["status"] == "no_correction_needed":

                print("\nNo spelling correction required.")
                print("Original question:", question)

            # Case 2: Unknown location
            elif pending["status"] == "location_not_found":

                print("\nLocation not recognized.")

                for item in pending["not_found_locations"]:

                    print(
                        f"\nUnrecognized location: {item['original']}"
                    )

                print(
                    "\nPlease enter a valid state or district name."
                )

            # Case 3: Ambiguous location
            elif pending["status"] == "clarification_required":

                print(
                    "\nCould not confidently identify "
                    "the following location:"
                )

                for item in pending["ambiguous_matches"]:

                    print(f"\nInput: {item['original']}")
                    print("Possible matches:")

                    for index, candidate in enumerate(
                        item["candidates"],
                        start=1
                    ):

                        print(
                            f"{index}. {candidate['name']} "
                            f"({candidate['type']}) "
                            f"- {candidate['confidence']}"
                        )

                print(
                    "\nPlease clarify the correct location."
                )

            # Case 4: Ask user before correction
            elif pending["status"] == "confirmation_required":

                print(
                    "\n" + pending["confirmation_question"]
                )

                while True:

                    answer = input(
                        "\nYour answer (Yes/No): "
                    )

                    result = confirm_location_correction(
                        pending,
                        answer
                    )

                    if result["status"] == "invalid_answer":

                        print(result["message"])
                        continue

                    if result["status"] == "corrected":

                        print("\nSpelling correction accepted!")

                    else:

                        print("\nSpelling correction rejected.")

                    print(
                        "Final question:",
                        result["question"]
                    )

                    break

    except Exception as error:

        print("\nQueryMate error:", str(error))
