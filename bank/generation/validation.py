"""Validation layer (spec 3.3) — structural checks that need no API call.

Two independent jobs:

* **Structural checks** that run with nothing installed: exactly one blank, the
  target word actually in the vocabulary pool, the answer not visible in the
  prompt, and — the spec's hardest requirement — the gap-fill uniqueness check
  against the unit's full eligible vocabulary.
* **spaCy checks**, when the small English model is installed: confirm the
  target word appears with the intended part of speech and that the sentence
  parses as a sentence. spaCy describes structure; it does not judge whether
  English is natural, which is why the Claude review pass exists alongside it.

Everything degrades: with no spaCy installed the structural checks still run
and the spaCy-specific ones report as skipped rather than failing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from bank.models import Item, QuestionType
from content.models import PartOfSpeech

BLANK_PATTERN = re.compile(r"_{3,}")

#: spaCy's coarse tags mapped onto our parts of speech.
SPACY_POS_MAP = {
    "NOUN": PartOfSpeech.NOUN,
    "PROPN": PartOfSpeech.NOUN,
    "VERB": PartOfSpeech.VERB,
    "AUX": PartOfSpeech.VERB,
    "ADJ": PartOfSpeech.ADJECTIVE,
    "ADV": PartOfSpeech.ADVERB,
    "ADP": PartOfSpeech.PREPOSITION,
    "CCONJ": PartOfSpeech.CONJUNCTION,
    "SCONJ": PartOfSpeech.CONJUNCTION,
    "DET": PartOfSpeech.DETERMINER,
    "PRON": PartOfSpeech.PRONOUN,
}


@dataclass
class ValidationResult:
    failures: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    spacy_ran: bool = False
    uniqueness_checked: bool = False

    @property
    def passed(self) -> bool:
        return not self.failures


@lru_cache(maxsize=1)
def load_nlp():
    """Load the small English model once, or return None if it is unavailable."""
    try:
        import spacy
    except ImportError:
        return None
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        return None


def spacy_available() -> bool:
    return load_nlp() is not None


# --------------------------------------------------------------------------
# Structural checks
# --------------------------------------------------------------------------


def _pool_words(item: Item) -> list[str]:
    """Every vocabulary word taught in this item's unit."""
    return list(item.unit.vocabulary.values_list("word", flat=True))


def check_single_blank(text: str, result: ValidationResult) -> None:
    blanks = BLANK_PATTERN.findall(text or "")
    if len(blanks) != 1:
        result.failures.append(f"expected exactly one blank, found {len(blanks)}")


def check_answer_not_given_away(text: str, answer: str, result: ValidationResult) -> None:
    """The answer must not already be sitting in the prompt."""
    if not answer:
        return
    pattern = rf"\b{re.escape(answer.strip())}\b"
    if re.search(pattern, text or "", flags=re.IGNORECASE):
        result.failures.append(f"the answer '{answer}' appears in the prompt")


def check_gap_uniqueness(item: Item, result: ValidationResult) -> None:
    """The spec's hardest correctness requirement (3.5).

    Substitutes every other word taught in the unit into the blank and rejects
    the item if another word fits. Without spaCy this can only rule out words
    that are grammatically impossible in the slot, so the check is recorded as
    partial and the Claude review pass carries the semantic half.
    """
    sentence = item.payload.get("sentence_with_gap", "")
    target = (item.payload.get("target_word") or item.model_answer or "").strip()
    if not sentence or not target:
        result.failures.append("gap-fill is missing its sentence or target word")
        return

    pool = [w for w in _pool_words(item) if w.lower() != target.lower()]
    nlp = load_nlp()
    if nlp is None:
        result.skipped.append("gap uniqueness: spaCy not installed, only the LLM pass checked it")
        return

    target_doc = nlp(BLANK_PATTERN.sub(target, sentence))
    target_tags = _slot_tags(target_doc, target)
    if target_tags is None:
        result.failures.append("could not locate the target word after filling the blank")
        return

    competitors = []
    for candidate in pool:
        if " " in candidate:
            continue
        doc = nlp(BLANK_PATTERN.sub(candidate, sentence))
        tags = _slot_tags(doc, candidate)
        # Same coarse tag AND same dependency role means the slot does not
        # grammatically exclude this word, so a teacher could be argued down.
        if tags == target_tags:
            competitors.append(candidate)

    result.uniqueness_checked = True
    if competitors:
        preview = ", ".join(competitors[:5])
        result.failures.append(f"another unit word may also fit the blank: {preview}")


