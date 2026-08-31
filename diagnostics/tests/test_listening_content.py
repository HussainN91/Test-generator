"""extract_question_content, checked against the real source file.

Every fixture here comes from the real clip bodies (via split_clips against
the actual .md, exactly as import_listening.py sees them) rather than
hand-typed synthetic text, because this extraction is exactly the kind
where a synthetic example can pass while missing a real formatting quirk -
see test_extraction_keys.py and test_extraction_worksheets.py for the same
convention already used by the neighbouring extractors.
"""

from unittest import mock

from django.conf import settings
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.extraction import listening_content
from diagnostics.extraction.listening_content import extract_question_content
from diagnostics.extraction.worksheets import split_clips

LISTENING_MD = settings.DIAGNOSTICS_SOURCE_DIR / "Listening Question Bank -2026 EC.md"


class RealClipsMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not LISTENING_MD.exists():
            raise AssertionError(f"Source file missing: {LISTENING_MD}")
        cls.bodies = split_clips(LISTENING_MD.read_text(encoding="utf-8"))


class PictureExtractionTests(RealClipsMixin, TestCase):
    """Clip 1: one question line per position, no text options needed."""

    def test_first_two_questions(self):
        result = extract_question_content(1, TaskType.PICTURE, self.bodies[1])
        self.assertEqual(len(result), 5)
        self.assertEqual(
            result[0],
            {"stem": "Which dish did Mark cook in the competition?", "options": []},
        )
        self.assertEqual(
            result[1],
            {"stem": "Where is the girl’s book now?", "options": []},
        )

    def test_all_five_have_no_options(self):
        result = extract_question_content(1, TaskType.PICTURE, self.bodies[1])
        for item in result:
            self.assertEqual(item["options"], [])
            self.assertTrue(item["stem"])
            self.assertNotIn("Clip 1, question", item["stem"])


class Mcq3ExtractionTests(RealClipsMixin, TestCase):
    """Clip 2: a question line then three lettered option lines."""

    def test_first_two_questions(self):
        result = extract_question_content(2, TaskType.MCQ3, self.bodies[2])
        self.assertEqual(len(result), 5)
        self.assertEqual(
            result[0],
            {
                "stem": "Simon’s mum decided to take him to the climbing centre because",
                "options": [
                    "she had enjoyed going there.",
                    "her friend had recommended it.",
                    "Simon had been there with his school.",
                ],
            },
        )
        self.assertEqual(
            result[1],
            {
                "stem": "Before he went to the centre, Simon was",
                "options": [
                    "worried about going climbing there.",
                    "interested in seeing the climbing wall.",
                    "disappointed to hear it was all indoors.",
                ],
            },
        )

    def test_all_five_have_three_options(self):
        result = extract_question_content(2, TaskType.MCQ3, self.bodies[2])
        for item in result:
            self.assertEqual(len(item["options"]), 3)


class TrueFalseExtractionTests(RealClipsMixin, TestCase):
    """Clip 4: a markdown table, one row per question."""

    def test_first_two_questions(self):
        result = extract_question_content(4, TaskType.TRUE_FALSE, self.bodies[4])
        self.assertEqual(len(result), 5)
        self.assertEqual(
            result[0],
            {
                "stem": (
                    "Lucas thinks Candy Floss gave a great performance "
                    "during the concert."
                ),
                "options": ["YES", "NO"],
            },
        )
        self.assertEqual(
            result[1],
            {
                "stem": "Claire feels the band’s dancing was better in the summer.",
                "options": ["YES", "NO"],
            },
        )

    def test_all_five_have_yes_no_options(self):
        result = extract_question_content(4, TaskType.TRUE_FALSE, self.bodies[4])
        for item in result:
            self.assertEqual(item["options"], ["YES", "NO"])


