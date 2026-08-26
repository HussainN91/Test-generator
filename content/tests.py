"""Parser tests, written against the three real guide formats.

Fixtures below are verbatim-shaped excerpts of the actual source files, so a
regression in the parser shows up here rather than after a 2,000-row import.
"""

from django.test import SimpleTestCase

from content.models import PartOfSpeech
from content.parsing.guide_parser import parse_guide

G9 = """# Grade 9 English Vocabulary and Grammar Guide

Intro prose that must be ignored.

---

## Unit 1
### Vocabulary
*   **Adjectives of Personality**:
    *   active *(adjective)*
    *   creative *(adjective)*
*   **Personal Details**:
    *   email address *(noun)*

### Grammar: Present Simple & Present Continuous
*   **Present Simple**: Used for things that are always true.
    *   *Form*: Subject + Verb (e.g., *learns, works*)

## Unit 2
### Vocabulary
*   **Change as a Verb and Noun**:
    *   change [= transport] *(verb)*
    *   change schools *(verb phrase)*

### Grammar: Past Simple Passive
*   *Form*: **Subject + was/were + past participle** (e.g., *This museum was built 150 years ago.*).
"""

G10 = """# Grade 10 Guide

## Table of Contents
*   Unit 1

## Unit 1: Describing People & Prefixes | Present Simple and Continuous

### I. Vocabulary

#### Describing People
| Word | Type | Definition |
| :--- | :--- | :--- |
| **attractive** | adj | Beautiful or pleasant to look at |
| **in early thirties** | phr | Aged between 30 and 34 |

#### Prefixes: Un-, In-, Im-
| Word | Type | Definition |
| :--- | :--- | :--- |
| **impatient** | adj | Easily annoyed |

### II. Grammar: Present Simple and Continuous

#### 1. Present Simple
*   **Regular habits**: (e.g., *I walk to school every day.*)

## Unit 17: Reported Commands (Grammar Focus)

*(Note: The source text contains no specific vocabulary list designated for Unit 17).*

### I. Grammar: Reported Commands

#### 1. Form and Structures
*   **Positive**: *Dad told me to open the door.*
"""

G11 = """# Grade 11 Guide

## Unit 1: Shopping & Countable/Uncountable Nouns

### Vocabulary: Shopping List
| Vocabulary Word | Part of Speech | Definition |
| :--- | :--- | :--- |
| **charge** | v | to ask an amount of money for something |
| **charges** | n | the amount of money that you have to pay |
| **send sth back** | pv | to return something to the person who sent it |

### Word Formation: Prefixes `un-` and `dis-`
*   **disagree** (v): to have a different opinion from someone else
*   **unhappy** (adj): sad

### Grammar: Countable & Uncountable Nouns; Determiners
#### Countable Nouns
*   Can be singular or plural.

## Unit 7: Music & Present Perfect vs. Past Simple

### Word Families
*   **achieve** (v) / **achievement** (n)
*   **music** (n) / **musical** (adj) / **musician** (n)

### Phrasal Verbs
*   **blow away**: to be moved on a current of air

### Grammar: Present Perfect and Past Simple
*   Example: *I have seen that film.*
"""


class Grade9FormatTests(SimpleTestCase):
    def setUp(self):
        self.units = parse_guide(G9)

    def test_finds_both_units(self):
        self.assertEqual([u.number for u in self.units], [1, 2])

    def test_bold_bullet_is_a_category_not_a_word(self):
        categories = [c.name for c in self.units[0].categories]
        self.assertEqual(categories, ["Adjectives of Personality", "Personal Details"])

    def test_parses_word_and_pos(self):
        words = {(e.word, e.part_of_speech) for e in self.units[0].entries}
        self.assertIn(("active", PartOfSpeech.ADJECTIVE), words)
        self.assertIn(("email address", PartOfSpeech.NOUN), words)

    def test_bracket_gloss_becomes_sense_note_not_part_of_word(self):
        entry = next(e for e in self.units[1].entries if e.word == "change")
        self.assertEqual(entry.sense_note, "= transport")
        self.assertEqual(entry.part_of_speech, PartOfSpeech.VERB)

    def test_verb_phrase_pos(self):
        entry = next(e for e in self.units[1].entries if e.word == "change schools")
        self.assertEqual(entry.part_of_speech, PartOfSpeech.VERB_PHRASE)

    def test_grammar_point_name_and_body(self):
        gp = self.units[0].grammar
        self.assertEqual(gp.name, "Present Simple & Present Continuous")
        self.assertIn("Subject + Verb", gp.body)

    def test_sample_sentences_extracted_from_examples(self):
        sentences = self.units[1].grammar.sample_sentences
        self.assertIn("This museum was built 150 years ago.", sentences)


