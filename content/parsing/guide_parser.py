"""Parses the grade 9/10/11 vocabulary-and-grammar guides into plain dataclasses.

The three guides were written by different hands and use three different
layouts, so the parser is deliberately shape-driven rather than grade-driven:
it recognises the *constructs* below wherever they appear, which means a guide
that mixes styles still imports correctly.

Constructs handled
------------------
Unit headings   ``## Unit 1`` / ``## Unit 1: Title | Grammar``
Vocabulary      ``### Vocabulary`` / ``### I. Vocabulary`` / ``### Vocabulary: Name``
                plus the topical sections ``### Phrasal Verbs``,
                ``### Word Formation: ...``, ``### Word Families``, etc.
Grammar         ``### Grammar: Name`` / ``### II. Grammar: Name``
Categories      ``#### Name`` (g10) or ``*   **Name**:`` (g9)
Entries         ``| **word** | pos | definition |``   (g10, g11 tables)
                ``*   **word** (pos): definition``     (g11 bullets)
                ``*   **word**: definition``           (g11 phrasal verbs)
                ``*   word *(pos)*``                   (g9 bullets)
                ``*   **a** (v) / **b** (n)``          (g11 word families)

This module has no Django imports beyond the PartOfSpeech choices, so it is
testable without a database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from content.models import PartOfSpeech

# --------------------------------------------------------------------------
# Part-of-speech normalisation
# --------------------------------------------------------------------------

#: Every spelling of a part of speech seen across the three guides.
POS_ALIASES = {
    "n": PartOfSpeech.NOUN,
    "noun": PartOfSpeech.NOUN,
    "nouns": PartOfSpeech.NOUN,
    "v": PartOfSpeech.VERB,
    "vb": PartOfSpeech.VERB,
    "verb": PartOfSpeech.VERB,
    "verbs": PartOfSpeech.VERB,
    "adj": PartOfSpeech.ADJECTIVE,
    "adjective": PartOfSpeech.ADJECTIVE,
    "adjectives": PartOfSpeech.ADJECTIVE,
    "adv": PartOfSpeech.ADVERB,
    "adverb": PartOfSpeech.ADVERB,
    "adverbs": PartOfSpeech.ADVERB,
    "prep": PartOfSpeech.PREPOSITION,
    "preposition": PartOfSpeech.PREPOSITION,
    "conj": PartOfSpeech.CONJUNCTION,
    "conjunction": PartOfSpeech.CONJUNCTION,
    "det": PartOfSpeech.DETERMINER,
    "determiner": PartOfSpeech.DETERMINER,
    "pron": PartOfSpeech.PRONOUN,
    "prn": PartOfSpeech.PRONOUN,
    "pronoun": PartOfSpeech.PRONOUN,
    "reflexive pronoun": PartOfSpeech.PRONOUN,
    "pv": PartOfSpeech.PHRASAL_VERB,
    "phr v": PartOfSpeech.PHRASAL_VERB,
    "phrasal verb": PartOfSpeech.PHRASAL_VERB,
    "phr": PartOfSpeech.PHRASE,
    "phrase": PartOfSpeech.PHRASE,
    "expression": PartOfSpeech.PHRASE,
    "idiom": PartOfSpeech.PHRASE,
    "collocation": PartOfSpeech.PHRASE,
    "verb phrase": PartOfSpeech.VERB_PHRASE,
    "phrasal": PartOfSpeech.PHRASAL_VERB,
    "noun phrase": PartOfSpeech.PHRASE,
    "adjective phrase": PartOfSpeech.PHRASE,
    "adverb phrase": PartOfSpeech.PHRASE,
    "prepositional phrase": PartOfSpeech.PHRASE,
}


def normalise_pos(raw: str | None) -> str:
    """Map a guide's POS label onto a PartOfSpeech value, defaulting to OTHER.

    Dual labels such as ``noun/adjective`` resolve to the first listed sense,
    which is the one the guide is teaching in that unit.
    """
    if not raw:
        return PartOfSpeech.OTHER
    key = raw.strip().strip(".").lower()
    key = re.sub(r"[*`_]", "", key)
    key = re.sub(r"\s+", " ", key).strip()
    if key in POS_ALIASES:
        return POS_ALIASES[key]
    for separator in ("/", " or ", ","):
        if separator in key:
            first = key.split(separator, 1)[0].strip()
            if first in POS_ALIASES:
                return POS_ALIASES[first]
    return PartOfSpeech.OTHER


# --------------------------------------------------------------------------
# Parsed shapes (deliberately not Django models — see module docstring)
# --------------------------------------------------------------------------


@dataclass
class ParsedEntry:
    word: str
    part_of_speech: str = PartOfSpeech.OTHER
    definition: str = ""
    sense_note: str = ""
    category: str = ""
    word_family: str = ""

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.word.lower(), self.part_of_speech, self.sense_note.lower())


@dataclass
class ParsedCategory:
    name: str
    order: int = 0


@dataclass
class ParsedGrammar:
    name: str
    body: str = ""
    sample_sentences: list[str] = field(default_factory=list)


@dataclass
class ParsedUnit:
    number: int
    title: str = ""
    theme: str = ""
    categories: list[ParsedCategory] = field(default_factory=list)
    entries: list[ParsedEntry] = field(default_factory=list)
    grammar: ParsedGrammar | None = None


# --------------------------------------------------------------------------
# Line patterns
# --------------------------------------------------------------------------

RE_UNIT = re.compile(r"^##\s+Unit\s+(\d+)\s*[:.\-–—]?\s*(.*)$", re.IGNORECASE)
RE_H3 = re.compile(r"^###\s+(.*)$")
RE_H4 = re.compile(r"^####\s+(.*)$")

#: Strips the "I." / "II." roman-numeral prefixes used in the grade 10 guide.
RE_ROMAN_PREFIX = re.compile(r"^(?:[IVXivx]+)\s*[.)]\s*")
#: Strips the "1." / "2." numeric prefixes used in grade 10 sub-headings.
RE_NUM_PREFIX = re.compile(r"^\d+\s*[.)]\s*")

RE_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
RE_TABLE_SEPARATOR = re.compile(r"^[\s|:\-]+$")

#: ``*   **Category Name**:``  — a bold bullet ending in a colon, no definition.
RE_CATEGORY_BULLET = re.compile(r"^\s*[*\-+]\s+\*\*(.+?)\*\*\s*:?\s*$")

#: ``*   **word** (pos): definition``  and ``*   **word**: definition``
RE_BOLD_ENTRY = re.compile(
    r"^\s*[*\-+]\s+\*\*(?P<word>.+?)\*\*"
    r"(?:\s*\((?P<pos>[^)]*)\))?"
    r"\s*:\s*(?P<definition>.+)$"
)

#: ``*   word *(pos)*``  — the grade 9 indented bullet form.
RE_PLAIN_ENTRY = re.compile(r"^\s*[*\-+]\s+(?P<word>[^*].*?)\s*\*\((?P<pos>[^)]*)\)\*\s*\.?\s*$")

#: ``*   **achieve** (v) / **achievement** (n)``  — word-family lines.
RE_FAMILY_MEMBER = re.compile(r"\*\*(?P<word>[^*]+?)\*\*\s*\((?P<pos>[^)]*)\)")

#: ``change [= transport]``  — the grade 9 disambiguating gloss.
RE_SENSE_NOTE = re.compile(r"^(?P<word>.+?)\s*\[(?P<note>[^\]]+)\]\s*$")

#: Sentences inside ``(e.g., *...*)`` or plain ``*...*`` emphasis in grammar bodies.
RE_EXAMPLE_EMPHASIS = re.compile(r"\*([^*\n]{12,240}?)\*")

#: Section headings that introduce vocabulary rather than grammar.
VOCAB_HEADING_PREFIXES = (
    "vocabulary",
    "phrasal verb",
    "word formation",
    "word famil",
    "collocation",
    "prefix",
    "suffix",
    "reporting verb",
    "strong adjective",
    "preposition",
    "expressions",
    "idioms",
)

#: Heading text signalling that every entry beneath it is a phrasal verb.
PHRASAL_HEADING_HINT = "phrasal verb"
FAMILY_HEADING_HINT = "word famil"


def _strip_markdown(text: str) -> str:
    """Remove bold/italic/code markers and collapse whitespace."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _clean_heading(text: str) -> str:
    text = RE_ROMAN_PREFIX.sub("", text.strip())
    text = RE_NUM_PREFIX.sub("", text)
    return _strip_markdown(text)