class GapFillExtractionTests(RealClipsMixin, TestCase):
    """Clip 3: one continuous cloze passage with 5 numbered blanks."""

    def test_first_two_questions(self):
        result = extract_question_content(3, TaskType.GAP_FILL, self.bodies[3])
        self.assertEqual(len(result), 5)
        self.assertEqual(
            result[0],
            {
                "stem": "Caspar’s mother dances across a ______ in the circus.",
                "options": [],
            },
        )
        self.assertEqual(
            result[1],
            {
                "stem": (
                    "Caspar’s brother is in an act where as many as "
                    "______ people balance on a motorbike."
                ),
                "options": [],
            },
        )

    def test_all_five_sentences(self):
        # Confirms the glued "voice. Caspar starts" / ". There are no
        # animals" boundaries are all found and that the filler sentence
        # with no blank ("There are no animals...") is dropped.
        result = extract_question_content(3, TaskType.GAP_FILL, self.bodies[3])
        stems = [item["stem"] for item in result]
        self.assertEqual(
            stems,
            [
                "Caspar’s mother dances across a ______ in the circus.",
                "Caspar’s brother is in an act where as many as "
                "______ people balance on a motorbike.",
                "Caspar’s dad is a good circus boss because he is "
                "______ and has a strong voice.",
                "Caspar starts the show by marching in front of the ______.",
                "One of Caspar’s jobs is selling ______.",
            ],
        )
        for item in result:
            self.assertEqual(item["options"], [])


class GapFillClip18Tests(RealClipsMixin, TestCase):
    """Clip 18: a second real cloze passage, with a £ blank and a period
    glued straight onto the following capitalised sentence with no space
    at all ("...secretary.Each theatre ticket...")."""

    def test_all_five_sentences(self):
        result = extract_question_content(18, TaskType.GAP_FILL, self.bodies[18])
        stems = [item["stem"] for item in result]
        self.assertEqual(
            stems,
            [
                "Meet at 6.00 p.m. at the ______ of the school.",
                "The name of the play is ______.",
                "Each theatre ticket will cost £______.",
                "After the theatre – have ______ and coffee.",
                "On the return journey, the coach will stop at the "
                "______ and then the school.",
            ],
        )
        for item in result:
            self.assertEqual(item["options"], [])


class GapFillClip19Tests(RealClipsMixin, TestCase):
    """Clip 19: the source itself mislabels the second blank "(**3**)"
    instead of "(**2**)" (the real marker run is 1, 3, 3, 4, 5 - there is
    no "2" anywhere in the raw text). Blanks must be matched by the order
    they appear in, not by the digit printed inside the marker, or this
    clip's five questions come out misaligned."""

    def test_all_five_sentences_despite_the_mislabelled_marker(self):
        result = extract_question_content(19, TaskType.GAP_FILL, self.bodies[19])
        stems = [item["stem"] for item in result]
        self.assertEqual(
            stems,
            [
                "The cinema is surrounded by ______ and there are "
                "beautiful views.",
                "It’s possible to watch the ______ during a film.",
                "Cinema visitors are advised to take a ______ with "
                "them to sit on.",
                "The cinema is ______ kilometres from the city if you "
                "go on foot.",
                "Cinema tickets can be bought online at www. ______ org.",
            ],
        )
        for item in result:
            self.assertEqual(item["options"], [])


class FormStyleGapFillTests(RealClipsMixin, TestCase):
    """Clips 7 and 11 are notes/forms, not a flowing paragraph - each
    blank sits alone on its own line rather than several sharing one line.
    These aren't part of the four worked examples in the spec, so this
    only checks the extractor copes without crashing and without losing
    any of the 5 blanks."""

    def test_clip_7_interview_form(self):
        result = extract_question_content(7, TaskType.GAP_FILL, self.bodies[7])
        self.assertEqual(len(result), 5)
        for item in result:
            self.assertIn("______", item["stem"])
            self.assertEqual(item["options"], [])

    def test_clip_11_hotel_notes(self):
        result = extract_question_content(11, TaskType.GAP_FILL, self.bodies[11])
        self.assertEqual(len(result), 5)
        for item in result:
            self.assertIn("______", item["stem"])
            self.assertEqual(item["options"], [])


