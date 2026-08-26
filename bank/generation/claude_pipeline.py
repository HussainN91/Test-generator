"""Offline generation and review through the Claude API (spec 3.2-3.3).

**Nothing in the deployed app imports this module.** It runs on the admin's
machine (or a one-off job), writes vetted items into the database, and the
production server only ever reads what it left behind. The `anthropic` import
is deliberately kept inside the functions so a production install without the
SDK still boots.

Two passes, as the spec requires:

1. **Generate** — the model is given the unit's grammar point, its vocabulary
   pool, and sample sentences as *structural* references, with an explicit
   instruction to generalise the pattern rather than reuse the examples.
   Structured Outputs constrains the response to the schema server-side.
2. **Review** — a second call judges each candidate for naturalness and, for
   gap-fills, whether exactly one word from the pool fits. A parser cannot
   judge either of these; a language model can.

Items that pass both land as DRAFT and still go through spaCy validation
(`validate_items`) before anything marks them approved.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from bank.generation.schemas import REVIEW_SCHEMA, generation_schema
from bank.models import QuestionType
from content.models import Unit

MODEL = "claude-opus-5"
MAX_TOKENS = 16000

#: Kept small: a short pool per call gives the model room to write carefully,
#: and makes the gap-fill uniqueness question tractable for the review pass.
DEFAULT_BATCH_SIZE = 8


class PipelineUnavailable(RuntimeError):
    """Raised when the pipeline is invoked without the SDK or credentials."""


@dataclass
class GeneratedItem:
    question_type: str
    fields: dict
    review_problem: str = ""

    @property
    def accepted(self) -> bool:
        return not self.review_problem


def _client():
    try:
        import anthropic
    except ImportError as error:  # pragma: no cover - environment dependent
        raise PipelineUnavailable(
            "The generation pipeline needs the Anthropic SDK: pip install anthropic"
        ) from error

    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        # The SDK also resolves `ant auth login` profiles, so this is a warning
        # path rather than a hard failure — let the SDK decide.
        pass
    return anthropic.Anthropic()


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You write English-language test items for secondary-school students following the Cambridge "Prepare" syllabus.

Rules that override everything else:

1. Every item must have exactly ONE correct answer. If a second answer from the supplied vocabulary pool could also be defended, the item is unusable — write a different one. A teacher marks these by ticking; an ambiguous item costs them more time than a whole extra page of questions.
2. Generalise the pattern. The sample sentences show you the STRUCTURE the unit teaches. Never reuse a sample sentence, and never lightly reword one. Write new sentences about new situations, using the vocabulary pool you are given.
3. Stay inside the level. Use only the supplied vocabulary plus common function words and everyday words a student at this level already knows.
4. Keep contexts age-appropriate and thematically consistent with the unit.
5. One sentence per item unless the question type needs two."""

TYPE_INSTRUCTIONS = {
    QuestionType.GAP_FILL: (
        "Write gap-fill items. Blank exactly one word, written as ________. The blank must be a "
        "word from the vocabulary pool. The surrounding sentence must make that word the only "
        "possible answer — check every other pool word before you commit, and report your check "
        "in distractor_check."
    ),
    QuestionType.WORD_FORMATION: (
        "Write word-formation items. Give a root word; the student writes a derived form that "
        "fits the gap. The grammar of the sentence must force one specific form (part of speech, "
        "singular/plural, positive/negative)."
    ),
    QuestionType.KEY_WORD_TRANSFORMATION: (
        "Write key word transformation items. Give a sentence and a key word; the student rewrites "
        "the sentence with the same meaning, using the key word unchanged. The target structure "
        "must be the unit's grammar point. List every acceptable rewrite."
    ),
    QuestionType.ERROR_CORRECTION: (
        "Write error-correction items. Each sentence contains exactly one error, and that error "
        "must be of the grammar point being taught — not a spelling slip or a vocabulary mistake. "
        "The rest of the sentence must be flawless."
    ),
}