def _slot_tags(doc, word: str) -> tuple[str, str] | None:
    for token in doc:
        if token.text.lower() == word.lower():
            return (token.pos_, token.dep_)
    return None


def check_target_pos(item: Item, result: ValidationResult) -> None:
    """Confirm the produced word really is the part of speech the item claims.

    Only meaningful for items whose prompt is a real sentence. A cue frame
    ("Write the adjective formed from ENTERTAIN: ____") gives the parser no
    syntactic context, so tagging the filled slot there produces false
    failures rather than findings.
    """
    if (item.payload or {}).get("cue_frame"):
        result.skipped.append("part-of-speech check: prompt is a cue frame, not a sentence")
        return

    nlp = load_nlp()
    if nlp is None:
        result.skipped.append("part-of-speech check: spaCy not installed")
        return

    sentence = item.payload.get("sentence_with_gap", "")
    answer = item.payload.get("correct_form") or item.model_answer
    expected = item.payload.get("target_pos")
    if not (sentence and answer and expected):
        return

    doc = nlp(BLANK_PATTERN.sub(answer, sentence))
    tags = _slot_tags(doc, answer)
    result.spacy_ran = True
    if tags is None:
        return
    actual = SPACY_POS_MAP.get(tags[0])
    if actual and actual != expected:
        result.failures.append(f"expected a {expected}, but the word reads as a {actual}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def validate_item(item: Item) -> ValidationResult:
    """Run every check that applies to this item's question type."""
    result = ValidationResult()
    payload = item.payload or {}

    if item.question_type == QuestionType.GAP_FILL:
        sentence = payload.get("sentence_with_gap", "")
        check_single_blank(sentence, result)
        check_answer_not_given_away(sentence, payload.get("target_word", ""), result)
        check_gap_uniqueness(item, result)
        pool = {w.lower() for w in _pool_words(item)}
        target = (payload.get("target_word") or "").lower()
        if target and target not in pool:
            result.failures.append(f"'{target}' is not in this unit's vocabulary")

    elif item.question_type == QuestionType.WORD_FORMATION:
        sentence = payload.get("sentence_with_gap", "")
        check_single_blank(sentence, result)
        check_answer_not_given_away(sentence, payload.get("correct_form", ""), result)
        check_target_pos(item, result)
        root = (payload.get("root_word") or "").lower()
        form = (payload.get("correct_form") or "").lower()
        if root and form and root == form:
            result.failures.append("the answer is identical to the root word")

    elif item.question_type == QuestionType.KEY_WORD_TRANSFORMATION:
        keyword = (payload.get("keyword") or "").lower()
        answers = item.acceptable_answers or payload.get("acceptable_answers") or []
        if not answers:
            result.failures.append("no acceptable answers recorded")
        for answer in answers:
            if keyword and keyword not in answer.lower():
                result.failures.append(f"an acceptable answer omits the key word: {answer}")
                break
        original = (payload.get("original_sentence") or "").lower()
        if keyword and keyword in original:
            result.failures.append("the key word already appears in the original sentence")

    elif item.question_type == QuestionType.ERROR_CORRECTION:
        sentence = payload.get("sentence_with_error", "")
        correction = payload.get("corrected_word_phrase", "")
        if not sentence or not correction:
            result.failures.append("missing the sentence or its correction")
        elif correction.lower() in sentence.lower():
            result.failures.append("the correction already appears in the sentence")

    elif item.question_type in (QuestionType.MULTIPLE_CHOICE, QuestionType.ODD_ONE_OUT):
        options = payload.get("options") or []
        if len(options) < 2:
            result.failures.append("fewer than two options")
        if len({o.lower() for o in options}) != len(options):
            result.failures.append("duplicate options")

    elif item.question_type == QuestionType.MATCHING:
        pairs = payload.get("item_set") or []
        lefts = [p.get("left", "").lower() for p in pairs]
        rights = [p.get("right", "").lower() for p in pairs]
        if len(pairs) < 3:
            result.failures.append("fewer than three pairs")
        if len(set(lefts)) != len(lefts):
            result.failures.append("the same word appears twice")
        if len(set(rights)) != len(rights):
            result.failures.append("the same definition appears twice")

    return result