def _split_sense_note(word: str) -> tuple[str, str]:
    match = RE_SENSE_NOTE.match(word)
    if not match:
        return word, ""
    return match.group("word").strip(), match.group("note").strip()


def _extract_sample_sentences(body: str) -> list[str]:
    """Pull example sentences out of a grammar body.

    Only emphasised runs that actually look like sentences are kept — a form
    skeleton such as ``Subject + verb-s`` is a pattern, not an example, and
    would pollute the few-shot references handed to the generator.
    """
    sentences: list[str] = []
    seen: set[str] = set()
    for raw in RE_EXAMPLE_EMPHASIS.findall(body):
        candidate = _strip_markdown(raw).strip(" .,;:").strip()
        if not candidate:
            continue
        # Must end like a sentence and contain a couple of words.
        if len(candidate.split()) < 4:
            continue
        if "+" in candidate or "/" in candidate or "→" in candidate:
            continue
        if not re.search(r"[a-z]", candidate):
            continue
        candidate = candidate.rstrip(".") + "."
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        sentences.append(candidate)
    return sentences


def _parse_table_row(line: str) -> tuple[str, str, str] | None:
    """Return (word, pos, definition) for a markdown table row, or None."""
    match = RE_TABLE_ROW.match(line)
    if not match:
        return None
    inner = match.group(1)
    if RE_TABLE_SEPARATOR.match(inner):
        return None
    cells = [c.strip() for c in inner.split("|")]
    if len(cells) < 2:
        return None
    word = _strip_markdown(cells[0])
    pos = cells[1]
    definition = _strip_markdown(cells[2]) if len(cells) > 2 else ""
    if not word:
        return None
    # Header rows vary in their first cell ("Word", "Phrase", "Phrase/Word"),
    # so identify them by the *type* column label instead.
    if _strip_markdown(pos).lower() in {"type", "part of speech", "pos", "meaning", "definition"}:
        return None
    if word.lower() in {"word", "vocabulary word", "words", "term", "vocabulary", "phrase"}:
        return None
    return word, pos, definition


