"""JSON schemas for Structured Outputs (spec 3.2).

The Claude API compiles these into a grammar that constrains generation
server-side, so the pipeline never has to repair malformed JSON or carry a
local validation library.

Every schema sets ``additionalProperties: false`` and lists every property in
``required`` — both are required for strict schema compilation.
"""

from __future__ import annotations

from bank.models import QuestionType

_GAP_FILL_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sentence_with_gap", "target_word", "distractor_check", "rationale"],
    "properties": {
        "sentence_with_gap": {
            "type": "string",
            "description": "One sentence with exactly one blank written as ________.",
        },
        "target_word": {
            "type": "string",
            "description": "The single word that fills the blank.",
        },
        "distractor_check": {
            "type": "string",
            "description": (
                "Name any other word from the supplied vocabulary pool that could also "
                "fit the blank grammatically and semantically, or write NONE."
            ),
        },
        "rationale": {
            "type": "string",
            "description": "One sentence: how the sentence forces this word and no other.",
        },
    },
}

_WORD_FORMATION_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sentence_with_gap", "root_word", "correct_form", "target_pos"],
    "properties": {
        "sentence_with_gap": {"type": "string", "description": "Sentence with one ________ blank."},
        "root_word": {"type": "string", "description": "The root, shown to the student in capitals."},
        "correct_form": {"type": "string", "description": "The derived form that fills the blank."},
        "target_pos": {
            "type": "string",
            "enum": ["noun", "verb", "adjective", "adverb"],
        },
    },
}

_TRANSFORMATION_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["original_sentence", "keyword", "acceptable_answers"],
    "properties": {
        "original_sentence": {"type": "string"},
        "keyword": {"type": "string", "description": "The word the rewrite must use, unchanged."},
        "acceptable_answers": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {"type": "string"},
            "description": "Every acceptable full rewrite, most natural first.",
        },
    },
}

_ERROR_CORRECTION_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sentence_with_error", "error_type", "corrected_word_phrase", "correct_sentence"],
    "properties": {
        "sentence_with_error": {
            "type": "string",
            "description": "A sentence containing exactly one error, of the target grammar point.",
        },
        "error_type": {"type": "string"},
        "corrected_word_phrase": {
            "type": "string",
            "description": "Only the corrected word or phrase, not the whole sentence.",
        },
        "correct_sentence": {"type": "string"},
    },
}

ITEM_SCHEMAS = {
    QuestionType.GAP_FILL: _GAP_FILL_ITEM,
    QuestionType.WORD_FORMATION: _WORD_FORMATION_ITEM,
    QuestionType.KEY_WORD_TRANSFORMATION: _TRANSFORMATION_ITEM,
    QuestionType.ERROR_CORRECTION: _ERROR_CORRECTION_ITEM,
}


def generation_schema(question_type: str) -> dict:
    """The response schema for a batch of one question type."""
    item_schema = ITEM_SCHEMAS[question_type]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {"items": {"type": "array", "items": item_schema}},
    }


#: Schema for the second-pass grammaticality review (spec 3.3).
REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["index", "natural", "single_answer", "problem"],
                "properties": {
                    "index": {"type": "integer", "description": "Position in the supplied list."},
                    "natural": {
                        "type": "boolean",
                        "description": "True if a native speaker would write this sentence.",
                    },
                    "single_answer": {
                        "type": "boolean",
                        "description": "True if exactly one answer from the unit's vocabulary fits.",
                    },
                    "problem": {
                        "type": "string",
                        "description": "The problem in a few words, or NONE.",
                    },
                },
            },
        }
    },
}
