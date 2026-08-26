"""Reclassify existing odd-one-out items out of multiple_choice.

Before this migration, "Which word means...?" and "Which word does not
belong?" were both stored as question_type=multiple_choice, distinguished
only by an incidental "shared_category" payload key. Anything with that key
was written by build_odd_one_out_items and is reclassified here; everything
else keeps its type.

content_hash is recomputed alongside question_type using the same formula as
DraftItem.content_hash() (bank/generation/bootstrap.py) rather than imported
from it, because a data migration must keep working even if that formula
changes later. content_hash is part of the hash basis, so leaving it stale
would make a future `seed_bank` re-run over these units treat every
reclassified item as new and insert a duplicate beside it.
"""

import hashlib
import json

from django.db import migrations


def _content_hash(unit_id, question_type, model_answer, payload):
    stable_payload = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    basis = f"{unit_id}|{question_type}|{model_answer}|{stable_payload}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def split_odd_one_out(apps, schema_editor):
    Item = apps.get_model("bank", "Item")
    for item in Item.objects.filter(
        question_type="multiple_choice", payload__has_key="shared_category"
    ):
        item.question_type = "odd_one_out"
        item.content_hash = _content_hash(
            item.unit_id, item.question_type, item.model_answer, item.payload
        )
        item.save(update_fields=["question_type", "content_hash"])


def merge_odd_one_out(apps, schema_editor):
    Item = apps.get_model("bank", "Item")
    for item in Item.objects.filter(question_type="odd_one_out"):
        item.question_type = "multiple_choice"
        item.content_hash = _content_hash(
            item.unit_id, item.question_type, item.model_answer, item.payload
        )
        item.save(update_fields=["question_type", "content_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("bank", "0002_alter_item_question_type"),
    ]

    operations = [
        migrations.RunPython(split_odd_one_out, merge_odd_one_out),
    ]
