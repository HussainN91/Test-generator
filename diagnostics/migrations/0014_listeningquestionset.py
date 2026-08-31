"""Step 1 of 4: create ListeningQuestionSet and a nullable link to it.

Split into four migrations because the existing rows have to be carried
across: the clip -> question_set re-parenting cannot be done in one operation
without either losing every question or failing the NOT NULL check.
"""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0013_correct_listening_stems")]

    operations = [
        migrations.CreateModel(
            name="ListeningQuestionSet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("number", models.PositiveSmallIntegerField(
                    help_text="1 or 2. Which of the recording's two question papers this is.",
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(2),
                    ],
                )),
                ("clip", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="question_sets",
                    to="diagnostics.audioclip",
                )),
            ],
            options={"ordering": ["clip__number", "number"]},
        ),
        migrations.AddConstraint(
            model_name="listeningquestionset",
            constraint=models.UniqueConstraint(
                fields=("clip", "number"), name="unique_listening_set_number"
            ),
        ),
        migrations.AddField(
            model_name="listeningquestion",
            name="question_set",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="diagnostics.listeningquestionset",
            ),
        ),
    ]
