"""seed_demo's catalogue is what the classes/gradebook checkpoints attach to
by name (step.constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES) — a renamed or
missing catalogue entry breaks generation silently, so the names are pinned
here."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from step import constants
from step.models import ObligationType


class SeedDemoCheckpointTypesTests(TestCase):
    def setUp(self):
        # seed_demo bails out with no regions to attach the demo teacher to.
        call_command("seed_geography", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())

    def test_the_three_checkpoint_types_are_seeded(self):
        call_command("seed_demo", stdout=StringIO())
        names = set(
            ObligationType.objects.filter(
                form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT
            ).values_list("name_template", flat=True)
        )
        self.assertEqual(names, set(constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES.values()))

    def test_the_superseded_generic_assessment_types_are_gone(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertFalse(
            ObligationType.objects.filter(name_template__startswith="Assessment Administration").exists()
        )
        self.assertFalse(
            ObligationType.objects.filter(name_template__startswith="Assessment Scoring").exists()
        )

    def test_checkpoint_types_are_annual_with_no_evidence(self):
        call_command("seed_demo", stdout=StringIO())
        boy = ObligationType.objects.get(name_template="Beginning-of-year diagnostic")
        self.assertEqual(boy.cadence, constants.CADENCE_ANNUAL)
        self.assertEqual(boy.evidence_spec, constants.EVIDENCE_NONE)
        self.assertFalse(boy.requires_review)
