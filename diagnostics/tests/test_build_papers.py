from collections import Counter
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from diagnostics.constants import (
    CLIP_TASK_TYPES, GRADES, PICTURE_CLIPS, REUSE_CAPS, SPEAKING_TASK_ORDER,
    VARIANTS,
)
from diagnostics.models import (
    AudioClip, ListeningQuestionSet, Paper, PaperSpeakingPrompt,
    PaperWritingQuestion, ReadingPassage, SpeakingPrompt, WritingQuestion, WritingSubtype,
)
from diagnostics.navigation import GROUP_NUMBERS, variants_for_group


def seed_content():
    """Real bank-size content: enough to build all 48 papers under the reuse
    caps - 20 clips (real task types) each with both question sets (every
    clip now needs two, since the two variants in a group share one
    recording and answer different question papers), 15 passages,
    200 writing questions (50 per subtype) and 50 speaking prompts (10 per
    task).

    The sets are left empty of questions deliberately: build_papers only
    checks that a ListeningQuestionSet exists for each (clip, number), never
    what's inside it. Tests that render or read actual question content
    (test_rendering.py's seed_questions_and_rubrics, for one) add their own
    questions on top of these sets - populating them here would collide
    with that on the unique (question_set, position) constraint."""
    for number in range(1, 21):
        clip = AudioClip.objects.create(number=number, task_type=CLIP_TASK_TYPES[number])
        for set_number in (1, 2):
            ListeningQuestionSet.objects.create(clip=clip, number=set_number)
    for n in range(1, 16):
        ReadingPassage.objects.create(
            label=f"R{n:02d}", title=f"Passage {n}", body=" ".join(["word"] * 220)
        )
    for subtype, count in [
        (WritingSubtype.GRAMMAR, 50), (WritingSubtype.VOCABULARY, 50),
        (WritingSubtype.JUMBLED, 50), (WritingSubtype.FILL_BLANK, 50),
    ]:
        for i in range(count):
            WritingQuestion.objects.create(
                subtype=subtype, stem=f"{subtype}-{i}",
                options=["a", "b", "c", "d"], answer="A",
            )
    for task in SPEAKING_TASK_ORDER:
        for i in range(10):
            SpeakingPrompt.objects.create(task=task, prompt=f"{task}-{i}")


class BuildPapersTests(TestCase):
    def setUp(self):
        seed_content()

    def test_builds_forty_eight_papers(self):
        call_command("build_papers", stdout=StringIO())
        self.assertEqual(Paper.objects.count(), 48)
        for grade in GRADES:
            self.assertEqual(Paper.objects.filter(grade=grade).count(), 16)

    def test_every_paper_has_a_picture_clip(self):
        call_command("build_papers", stdout=StringIO())
        for paper in Paper.objects.all():
            numbers = {paper.listening_clip_1.number, paper.listening_clip_2.number}
            self.assertEqual(
                len(numbers & set(PICTURE_CLIPS)), 1,
                f"{paper} has {len(numbers & set(PICTURE_CLIPS))} picture clips",
            )

    def test_every_paper_has_ten_writing_and_five_speaking(self):
        call_command("build_papers", stdout=StringIO())
        for paper in Paper.objects.all():
            self.assertEqual(
                PaperWritingQuestion.objects.filter(paper=paper).count(), 10, str(paper)
            )
            self.assertEqual(
                PaperSpeakingPrompt.objects.filter(paper=paper).count(), 5, str(paper)
            )

    def test_reading_passages_stay_within_reuse_cap_per_grade(self):
        call_command("build_papers", stdout=StringIO())
        cap = REUSE_CAPS["reading_passage"]
        for grade in GRADES:
            labels = [
                p.reading_passage.label for p in Paper.objects.filter(grade=grade)
            ]
            self.assertEqual(len(labels), len(VARIANTS))
            counts = Counter(labels)
            over_cap = {label: n for label, n in counts.items() if n > cap}
            self.assertEqual(over_cap, {}, f"grade {grade} exceeds the reuse cap")

    def test_papers_are_published(self):
        call_command("build_papers", stdout=StringIO())
        self.assertEqual(Paper.objects.filter(is_published=True).count(), 48)

    def test_rebuild_is_idempotent(self):
        call_command("build_papers", stdout=StringIO())
        call_command("build_papers", stdout=StringIO())
        self.assertEqual(Paper.objects.count(), 48)
        self.assertEqual(PaperWritingQuestion.objects.count(), 480)
        self.assertEqual(PaperSpeakingPrompt.objects.count(), 240)

    def _fingerprint(self):
        return {
            str(paper): (
                sorted(paper.writing_questions.values_list("pk", flat=True)),
                sorted(paper.speaking_prompts.values_list("pk", flat=True)),
            )
            for paper in Paper.objects.all()
        }

    def test_rebuild_leaves_existing_paper_content_unchanged(self):
        call_command("build_papers", stdout=StringIO())
        before = self._fingerprint()
        call_command("build_papers", stdout=StringIO())
        self.assertEqual(
            before, self._fingerprint(),
            "a plain rebuild silently reissued different content under the same "
            "paper names - papers already handed out would no longer match",
        )

    def test_rebuilding_does_not_change_listening_or_reading(self):
        """update_or_create rewrites these fields on every run, so the
        allocator must be deterministic or a rebuild silently reissues
        different content under the same paper name."""
        call_command("build_papers", stdout=StringIO())
        before = {
            str(p): (p.listening_set_1_id, p.listening_set_2_id, p.reading_passage_id)
            for p in Paper.objects.all()
        }
        call_command("build_papers", stdout=StringIO())
        after = {
            str(p): (p.listening_set_1_id, p.listening_set_2_id, p.reading_passage_id)
            for p in Paper.objects.all()
        }
        self.assertEqual(before, after)

    def test_resample_flag_does_redraw_content(self):
        call_command("build_papers", stdout=StringIO())
        before = self._fingerprint()
        call_command("build_papers", "--resample", stdout=StringIO())
        self.assertNotEqual(before, self._fingerprint())

    def test_rebuild_fills_in_a_paper_whose_content_was_lost(self):
        call_command("build_papers", stdout=StringIO())
        victim = Paper.objects.get(grade=9, variant="A")
        PaperWritingQuestion.objects.filter(paper=victim).delete()
        call_command("build_papers", stdout=StringIO())
        self.assertEqual(
            PaperWritingQuestion.objects.filter(paper=victim).count(), 10
        )

    def test_missing_clips_aborts_before_writing_anything(self):
        AudioClip.objects.all().delete()
        with self.assertRaises(CommandError):
            call_command("build_papers", stdout=StringIO())
        self.assertEqual(Paper.objects.count(), 0)

    def test_too_few_passages_aborts(self):
        ReadingPassage.objects.all().delete()
        ReadingPassage.objects.create(
            label="R01", title="only", body=" ".join(["word"] * 220)
        )
        with self.assertRaises(CommandError):
            call_command("build_papers", stdout=StringIO())
        self.assertEqual(Paper.objects.count(), 0)


