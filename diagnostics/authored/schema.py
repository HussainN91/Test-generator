"""Validation for authored reading, writing and speaking content (spec 3.3).

Authored content is the bulk of the diagnostic and the part no parser can
check for us, so the shape is enforced mechanically: word counts, question
counts, subtype distribution, and answer well-formedness. Quality remains a
human review gate; these rules only stop malformed content reaching the bank.
"""

from diagnostics.constants import MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS, OPTION_LETTERS

TRUE_FALSE_ANSWERS = {"TRUE", "FALSE", "NOT GIVEN"}


class ContentError(ValueError):
    """Authored content does not match the required pattern."""


def _require_positions(items, expected, label, key="position"):
    positions = [item[key] for item in items]
    if positions != list(range(1, expected + 1)):
        raise ContentError(
            f"{label}: expected exactly {expected} items numbered 1-{expected}, "
            f"got positions {positions}."
        )


VALID_READING_SUBTYPES = {
    "true_false_ng", "mcq", "completion", "heading_matching", "paragraph_matching",
}


def validate_reading(payload):
    """Validate one reading passage + its 10 questions.

    No fixed subtype distribution is enforced — the real content bank mixes
    subtypes freely per passage (see Design Revision 1). Only the total count
    (exactly 10) and each question's subtype membership are checked.
    """
    label = payload.get("label", "<unlabelled>")
    if "label" not in payload:
        raise ContentError(f"{label}: missing required \"label\" field.")
    word_count = len(payload["body"].split())
    if not MIN_PASSAGE_WORDS <= word_count <= MAX_PASSAGE_WORDS:
        raise ContentError(
            f"{label}: passage must be {MIN_PASSAGE_WORDS}-{MAX_PASSAGE_WORDS} words; "
            f"this one is {word_count}."
        )

    questions = payload["questions"]
    _require_positions(questions, 10, label)
    for question in questions:
        if question["subtype"] not in VALID_READING_SUBTYPES:
            raise ContentError(
                f"{label} Q{question['position']}: unknown subtype "
                f"{question['subtype']!r}; must be one of {sorted(VALID_READING_SUBTYPES)}."
            )

    for question in questions:
        position, subtype, answer = (
            question["position"], question["subtype"], question["answer"],
        )
        if subtype == "true_false_ng":
            if answer not in TRUE_FALSE_ANSWERS:
                raise ContentError(
                    f"{label} Q{position}: answer must be one of {sorted(TRUE_FALSE_ANSWERS)}."
                )
        elif subtype == "mcq":
            if len(question["options"]) != 4:
                raise ContentError(f"{label} Q{position}: mcq needs four options.")
            if answer not in OPTION_LETTERS:
                raise ContentError(
                    f"{label} Q{position}: answer must be an option letter A-D."
                )
        elif subtype == "completion":
            if len(answer.split()) > 2:
                raise ContentError(
                    f"{label} Q{position}: completion answers are at most two words."
                )
        elif subtype == "heading_matching":
            if not question["options"]:
                raise ContentError(f"{label} Q{position}: heading_matching needs options.")
            normalized_options = {str(option).strip().lower() for option in question["options"]}
            if str(answer).strip().lower() not in normalized_options:
                raise ContentError(
                    f"{label} Q{position}: answer must be one of the given headings."
                )
        elif subtype == "paragraph_matching":
            if not answer:
                raise ContentError(f"{label} Q{position}: paragraph_matching needs an answer.")
    return payload