class SourceTypoCorrectionTests(RealClipsMixin, TestCase):
    """The client's own file has five verbatim slips that would otherwise
    be printed to students as-is - four single-word spelling/agreement
    typos plus one verified content error (clip 1 Q4: the transcript has
    the *boy* packing, not the girl printed in the stem). Each is
    corrected on the way in and listed in STEM_CORRECTIONS.
    """

    def test_the_boy_packing_typo_is_corrected(self):
        result = extract_question_content(1, TaskType.PICTURE, self.bodies[1])
        self.assertEqual(
            result[3]["stem"], "What will the boy take with him on holiday?",
        )

    def test_the_raw_source_really_does_contain_the_girl_packing_typo(self):
        """Guards the correction itself: if the client fixes their file,
        this fails and the STEM_CORRECTIONS entry can be retired."""
        self.assertIn(
            "What will the girl take with her on holiday?", self.bodies[1]
        )

    def test_the_name_same_typo_is_corrected(self):
        result = extract_question_content(4, TaskType.TRUE_FALSE, self.bodies[4])
        self.assertEqual(
            result[2]["stem"],
            "Lucas and Claire have the same opinion about the band’s costumes.",
        )

    def test_the_raw_source_really_does_contain_the_typo(self):
        """Guards the correction itself: if the client fixes their file,
        this fails and the STEM_CORRECTIONS entry can be retired."""
        self.assertIn("have the name opinion", self.bodies[4])

    def test_the_pictures_shows_typo_is_corrected(self):
        result = extract_question_content(5, TaskType.PICTURE, self.bodies[5])
        self.assertEqual(
            result[3]["stem"], "Which picture shows what happened?",
        )

    def test_the_raw_source_really_does_contain_the_pictures_shows_typo(self):
        """Guards the correction itself: if the client fixes their file,
        this fails and the STEM_CORRECTIONS entry can be retired."""
        self.assertIn("Which pictures shows what happened?", self.bodies[5])

    def test_the_lckworth_typo_is_corrected(self):
        result = extract_question_content(6, TaskType.MCQ3, self.bodies[6])
        self.assertEqual(
            result[4]["stem"],
            "What does the festival programme offer at Ickworth?",
        )

    def test_the_raw_source_really_does_contain_the_lckworth_typo(self):
        """Guards the correction itself: if the client fixes their file,
        this fails and the STEM_CORRECTIONS entry can be retired."""
        self.assertIn(
            "What does the festival programme offer at lckworth?", self.bodies[6]
        )

    def test_the_drives_drivers_typo_is_corrected(self):
        result = extract_question_content(13, TaskType.PICTURE, self.bodies[13])
        self.assertEqual(
            result[2]["stem"], "Why will drivers have problems this morning?",
        )

    def test_the_raw_source_really_does_contain_the_drives_typo(self):
        """Guards the correction itself: if the client fixes their file,
        this fails and the STEM_CORRECTIONS entry can be retired."""
        self.assertIn("Why will drives have problems this morning?", self.bodies[13])

    def test_a_correction_that_no_longer_matches_is_left_alone(self):
        """Applied only on an exact match, so an upstream fix is a no-op
        rather than a crash or a double-correction."""
        stale = {(4, 3): ("text the source has never contained", "replacement")}
        with mock.patch.object(listening_content, "STEM_CORRECTIONS", stale):
            result = extract_question_content(4, TaskType.TRUE_FALSE, self.bodies[4])
        self.assertEqual(
            result[2]["stem"],
            "Lucas and Claire have the name opinion about the band’s costumes.",
        )


class AllClipsSmokeTests(RealClipsMixin, TestCase):
    """Every clip in the real bank must parse to exactly 5 usable items."""

    def test_every_clip_parses_to_five_non_placeholder_stems(self):
        from diagnostics.constants import CLIP_TASK_TYPES

        for number in range(1, 21):
            task_type = CLIP_TASK_TYPES[number]
            result = extract_question_content(number, task_type, self.bodies[number])
            self.assertEqual(len(result), 5, f"clip {number}")
            for item in result:
                self.assertTrue(item["stem"].strip(), f"clip {number} empty stem")
                self.assertNotRegex(
                    item["stem"], r"^Clip \d+, question \d+$", f"clip {number}"
                )