class CheckPapersTests(TestCase):
    def setUp(self):
        seed_content()
        call_command("build_papers", stdout=StringIO())

    def test_passes_on_a_correctly_built_bank(self):
        out = StringIO()
        call_command("check_papers", stdout=out)
        self.assertIn("pass", out.getvalue().lower())

    def test_fails_when_a_grade_exceeds_the_reading_passage_reuse_cap(self):
        # Force three variants in grade 9 to share one passage - one more
        # than the reuse cap of 2 allows.
        cap = REUSE_CAPS["reading_passage"]
        victims = Paper.objects.filter(grade=9, variant__in=list(VARIANTS[: cap + 1]))
        shared_passage = victims.first().reading_passage
        Paper.objects.filter(pk__in=victims.values_list("pk", flat=True)).update(
            reading_passage=shared_passage
        )
        with self.assertRaises(CommandError) as ctx:
            call_command("check_papers", stdout=StringIO())
        self.assertIn("Grade 9", str(ctx.exception))

    def test_fails_when_a_grade_repeats_a_writing_question_beyond_its_cap(self):
        first = Paper.objects.get(grade=9, variant="A")
        clash = Paper.objects.get(grade=9, variant="B")
        shared = PaperWritingQuestion.objects.filter(paper=first).first()
        victim = PaperWritingQuestion.objects.filter(paper=clash).first()
        PaperWritingQuestion.objects.filter(pk=victim.pk).update(
            question=shared.question
        )
        with self.assertRaises(CommandError) as ctx:
            call_command("check_papers", stdout=StringIO())
        self.assertIn("Grade 9", str(ctx.exception))

    def test_fails_when_papers_are_missing(self):
        Paper.objects.filter(grade=11).delete()
        with self.assertRaises(CommandError):
            call_command("check_papers", stdout=StringIO())


class GroupBuildTests(TestCase):
    def setUp(self):
        seed_content()

    def test_built_papers_share_audio_within_every_group(self):
        call_command("build_papers", stdout=StringIO())
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                a = Paper.objects.get(grade=grade, variant=first)
                b = Paper.objects.get(grade=grade, variant=second)
                self.assertEqual(
                    (a.listening_set_1.clip_id, a.listening_set_2.clip_id),
                    (b.listening_set_1.clip_id, b.listening_set_2.clip_id),
                    f"G{grade} group {group}",
                )

    def test_built_papers_use_different_question_sets_within_every_group(self):
        call_command("build_papers", stdout=StringIO())
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                a = Paper.objects.get(grade=grade, variant=first)
                b = Paper.objects.get(grade=grade, variant=second)
                self.assertNotEqual(
                    (a.listening_set_1_id, a.listening_set_2_id),
                    (b.listening_set_1_id, b.listening_set_2_id),
                    f"G{grade} group {group} would sit identical papers",
                )

    def test_build_refuses_when_a_clip_has_no_second_set(self):
        ListeningQuestionSet.objects.filter(number=2, clip__number=3).delete()
        with self.assertRaisesMessage(CommandError, "second question set"):
            call_command("build_papers")