class _UnitBuilder:
    """Accumulates one unit's parsed content while walking the guide's lines."""

    def __init__(self, number: int, heading_tail: str):
        self.unit = ParsedUnit(number=number)
        title = _clean_heading(heading_tail)
        # "Reported Commands (Grammar Focus)" -> keep as title, it is all we have.
        self.unit.title = title
        self.unit.theme = title.split("|")[0].split("&")[0].strip() if title else ""

        self._seen_entries: set[tuple[str, str, str]] = set()
        self._seen_categories: set[str] = set()
        self._category: str = ""
        self._in_vocabulary = False
        self._forced_pos: str | None = None
        self._is_family_section = False
        self._grammar_name: str | None = None
        self._grammar_lines: list[str] = []

    # -- section transitions -------------------------------------------------

    def start_section(self, heading: str) -> None:
        cleaned = _clean_heading(heading)
        lowered = cleaned.lower()

        if lowered.startswith("grammar"):
            self._flush_grammar()
            self._in_vocabulary = False
            self._grammar_name = cleaned.split(":", 1)[1].strip() if ":" in cleaned else cleaned
            self._grammar_lines = []
            return

        if any(lowered.startswith(prefix) for prefix in VOCAB_HEADING_PREFIXES):
            self._flush_grammar()
            self._in_vocabulary = True
            self._is_family_section = FAMILY_HEADING_HINT in lowered
            self._forced_pos = (
                PartOfSpeech.PHRASAL_VERB if PHRASAL_HEADING_HINT in lowered else None
            )
            # "Vocabulary: Shopping List" -> category "Shopping List";
            # a bare "Vocabulary" heading leaves the category to be set by ####.
            if ":" in cleaned:
                self.add_category(cleaned.split(":", 1)[1].strip())
            elif lowered != "vocabulary":
                self.add_category(cleaned)
            else:
                self._category = ""
            return

        # An unrecognised H3 ends whatever section we were in.
        self._flush_grammar()
        self._in_vocabulary = False

    def start_subsection(self, heading: str) -> None:
        """An H4. Inside vocabulary it names a category; inside grammar it is body text."""
        if self._in_vocabulary:
            self.add_category(_clean_heading(heading))
        elif self._grammar_name is not None:
            self._grammar_lines.append(heading)

    def add_category(self, name: str) -> None:
        if not name:
            return
        self._category = name
        if name not in self._seen_categories:
            self._seen_categories.add(name)
            self.unit.categories.append(ParsedCategory(name=name, order=len(self.unit.categories)))

    # -- content -------------------------------------------------------------

    def add_line(self, line: str) -> None:
        if self._grammar_name is not None:
            self._grammar_lines.append(line)
            return
        if not self._in_vocabulary:
            return

        if self._is_family_section and self._try_word_family(line):
            return
        if self._try_table_row(line):
            return
        if self._try_category_bullet(line):
            return
        if self._try_bold_entry(line):
            return
        self._try_plain_entry(line)

    def _add_entry(self, entry: ParsedEntry) -> None:
        if not entry.word or len(entry.word) > 120:
            return
        # "-ed endings", "-ing forms": suffix labels used as bullet headers in
        # grammar-flavoured vocabulary sections, not headwords.
        if entry.word.startswith("-") and " " in entry.word:
            return
        if entry.dedupe_key in self._seen_entries:
            return
        self._seen_entries.add(entry.dedupe_key)
        entry.category = entry.category or self._category
        self.unit.entries.append(entry)

    def _try_table_row(self, line: str) -> bool:
        parsed = _parse_table_row(line)
        if parsed is None:
            return RE_TABLE_ROW.match(line) is not None  # consumed separator/header
        word, pos, definition = parsed
        word, sense = _split_sense_note(word)
        self._add_entry(
            ParsedEntry(
                word=word,
                part_of_speech=self._forced_pos or normalise_pos(pos),
                definition=definition,
                sense_note=sense,
            )
        )
        return True

    def _try_category_bullet(self, line: str) -> bool:
        match = RE_CATEGORY_BULLET.match(line)
        if not match:
            return False
        self.add_category(_strip_markdown(match.group(1)))
        return True

    def _try_bold_entry(self, line: str) -> bool:
        match = RE_BOLD_ENTRY.match(line)
        if not match:
            return False
        word = _strip_markdown(match.group("word"))
        word, sense = _split_sense_note(word)
        pos = match.group("pos")
        self._add_entry(
            ParsedEntry(
                word=word,
                part_of_speech=self._forced_pos or normalise_pos(pos),
                definition=_strip_markdown(match.group("definition")),
                sense_note=sense,
            )
        )
        return True

    def _try_plain_entry(self, line: str) -> bool:
        match = RE_PLAIN_ENTRY.match(line)
        if not match:
            return False
        word = _strip_markdown(match.group("word"))
        word, sense = _split_sense_note(word)
        self._add_entry(
            ParsedEntry(
                word=word,
                part_of_speech=self._forced_pos or normalise_pos(match.group("pos")),
                sense_note=sense,
            )
        )
        return True

    def _try_word_family(self, line: str) -> bool:
        """``*   **achieve** (v) / **achievement** (n)`` -> one entry per member."""
        members = RE_FAMILY_MEMBER.findall(line)
        if len(members) < 2:
            return False
        family_key = _strip_markdown(members[0][0]).lower()
        for raw_word, raw_pos in members:
            word = _strip_markdown(raw_word)
            self._add_entry(
                ParsedEntry(
                    word=word,
                    part_of_speech=normalise_pos(raw_pos),
                    word_family=family_key,
                )
            )
        return True

    # -- finishing -----------------------------------------------------------

    def _flush_grammar(self) -> None:
        if self._grammar_name is None:
            return
        body = "\n".join(self._grammar_lines).strip()
        self.unit.grammar = ParsedGrammar(
            name=self._grammar_name,
            body=body,
            sample_sentences=_extract_sample_sentences(body),
        )
        self._grammar_name = None
        self._grammar_lines = []

    def build(self) -> ParsedUnit:
        self._flush_grammar()
        # The grade 9 guide uses bare "## Unit 5" headings with no title. Fall
        # back to the unit's own content so teachers still see something
        # meaningful in the unit picker.
        if not self.unit.title and self.unit.grammar:
            self.unit.title = self.unit.grammar.name
        if not self.unit.theme and self.unit.categories:
            self.unit.theme = self.unit.categories[0].name
        return self.unit


def parse_guide(text: str) -> list[ParsedUnit]:
    """Parse a full guide document into its units.

    Content before the first ``## Unit N`` heading (title, intro, table of
    contents) is ignored.
    """
    units: list[ParsedUnit] = []
    builder: _UnitBuilder | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        unit_match = RE_UNIT.match(line)
        if unit_match:
            if builder is not None:
                units.append(builder.build())
            builder = _UnitBuilder(int(unit_match.group(1)), unit_match.group(2))
            continue

        if builder is None:
            continue  # pre-unit preamble

        if line.startswith("## "):
            # A non-unit H2 (e.g. "## Table of Contents") ends the current unit.
            units.append(builder.build())
            builder = None
            continue

        h3 = RE_H3.match(line)
        if h3:
            builder.start_section(h3.group(1))
            continue

        h4 = RE_H4.match(line)
        if h4:
            builder.start_subsection(h4.group(1))
            continue

        builder.add_line(line)

    if builder is not None:
        units.append(builder.build())

    return units
