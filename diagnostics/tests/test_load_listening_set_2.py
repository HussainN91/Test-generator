"""The loader is the only writer of set 2, so these tests are what stop it
silently half-loading: a clip must come out with five questions or the whole
command must roll back."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase

from diagnostics.models import (
    AudioClip, ListeningQuestion, ListeningQuestionSet,
)


def _clip_payload(number, task_type, **overrides):
    questions = []
    for position in range(1, 6):
        question = {
            "position": position, "stem": f"Clip {number} set 2 Q{position}",
            "options": ["a", "b", "c"], "answer": "A", "acceptable_answers": [],
        }
        question.update(overrides)
        questions.append(question)
    return {"number": number, "task_type": task_type, "questions": questions}


class LoadListeningSetTwoTests(TestCase):
    def setUp(self):
        from diagnostics.constants import CLIP_TASK_TYPES
        for number, task in CLIP_TASK_TYPES.items():
            AudioClip.objects.create(number=number, task_type=task)
            ListeningQuestionSet.objects.create(
                clip=AudioClip.objects.get(number=number), number=1
            )
        self.payload_path = Path(settings.BASE_DIR) / "test-listening-set-2.json"
        self.addCleanup(
            lambda: self.payload_path.exists() and self.payload_path.unlink()
        )

    def _write(self, clips):
        self.payload_path.write_text(json.dumps({"clips": clips}), encoding="utf-8")

    def _full_payload(self):
        from diagnostics.constants import CLIP_TASK_TYPES, PICTURE_CLIPS
        clips = []
        for number, task in CLIP_TASK_TYPES.items():
            if number in PICTURE_CLIPS:
                clips.append(_clip_payload(
                    number, task, options=[],
                    image=f"clip-{number:02d}-q6.jpg", answer="B",
                ))
            elif task == "gap_fill":
                clips.append(_clip_payload(number, task, options=[], answer="museum"))
            else:
                clips.append(_clip_payload(number, task))
        return clips

    def test_loads_a_second_set_for_every_clip(self):
        self._write(self._full_payload())
        call_command("load_listening_set_2", source=str(self.payload_path),
                     skip_images=True)
        self.assertEqual(ListeningQuestionSet.objects.filter(number=2).count(), 20)
        self.assertEqual(
            ListeningQuestion.objects.filter(question_set__number=2).count(), 100
        )

    def test_set_one_is_never_touched(self):
        first = ListeningQuestionSet.objects.get(clip__number=1, number=1)
        ListeningQuestion.objects.create(
            question_set=first, position=1, stem="original", answer="A"
        )
        self._write(self._full_payload())
        call_command("load_listening_set_2", source=str(self.payload_path),
                     skip_images=True)
        self.assertTrue(
            ListeningQuestion.objects.filter(
                question_set=first, stem="original"
            ).exists()
        )

    def test_reloading_replaces_set_two_rather_than_duplicating_it(self):
        self._write(self._full_payload())
        call_command("load_listening_set_2", source=str(self.payload_path),
                     skip_images=True)
        call_command("load_listening_set_2", source=str(self.payload_path),
                     skip_images=True)
        self.assertEqual(
            ListeningQuestion.objects.filter(question_set__number=2).count(), 100
        )

    def test_a_malformed_clip_rolls_the_whole_load_back(self):
        clips = self._full_payload()
        clips[7]["questions"][2]["answer"] = "Z"
        self._write(clips)
        with self.assertRaises(CommandError):
            call_command("load_listening_set_2", source=str(self.payload_path),
                         skip_images=True)
        self.assertEqual(ListeningQuestionSet.objects.filter(number=2).count(), 0)

    def test_a_missing_image_is_refused_before_anything_is_written(self):
        clips = self._full_payload()
        for clip in clips:
            if clip["number"] == 1:
                clip["questions"][0]["image"] = "clip-99-q9.jpg"
        self._write(clips)
        with self.assertRaisesMessage(CommandError, "clip-99-q9.jpg"):
            call_command("load_listening_set_2", source=str(self.payload_path))
        self.assertEqual(ListeningQuestionSet.objects.filter(number=2).count(), 0)

    def test_a_missing_clip_in_the_payload_is_refused(self):
        clips = self._full_payload()[:-1]
        self._write(clips)
        with self.assertRaises(CommandError):
            call_command("load_listening_set_2", source=str(self.payload_path),
                         skip_images=True)

    def test_a_real_image_is_referenced_not_duplicated_or_renamed(self):
        """Regression test for a real bug: the picture-strip files (e.g.
        clip-01-q6.jpg) already live permanently under MEDIA_ROOT - the
        loader must point the ImageField at that existing file directly,
        never re-save its bytes into the same directory.
        FileSystemStorage never overwrites on a name collision; it silently
        renames to clip-01-q6_XXXXXXXX.jpg instead, which would produce a
        stray duplicate file on every run and a different image.name each
        time, breaking the "idempotent, re-running just rebuilds set 2"
        guarantee. This test runs the real (no --skip-images) path against
        a real file already present in this worktree, so a regression here
        shows up as a failing assertion, not just as files silently
        accumulating on disk."""
        self._write(self._full_payload())

        image_dir = Path(settings.MEDIA_ROOT) / "diagnostics" / "listening"
        canonical = image_dir / "clip-01-q6.jpg"
        self.assertTrue(canonical.exists(), f"fixture image missing: {canonical}")
        original_bytes = canonical.read_bytes()
        before = sorted(p.name for p in image_dir.glob("clip-01-q6*"))

        call_command("load_listening_set_2", source=str(self.payload_path))

        question = ListeningQuestion.objects.get(
            question_set__clip__number=1, question_set__number=2, position=1
        )
        self.assertEqual(question.image.name, "diagnostics/listening/clip-01-q6.jpg")
        self.assertEqual(Path(question.image.path).read_bytes(), original_bytes)

        after_first_run = sorted(p.name for p in image_dir.glob("clip-01-q6*"))
        self.assertEqual(
            after_first_run, before,
            "loading must not create a new/renamed image file on disk",
        )

        first_run_name = question.image.name

        # Re-run: idempotency means the SAME name comes back, no suffix drift,
        # and still no new file appears next to the original.
        call_command("load_listening_set_2", source=str(self.payload_path))
        question = ListeningQuestion.objects.get(
            question_set__clip__number=1, question_set__number=2, position=1
        )
        self.assertEqual(question.image.name, first_run_name)

        after_second_run = sorted(p.name for p in image_dir.glob("clip-01-q6*"))
        self.assertEqual(
            after_second_run, before,
            "re-running must not create a new/renamed image file either",
        )
