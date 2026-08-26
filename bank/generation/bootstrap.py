"""Deterministic item generation from the imported syllabus — no LLM involved.

Why this exists
---------------
The Claude pipeline (``bank/generation/claude_pipeline.py``) is what produces
the production-quality item types the spec prioritises: gap-fill, key word
transformation and error correction. All three require *newly written
sentences*, which only a language model can supply.

This module covers the three types that can be derived with certainty from
data already in the database — vocabulary, part of speech and the guide's own
definitions — so the app is usable end-to-end before any API key exists:

* **matching**        vocabulary <-> definition (definitions come from the guide)
* **multiple choice** definition given, four same-part-of-speech options
* **word formation**  prefix/suffix pairs and word families

Every item it produces has a single unambiguous answer, which is the whole
point of the marking-speed constraint. Distractors are drawn from the same
unit and same part of speech so an option set is never trivially eliminable.

Determinism: item selection is seeded per unit, so re-running produces the
same bank rather than a slightly different one each time.
"""

from __future__ import annotations

import hashlib
import random
import re
import string
from dataclasses import dataclass, field

from content.models import PartOfSpeech, Unit, VocabularyEntry
from bank.models import QuestionType

#: Prefixes the guides teach explicitly, longest first so "un" does not win
#: over a longer match.
NEGATIVE_PREFIXES = ("un", "in", "im", "ir", "il", "dis", "non", "mis")

#: Suffix -> the part of speech it derives, used to label word-family items.
SUFFIX_POS_HINTS = {
    "ment": PartOfSpeech.NOUN,
    "tion": PartOfSpeech.NOUN,
    "sion": PartOfSpeech.NOUN,
    "ness": PartOfSpeech.NOUN,
    "ity": PartOfSpeech.NOUN,
    "er": PartOfSpeech.NOUN,
    "or": PartOfSpeech.NOUN,
    "ist": PartOfSpeech.NOUN,
    "ian": PartOfSpeech.NOUN,
    "ance": PartOfSpeech.NOUN,
    "ence": PartOfSpeech.NOUN,
    "ful": PartOfSpeech.ADJECTIVE,
    "less": PartOfSpeech.ADJECTIVE,
    "able": PartOfSpeech.ADJECTIVE,
    "ible": PartOfSpeech.ADJECTIVE,
    "ive": PartOfSpeech.ADJECTIVE,
    "ous": PartOfSpeech.ADJECTIVE,
    "al": PartOfSpeech.ADJECTIVE,
    "ic": PartOfSpeech.ADJECTIVE,
    "ly": PartOfSpeech.ADVERB,
    "ing": PartOfSpeech.ADJECTIVE,
    "ed": PartOfSpeech.ADJECTIVE,
}

MATCHING_SET_SIZE = 5
MCQ_OPTION_COUNT = 4
#: Option labels. Matching sets use five, MCQ uses the first four.
OPTION_LETTERS = string.ascii_uppercase


@dataclass
class DraftItem:
    """A generated item, not yet persisted."""

    unit_id: int
    question_type: str
    payload: dict
    model_answer: str
    acceptable_answers: list[str] = field(default_factory=list)
    target_vocabulary_id: int | None = None

    def content_hash(self) -> str:
        basis = f"{self.unit_id}|{self.question_type}|{self.model_answer}|{_stable(self.payload)}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _stable(payload: dict) -> str:
    """A stable string form of a payload, for hashing."""
    import json

    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _is_single_word(word: str) -> bool:
    return " " not in word.strip()


def _usable_for_definition_items(entry: VocabularyEntry) -> bool:
    """A definition-based item needs a definition that is not a bare restatement."""
    definition = entry.definition.strip()
    if len(definition) < 12:
        return False
    # "unfriendly -> Not friendly" would make the answer guessable from the
    # definition text itself, which tests nothing.
    if entry.word.lower() in definition.lower():
        return False
    return True


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


def build_matching_items(unit: Unit, rng: random.Random) -> list[DraftItem]:
    """Group definable vocabulary into fixed sets of five word/definition pairs."""
    entries = [e for e in unit.vocabulary.all() if _usable_for_definition_items(e)]
    # Same word appearing twice in one set would make the pairing ambiguous.
    seen: set[str] = set()
    unique: list[VocabularyEntry] = []
    for entry in entries:
        key = entry.word.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)

    rng.shuffle(unique)
    items: list[DraftItem] = []
    for start in range(0, len(unique) - MATCHING_SET_SIZE + 1, MATCHING_SET_SIZE):
        chunk = unique[start : start + MATCHING_SET_SIZE]
        pairs = [{"left": e.word, "right": e.definition} for e in chunk]
        # Definitions are presented shuffled; the answer key restores the pairing.
        order = list(range(len(chunk)))
        rng.shuffle(order)
        answer = ", ".join(f"{i + 1}-{OPTION_LETTERS[order.index(i)]}" for i in range(len(chunk)))
        items.append(
            DraftItem(
                unit_id=unit.id,
                question_type=QuestionType.MATCHING,
                payload={
                    "item_set": pairs,
                    "prompt": "Match each word (1-5) to its meaning (A-E).",
                    "right_order": order,
                },
                model_answer=answer,
            )
        )
    return items