class Grade10FormatTests(SimpleTestCase):
    def setUp(self):
        self.units = parse_guide(G10)

    def test_skips_table_of_contents(self):
        self.assertEqual([u.number for u in self.units], [1, 17])

    def test_unit_title_excludes_number_prefix(self):
        self.assertEqual(
            self.units[0].title, "Describing People & Prefixes | Present Simple and Continuous"
        )

    def test_table_rows_parsed_with_definitions(self):
        entry = next(e for e in self.units[0].entries if e.word == "attractive")
        self.assertEqual(entry.part_of_speech, PartOfSpeech.ADJECTIVE)
        self.assertEqual(entry.definition, "Beautiful or pleasant to look at")

    def test_header_and_separator_rows_are_not_entries(self):
        words = [e.word for e in self.units[0].entries]
        self.assertNotIn("Word", words)
        self.assertNotIn(":---", words)

    def test_multi_word_phrase_entry(self):
        entry = next(e for e in self.units[0].entries if e.word == "in early thirties")
        self.assertEqual(entry.part_of_speech, PartOfSpeech.PHRASE)

    def test_categories_come_from_h4(self):
        self.assertEqual(
            [c.name for c in self.units[0].categories],
            ["Describing People", "Prefixes: Un-, In-, Im-"],
        )

    def test_roman_numeral_prefix_stripped_from_grammar_name(self):
        self.assertEqual(self.units[0].grammar.name, "Present Simple and Continuous")

    def test_grammar_only_unit_has_no_vocabulary(self):
        unit17 = self.units[1]
        self.assertEqual(unit17.entries, [])
        self.assertEqual(unit17.grammar.name, "Reported Commands")


class Grade11FormatTests(SimpleTestCase):
    def setUp(self):
        self.units = parse_guide(G11)

    def test_vocabulary_heading_carries_category_name(self):
        self.assertIn("Shopping List", [c.name for c in self.units[0].categories])

    def test_short_pos_codes_expand(self):
        by_word = {e.word: e for e in self.units[0].entries}
        self.assertEqual(by_word["charge"].part_of_speech, PartOfSpeech.VERB)
        self.assertEqual(by_word["charges"].part_of_speech, PartOfSpeech.NOUN)
        self.assertEqual(by_word["send sth back"].part_of_speech, PartOfSpeech.PHRASAL_VERB)

    def test_inline_bullet_definition_format(self):
        entry = next(e for e in self.units[0].entries if e.word == "disagree")
        self.assertEqual(entry.part_of_speech, PartOfSpeech.VERB)
        self.assertEqual(entry.definition, "to have a different opinion from someone else")

    def test_word_family_line_expands_to_one_entry_per_form(self):
        unit7 = self.units[1]
        family = {e.word: e for e in unit7.entries if e.word_family == "achieve"}
        self.assertEqual(set(family), {"achieve", "achievement"})
        self.assertEqual(family["achievement"].part_of_speech, PartOfSpeech.NOUN)

    def test_three_member_word_family(self):
        unit7 = self.units[1]
        family = {e.word for e in unit7.entries if e.word_family == "music"}
        self.assertEqual(family, {"music", "musical", "musician"})

    def test_phrasal_verb_section_sets_pos(self):
        unit7 = self.units[1]
        entry = next(e for e in unit7.entries if e.word == "blow away")
        self.assertEqual(entry.part_of_speech, PartOfSpeech.PHRASAL_VERB)


class DeduplicationTests(SimpleTestCase):
    def test_same_word_twice_in_one_unit_is_deduplicated(self):
        text = """## Unit 1
### Vocabulary
*   **A**:
    *   funny *(adjective)*
*   **B**:
    *   funny *(adjective)*

### Grammar: Test Point
*   body
"""
        unit = parse_guide(text)[0]
        self.assertEqual([e.word for e in unit.entries], ["funny"])

    def test_same_word_different_pos_kept_separately(self):
        text = """## Unit 1
### Vocabulary
*   **A**:
    *   change *(noun)*
    *   change *(verb)*

### Grammar: Test Point
*   body
"""
        unit = parse_guide(text)[0]
        self.assertEqual(len(unit.entries), 2)