def build_generation_prompt(unit: Unit, question_type: str, count: int) -> str:
    """Assemble the unit's grammar point, vocabulary pool and pattern references."""
    grammar = getattr(unit, "grammar_point", None)
    vocabulary = list(unit.vocabulary.all())

    pool_lines = []
    for entry in vocabulary:
        label = entry.get_part_of_speech_display().lower()
        gloss = f" — {entry.definition}" if entry.definition else ""
        pool_lines.append(f"- {entry.word} ({label}){gloss}")

    samples = list(grammar.sample_sentences.all()[:8]) if grammar else []
    sample_lines = [f"- {s.text}" for s in samples]

    sections = [
        f"Grade {unit.grade.number}, Unit {unit.number}: {unit.title or unit.theme}",
        "",
        f"GRAMMAR POINT: {grammar.name if grammar else 'general vocabulary'}",
    ]
    if grammar and grammar.body:
        sections += ["", "How the syllabus explains it:", grammar.body[:4000]]
    if sample_lines:
        sections += [
            "",
            "PATTERN REFERENCES (structure only — do not reuse or reword these):",
            *sample_lines,
        ]
    sections += [
        "",
        "VOCABULARY POOL (the only content words you may target):",
        *pool_lines,
        "",
        f"TASK: {TYPE_INSTRUCTIONS[question_type]}",
        "",
        f"Write {count} items. Each must target a different vocabulary word.",
    ]
    return "\n".join(sections)


def build_review_prompt(unit: Unit, question_type: str, candidates: list[dict]) -> str:
    """Ask a second pass to judge naturalness and answer uniqueness."""
    pool = ", ".join(entry.word for entry in unit.vocabulary.all())
    listing = json.dumps(candidates, ensure_ascii=False, indent=1)
    return (
        f"These are candidate {QuestionType(question_type).label} items for grade "
        f"{unit.grade.number}, unit {unit.number}.\n\n"
        f"The unit's vocabulary pool is: {pool}\n\n"
        f"Candidates (index matches position):\n{listing}\n\n"
        "For each candidate decide two things.\n"
        "1. natural: would a careful native speaker write this sentence? Judge the English "
        "itself — awkward phrasing, wrong collocation, or a stilted context all mean false.\n"
        "2. single_answer: is there EXACTLY ONE answer? For a gap-fill, check every word in the "
        "pool against the blank. For a transformation, check that no other structure using the "
        "key word also works. If any second answer is defensible, this is false.\n"
        "Be strict. A wrong item reaching a classroom costs far more than a rejected one."
    )


# --------------------------------------------------------------------------
# API calls
# --------------------------------------------------------------------------


def _structured_call(client, prompt: str, schema: dict, system: str | None = None) -> dict:
    """One Structured Outputs call; the response is guaranteed to match `schema`."""
    kwargs = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"format": {"type": "json_schema", "schema": schema}, "effort": "high"},
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    if response.stop_reason == "refusal":
        raise PipelineUnavailable(
            f"The model declined this request: {getattr(response.stop_details, 'explanation', '')}"
        )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def generate_candidates(unit: Unit, question_type: str, count: int) -> list[dict]:
    """Pass 1: produce `count` schema-valid candidate items for one unit."""
    client = _client()
    prompt = build_generation_prompt(unit, question_type, count)
    data = _structured_call(client, prompt, generation_schema(question_type), SYSTEM_PROMPT)
    return data.get("items", [])


def review_candidates(unit: Unit, question_type: str, candidates: list[dict]) -> list[str]:
    """Pass 2: return one problem string per candidate ("" means it passed)."""
    if not candidates:
        return []
    client = _client()
    prompt = build_review_prompt(unit, question_type, candidates)
    data = _structured_call(client, prompt, REVIEW_SCHEMA)

    problems = ["review returned no verdict"] * len(candidates)
    for verdict in data.get("verdicts", []):
        index = verdict.get("index", -1)
        if not 0 <= index < len(candidates):
            continue
        if not verdict.get("natural", False):
            problems[index] = f"unnatural: {verdict.get('problem', '')}".strip()
        elif not verdict.get("single_answer", False):
            problems[index] = f"more than one answer: {verdict.get('problem', '')}".strip()
        else:
            problems[index] = ""
    return problems


def generate_reviewed_items(
    unit: Unit, question_type: str, count: int = DEFAULT_BATCH_SIZE
) -> list[GeneratedItem]:
    """Run both passes and return every candidate with its review outcome attached.

    Rejected candidates are returned too, not dropped — the caller records them
    so an admin can see what the pipeline threw away and why.
    """
    candidates = generate_candidates(unit, question_type, count)
    problems = review_candidates(unit, question_type, candidates)
    return [
        GeneratedItem(question_type=question_type, fields=fields, review_problem=problem)
        for fields, problem in zip(candidates, problems)
    ]
