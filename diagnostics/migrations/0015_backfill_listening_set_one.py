"""Step 2 of 4: give every clip a set 1 and move its questions onto it.

Reversible so the whole four-migration stack can be unwound on a dev box:
reversing puts each question's clip_id back and deletes the sets.
"""

from django.db import migrations


def create_first_sets(apps, schema_editor):
    AudioClip = apps.get_model("diagnostics", "AudioClip")
    ListeningQuestionSet = apps.get_model("diagnostics", "ListeningQuestionSet")
    ListeningQuestion = apps.get_model("diagnostics", "ListeningQuestion")

    for clip in AudioClip.objects.all():
        question_set, _ = ListeningQuestionSet.objects.get_or_create(
            clip=clip, number=1
        )
        ListeningQuestion.objects.filter(clip=clip).update(question_set=question_set)

    orphans = ListeningQuestion.objects.filter(question_set__isnull=True).count()
    if orphans:
        raise RuntimeError(
            f"{orphans} listening questions have no clip and cannot be assigned "
            f"to a set; refusing to continue and leave them unreachable."
        )


def undo_first_sets(apps, schema_editor):
    ListeningQuestionSet = apps.get_model("diagnostics", "ListeningQuestionSet")
    ListeningQuestion = apps.get_model("diagnostics", "ListeningQuestion")

    for question in ListeningQuestion.objects.select_related("question_set"):
        question.clip_id = question.question_set.clip_id
        question.save(update_fields=["clip_id"])
    ListeningQuestionSet.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0014_listeningquestionset")]

    operations = [migrations.RunPython(create_first_sets, undo_first_sets)]