# --------------------------------------------------------------------------
# Multiple choice
# --------------------------------------------------------------------------


#: Words too common to signal that two definitions describe the same idea.
_STOPWORDS = {
    "a", "an", "the", "of", "to", "or", "and", "in", "on", "for", "with", "that",
    "you", "your", "someone", "something", "is", "are", "be", "not", "very",
    "used", "usually", "especially", "when", "who", "which", "it", "its", "as",
    "have", "has", "do", "does", "make", "makes", "made", "so", "but", "from",
    "by", "at", "this", "these", "there", "their", "them", "they", "people",
}


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _is_safe_distractor(target: VocabularyEntry, other: VocabularyEntry) -> bool:
    """Reject distractors that could defensibly also answer the definition cue.

    Near-synonyms are the failure mode here: asking "which word means
    'beautiful or pleasant to look at'" with both *attractive* and *pretty* on
    the list has two right answers, which breaks tick-based marking. Two cheap
    signals catch most of these — one definition naming the other's headword,
    and heavy content-word overlap between the two definitions.
    """
    target_definition = target.definition.lower()
    other_definition = other.definition.lower()

    if other.word.lower() in target_definition or target.word.lower() in other_definition:
        return False

    target_words = _content_words(target.definition)
    other_words = _content_words(other.definition)
    if not target_words or not other_words:
        return True
    overlap = target_words & other_words
    return len(overlap) < 2


def build_multiple_choice_items(unit: Unit, rng: random.Random) -> list[DraftItem]:
    """Definition-cue MCQs with same-part-of-speech distractors from the same unit."""
    entries = list(unit.vocabulary.all())
    by_pos: dict[str, list[VocabularyEntry]] = {}
    for entry in entries:
        by_pos.setdefault(entry.part_of_speech, []).append(entry)

    items: list[DraftItem] = []
    for entry in entries:
        if not _usable_for_definition_items(entry):
            continue
        pool = [
            other
            for other in by_pos.get(entry.part_of_speech, [])
            if other.word.lower() != entry.word.lower() and _is_safe_distractor(entry, other)
        ]
        if len(pool) < MCQ_OPTION_COUNT - 1:
            continue
        distractors = rng.sample(pool, MCQ_OPTION_COUNT - 1)
        options = [entry.word] + [d.word for d in distractors]
        rng.shuffle(options)
        correct_index = options.index(entry.word)
        items.append(
            DraftItem(
                unit_id=unit.id,
                question_type=QuestionType.MULTIPLE_CHOICE,
                payload={
                    "sentence": f'Which word means "{entry.definition.rstrip(".")}"?',
                    "options": options,
                    "correct_option": OPTION_LETTERS[correct_index],
                },
                model_answer=OPTION_LETTERS[correct_index],
                target_vocabulary_id=entry.id,
            )
        )
    return items


# --------------------------------------------------------------------------
# Odd one out
# --------------------------------------------------------------------------

#: Category names that are groupings of convenience rather than semantic fields,
#: so membership in them says nothing about a word's meaning.
_NON_SEMANTIC_CATEGORY_HINTS = (
    "prefix",
    "suffix",
    "word formation",
    "word famil",
    "phrasal verb",
    "collocation",
    "adjective ending",
    "different meaning",
    "part 1",
    "part 2",
)

ODD_ONE_OUT_GROUP_SIZE = 3
MAX_ODD_ONE_OUT_PER_UNIT = 6


def _semantic_key(name: str) -> str:
    """Normalise a category name so "Animals (Part 1)" and "(Part 2)" collide."""
    key = re.sub(r"\(.*?\)", "", name.lower())
    key = re.sub(r"\bpart\s*\d+\b", "", key)
    return re.sub(r"[^a-z]+", " ", key).strip()


def _is_semantic_category(name: str) -> bool:
    lowered = name.lower()
    return not any(hint in lowered for hint in _NON_SEMANTIC_CATEGORY_HINTS)


