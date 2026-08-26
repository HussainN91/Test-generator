"""Turn an Item's typed payload into something printable.

Both the HTML templates and the .docx exporter go through here, so a test on
screen and the same test on paper can never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bank.models import Item, QuestionType

OPTION_LETTERS = "ABCDEFGH"


@dataclass
class RenderedQuestion:
    """A question reduced to the pieces a renderer needs, whatever the type."""

    instruction: str
    prompt: str
    options: list[str] = field(default_factory=list)
    pairs: list[tuple[str, str]] = field(default_factory=list)
    answer: str = ""
    answer_lines: int = 1

    @property
    def lettered_options(self) -> list[tuple[str, str]]:
        return list(zip(OPTION_LETTERS, self.options))

    @property
    def matching_rows(self) -> list[dict]:
        """One row per pair: the numbered word beside the lettered definition."""
        return [
            {
                "number": index + 1,
                "left": left,
                "letter": OPTION_LETTERS[index],
                "right": right,
            }
            for index, (left, right) in enumerate(self.pairs)
        ]


INSTRUCTIONS = {
    QuestionType.GAP_FILL: "Complete the sentence with one word.",
    QuestionType.WORD_FORMATION: "Use the word in capitals to form a word that fits the gap.",
    QuestionType.KEY_WORD_TRANSFORMATION: (
        "Rewrite the sentence using the key word, keeping the same meaning."
    ),
    QuestionType.ERROR_CORRECTION: "There is one mistake in this sentence. Correct it.",
    QuestionType.MATCHING: "Match each word to its meaning.",
    QuestionType.MULTIPLE_CHOICE: "Choose the correct answer.",
    QuestionType.ODD_ONE_OUT: "Choose the correct answer.",
}


def render_question(item: Item) -> RenderedQuestion:
    """Build a renderer-agnostic view of one item."""
    payload = item.payload or {}
    instruction = INSTRUCTIONS.get(item.question_type, "")
    answer = item.model_answer

    if item.question_type == QuestionType.GAP_FILL:
        return RenderedQuestion(
            instruction=instruction,
            prompt=payload.get("sentence_with_gap", ""),
            answer=answer,
        )

    if item.question_type == QuestionType.WORD_FORMATION:
        root = payload.get("root_word", "")
        prompt = payload.get("sentence_with_gap", "")
        if root and root.upper() not in prompt.upper():
            prompt = f"{prompt}   ({root.upper()})"
        return RenderedQuestion(instruction=instruction, prompt=prompt, answer=answer)

    if item.question_type == QuestionType.KEY_WORD_TRANSFORMATION:
        alternatives = item.acceptable_answers or payload.get("acceptable_answers") or []
        return RenderedQuestion(
            instruction=f'{instruction} Key word: {payload.get("keyword", "")}',
            prompt=payload.get("original_sentence", ""),
            answer=" / ".join([answer] + [a for a in alternatives if a != answer]),
            answer_lines=2,
        )

    if item.question_type == QuestionType.ERROR_CORRECTION:
        return RenderedQuestion(
            instruction=instruction,
            prompt=payload.get("sentence_with_error", ""),
            answer=answer,
        )

    if item.question_type == QuestionType.MATCHING:
        pairs_raw = payload.get("item_set", [])
        words = [p.get("left", "") for p in pairs_raw]
        definitions = [p.get("right", "") for p in pairs_raw]
        order = payload.get("right_order") or list(range(len(pairs_raw)))
        if len(order) != len(pairs_raw):
            order = list(range(len(pairs_raw)))

        # Left column keeps the stored order and is numbered 1..n; the right
        # column is lettered A..N in the shuffled `order` recorded at
        # generation time, which is what item.model_answer was computed against.
        rows = [(words[i], definitions[order[i]]) for i in range(len(pairs_raw))]
        return RenderedQuestion(
            instruction=payload.get("prompt") or instruction,
            prompt="",
            pairs=rows,
            answer=answer,
            answer_lines=len(rows),
        )

    if item.question_type in (QuestionType.MULTIPLE_CHOICE, QuestionType.ODD_ONE_OUT):
        return RenderedQuestion(
            instruction=instruction,
            prompt=payload.get("sentence", ""),
            options=payload.get("options", []),
            answer=answer,
        )

    return RenderedQuestion(instruction=instruction, prompt=str(payload), answer=answer)


def render_variant(variant) -> list[tuple[int, RenderedQuestion]]:
    """All questions of a variant, in their fixed order."""
    return [
        (question.position, render_question(question.item))
        for question in variant.questions.select_related("item").all()
    ]
