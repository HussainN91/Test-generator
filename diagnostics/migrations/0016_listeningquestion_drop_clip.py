"""Step 3 of 4: make question_set required and retire the direct clip link.

Order matters, in both directions:
- Forward: the old unique(clip, position) constraint has to go before its
  column does, and question_set can only become NOT NULL once 0015 has
  filled every row.
- Reverse: clip is made nullable *before* it's dropped, purely so that
  reversing can re-add the column without Postgres/SQLite rejecting a
  NOT NULL column with no default on a populated table. The RunPython step
  is a no-op forward; its reverse repopulates clip_id from question_set.clip_id
  once the column exists again (i.e. after RemoveField's own reverse has run,
  which is why it sits *before* RemoveField in this list - operations reverse
  in reverse order) and *before* clip is forced back to NOT NULL.
"""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def _noop(apps, schema_editor):
    pass


def _restore_clip_ids(apps, schema_editor):
    ListeningQuestion = apps.get_model("diagnostics", "ListeningQuestion")
    for question in ListeningQuestion.objects.select_related("question_set"):
        question.clip_id = question.question_set.clip_id
        question.save(update_fields=["clip_id"])


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0015_backfill_listening_set_one")]

    operations = [
        migrations.RemoveConstraint(
            model_name="listeningquestion",
            name="unique_listening_position",
        ),
        migrations.AlterField(
            model_name="listeningquestion",
            name="clip",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="diagnostics.audioclip",
            ),
        ),
        migrations.RunPython(_noop, _restore_clip_ids),
        migrations.RemoveField(model_name="listeningquestion", name="clip"),
        migrations.AlterField(
            model_name="listeningquestion",
            name="question_set",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.AlterModelOptions(
            name="listeningquestion",
            options={"ordering": ["question_set__clip__number",
                                  "question_set__number", "position"]},
        ),
        migrations.AddConstraint(
            model_name="listeningquestion",
            constraint=models.UniqueConstraint(
                fields=("question_set", "position"), name="unique_listening_position"
            ),
        ),
    ]