def _semantic_category_groups(
    entries,
) -> tuple[dict[int, list[VocabularyEntry]], dict[int, str]]:
    """Group vocabulary entries into their semantic categories, deduplicated by word.

    A word listed twice in one category (two senses, two parts of speech)
    would otherwise appear twice in the same set of options.
    """
    groups: dict[int, list[VocabularyEntry]] = {}
    names: dict[int, str] = {}
    seen_in_group: dict[int, set[str]] = {}
    for entry in entries:
        if entry.category is None or not _is_semantic_category(entry.category.name):
            continue
        seen = seen_in_group.setdefault(entry.category_id, set())
        if entry.word.lower() in seen:
            continue
        seen.add(entry.word.lower())
        groups.setdefault(entry.category_id, []).append(entry)
        names[entry.category_id] = entry.category.name
    return groups, names


def build_odd_one_out_items(unit: Unit, rng: random.Random) -> list[DraftItem]:
    """"Which word does not belong?" — three words from one semantic field, one from another.

    This is the only definition-free item type here, which matters because the
    grade 9 guide lists vocabulary with parts of speech but no glosses. The
    answer is unique as long as the two categories are genuinely different
    fields, so categories that merely group by word-formation pattern (prefixes,
    phrasal verbs) are excluded, and two categories that normalise to the same
    field ("Animals (Part 1)" / "(Part 2)") are never paired.

    Some units only have one usable semantic field of their own — not enough
    to contrast against internally. Rather than produce nothing, the single
    "odd" word for those units is borrowed from another unit in the same
    grade; the three-word family is still drawn entirely from `unit`, so the
    item still tests this unit's own vocabulary.
    """
    groups, names = _semantic_category_groups(unit.vocabulary.select_related("category"))
    usable = [cid for cid, entries in groups.items() if len(entries) >= ODD_ONE_OUT_GROUP_SIZE]
    if not usable:
        return []

    other_candidates = list(usable)
    if len(usable) < 2:
        sibling_entries = VocabularyEntry.objects.filter(
            unit__grade_id=unit.grade_id
        ).exclude(unit_id=unit.id).select_related("category")
        sibling_groups, sibling_names = _semantic_category_groups(sibling_entries)
        for cid, entries in sibling_groups.items():
            groups[cid] = entries
            names[cid] = sibling_names[cid]
            other_candidates.append(cid)

    if len(other_candidates) < 2:
        return []

    items: list[DraftItem] = []
    pairs = [(a, b) for a in usable for b in other_candidates if a != b]
    rng.shuffle(pairs)

    for home_id, other_id in pairs:
        if len(items) >= MAX_ODD_ONE_OUT_PER_UNIT:
            break
        if _semantic_key(names[home_id]) == _semantic_key(names[other_id]):
            continue

        home_words = {e.word.lower() for e in groups[home_id]}
        outsiders = [e for e in groups[other_id] if e.word.lower() not in home_words]
        if not outsiders:
            continue

        family = rng.sample(groups[home_id], ODD_ONE_OUT_GROUP_SIZE)
        odd = rng.choice(outsiders)
        options = [e.word for e in family] + [odd.word]
        rng.shuffle(options)
        correct_index = options.index(odd.word)

        items.append(
            DraftItem(
                unit_id=unit.id,
                question_type=QuestionType.ODD_ONE_OUT,
                payload={
                    "sentence": "Which word does not belong with the others?",
                    "options": options,
                    "correct_option": OPTION_LETTERS[correct_index],
                    "shared_category": names[home_id],
                },
                model_answer=OPTION_LETTERS[correct_index],
                target_vocabulary_id=odd.id,
            )
        )
    return items


# --------------------------------------------------------------------------
# Word formation
# --------------------------------------------------------------------------


def _strip_negative_prefix(word: str) -> str | None:
    """"unhappy" -> "happy". Returns None when no taught prefix applies."""
    lowered = word.lower()
    for prefix in sorted(NEGATIVE_PREFIXES, key=len, reverse=True):
        if not lowered.startswith(prefix):
            continue
        root = lowered[len(prefix) :]
        if len(root) < 3:
            continue
        return root
    return None


def _is_negation_of(entry: VocabularyEntry, root: str, root_entry: VocabularyEntry) -> bool:
    """Guard against accidental prefix matches such as *take* -> *mistake*.

    A real taught negation keeps the root's part of speech and says so in its
    own definition ("not friendly", "the opposite of ..."). Requiring both
    signals is strict, but a wrong word-formation item is worse than a missing
    one — the teacher would have to catch it while marking.
    """
    if not entry.definition:
        return False
    if entry.part_of_speech != root_entry.part_of_speech:
        return False
    definition = entry.definition.lower()
    return definition.startswith(("not ", "without ", "unable")) or "opposite of" in definition


def _pos_label(part_of_speech: str) -> str:
    return {
        PartOfSpeech.NOUN: "noun",
        PartOfSpeech.VERB: "verb",
        PartOfSpeech.ADJECTIVE: "adjective",
        PartOfSpeech.ADVERB: "adverb",
    }.get(part_of_speech, "word")


