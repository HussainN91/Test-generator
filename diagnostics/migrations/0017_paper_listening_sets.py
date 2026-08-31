"""Step 4 of 4: point papers at question sets instead of recordings.

Nullable first, backfilled to each paper's existing clip at set 1, then made
required - the same carry-the-data-across shape as 0014-0016. Every paper
lands on set 1, so this migration changes no student-visible content; the
allocator starts issuing set 2 in a later phase.

Reversibility follows the same fix 0016 needed, for the same reason: the two
RemoveField operations at the end have no explicit reverse, so Django would
otherwise try to auto-reverse them using listening_clip_1/2's ORIGINAL
non-nullable, no-default definition (from 0003_paper.py) - which fails with
an IntegrityError against a populated table (48 real papers in this
worktree). The fix: listening_clip_1/2 are made nullable via AlterField
*before* the RemoveField calls, and a RunPython step (a no-op forward; its
reverse repopulates listening_clip_1_id/listening_clip_2_id from
listening_set_1.clip_id/listening_set_2.clip_id) sits where it runs *after*
RemoveField's reverse re-adds the columns but *before* the AlterField that
forces them back to NOT NULL reverses (operations reverse in reverse order,
so "runs after" in the reverse direction means "sits earlier" in this list).

The listening_set_1/listening_set_2 side needs no equivalent rescue: on a
full reverse those columns are simply dropped again (AddField's reverse is
RemoveField), discarding their data outright, so the RunPython that backfills
them from the old clip fields only needs a real forward function - its
reverse is a genuine no-op.
"""

import django.db.models.deletion
from django.db import migrations, models


def point_papers_at_set_one(apps, schema_editor):
    Paper = apps.get_model("diagnostics", "Paper")
    ListeningQuestionSet = apps.get_model("diagnostics", "ListeningQuestionSet")

    first_sets = {
        question_set.clip_id: question_set.pk
        for question_set in ListeningQuestionSet.objects.filter(number=1)
    }
    for paper in Paper.objects.all():
        try:
            paper.listening_set_1_id = first_sets[paper.listening_clip_1_id]
            paper.listening_set_2_id = first_sets[paper.listening_clip_2_id]
        except KeyError as missing:
            raise RuntimeError(
                f"{paper.grade}-{paper.variant} uses clip id {missing} which has "
                f"no set 1; run migration 0015 first."
            ) from None
        paper.save(update_fields=["listening_set_1_id", "listening_set_2_id"])


def _noop(apps, schema_editor):
    pass


def _restore_clip_ids(apps, schema_editor):
    Paper = apps.get_model("diagnostics", "Paper")
    for paper in Paper.objects.select_related("listening_set_1", "listening_set_2"):
        paper.listening_clip_1_id = paper.listening_set_1.clip_id
        paper.listening_clip_2_id = paper.listening_set_2.clip_id
        paper.save(update_fields=["listening_clip_1_id", "listening_clip_2_id"])


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0016_listeningquestion_drop_clip")]

    operations = [
        migrations.AddField(
            model_name="paper",
            name="listening_set_1",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_first", to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.AddField(
            model_name="paper",
            name="listening_set_2",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_second", to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.RunPython(point_papers_at_set_one, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="paper",
            name="listening_set_1",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_first", to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.AlterField(
            model_name="paper",
            name="listening_set_2",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_second", to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.AlterField(
            model_name="paper",
            name="listening_clip_1",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_first", to="diagnostics.audioclip",
            ),
        ),
        migrations.AlterField(
            model_name="paper",
            name="listening_clip_2",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_second", to="diagnostics.audioclip",
            ),
        ),
        migrations.RunPython(_noop, _restore_clip_ids),
        migrations.RemoveField(model_name="paper", name="listening_clip_1"),
        migrations.RemoveField(model_name="paper", name="listening_clip_2"),
    ]