def build_word_formation_items(unit: Unit, rng: random.Random) -> list[DraftItem]:
    """Two sources: prefixed forms whose root is also in the syllabus, and word families.

    A prefixed form only becomes an item when its root word actually appears in
    the same grade — otherwise the student is being asked to derive from a word
    they have not been taught.
    """
    entries = list(unit.vocabulary.all())
    grade_lemmas = {
        e.word.lower()
        for e in VocabularyEntry.objects.filter(unit__grade_id=unit.grade_id).only("word")
    }

    items: list[DraftItem] = []
    used: set[tuple[str, str]] = set()

    roots_by_word = {
        e.word.lower(): e
        for e in VocabularyEntry.objects.filter(unit__grade_id=unit.grade_id).only(
            "word", "part_of_speech"
        )
    }

    for entry in entries:
        if not _is_single_word(entry.word):
            continue

        root = _strip_negative_prefix(entry.word)
        root_entry = roots_by_word.get(root) if root else None
        if (
            root
            and root in grade_lemmas
            and root_entry is not None
            and _is_negation_of(entry, root, root_entry)
            and (root, entry.word.lower()) not in used
        ):
            used.add((root, entry.word.lower()))
            cue = entry.definition.rstrip(".")
            items.append(
                DraftItem(
                    unit_id=unit.id,
                    question_type=QuestionType.WORD_FORMATION,
                    payload={
                        "sentence_with_gap": (
                            f'Form a word from {root.upper()} that means "{cue}": ________'
                        ),
                        "root_word": root,
                        "correct_form": entry.word,
                        "target_pos": entry.part_of_speech,
                        "cue": cue,
                        "cue_frame": True,
                    },
                    model_answer=entry.word,
                    target_vocabulary_id=entry.id,
                )
            )

    # Word families: "achieve (v) / achievement (n)" gives a derivation whose
    # direction is fixed by the requested part of speech.
    families: dict[str, list[VocabularyEntry]] = {}
    for entry in entries:
        if entry.word_family:
            families.setdefault(entry.word_family, []).append(entry)

    for family_key, members in families.items():
        root = next((m for m in members if m.word.lower() == family_key), None)
        if root is None:
            continue
        for member in members:
            # `record` appears as both noun and verb: same word, different entries,
            # so a pk comparison alone lets a root through as its own answer.
            if member.pk == root.pk or member.word.lower() == root.word.lower():
                continue
            if not _is_single_word(member.word):
                continue
            if (root.word.lower(), member.word.lower()) in used:
                continue
            used.add((root.word.lower(), member.word.lower()))
            items.append(
                DraftItem(
                    unit_id=unit.id,
                    question_type=QuestionType.WORD_FORMATION,
                    payload={
                        "sentence_with_gap": (
                            f"Write the {_pos_label(member.part_of_speech)} formed from "
                            f"{root.word.upper()}: ________"
                        ),
                        "root_word": root.word,
                        "correct_form": member.word,
                        "target_pos": member.part_of_speech,
                        "cue": f"{_pos_label(member.part_of_speech)} form",
                        "cue_frame": True,
                    },
                    model_answer=member.word,
                    target_vocabulary_id=member.id,
                )
            )

    return _drop_ambiguous_word_formation(items)


def _drop_ambiguous_word_formation(items: list[DraftItem]) -> list[DraftItem]:
    """Reject items where one root + one target part of speech has two answers.

    ``entertain`` yields both *entertainer* and *entertainment* as nouns; asking
    for "the noun from ENTERTAIN" then has two right answers and cannot be
    tick-marked, so neither version is kept.
    """
    counts: dict[tuple[str, str], int] = {}
    for item in items:
        key = (item.payload["root_word"].lower(), item.payload["target_pos"])
        counts[key] = counts.get(key, 0) + 1
    return [
        item
        for item in items
        if counts[(item.payload["root_word"].lower(), item.payload["target_pos"])] == 1
    ]


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

#: Keyed by the label the --type flag accepts, not by question type, because
#: two builders both emit multiple-choice items.
BUILDERS = {
    "matching": build_matching_items,
    "multiple_choice": build_multiple_choice_items,
    "odd_one_out": build_odd_one_out_items,
    "word_formation": build_word_formation_items,
}


def generate_for_unit(unit: Unit, question_types: list[str] | None = None) -> list[DraftItem]:
    """Generate every deterministic item type for one unit.

    The RNG is seeded from the unit so repeated runs are identical.
    """
    seed = int(hashlib.sha256(f"unit-{unit.pk}".encode()).hexdigest()[:8], 16)
    wanted = question_types or list(BUILDERS)
    items: list[DraftItem] = []
    for question_type in wanted:
        builder = BUILDERS.get(question_type)
        if builder is None:
            continue
        items.extend(builder(unit, random.Random(seed)))
    return items
