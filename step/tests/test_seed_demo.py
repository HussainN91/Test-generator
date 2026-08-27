"""seed_demo's catalogue is what the classes/gradebook checkpoints attach to
by name (step.constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES) — a renamed or
missing catalogue entry breaks generation silently, so the names are pinned
here."""

import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from step import constants
from step.models import Evidence, ObligationType

MEDIA = tempfile.mkdtemp()


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

    @override_settings(MEDIA_ROOT=MEDIA)
    def test_the_accepted_monthly_reports_carry_a_real_file_not_an_empty_one(self):
        """A file-kind Evidence row with no actual file crashes any template
        that reads evidence.file.url (FieldFile.url raises on an empty file) —
        found by test-generator-a7 auditing the admin review screen against
        this command's seed data."""
        call_command("seed_demo", stdout=StringIO())
        file_evidence = Evidence.objects.filter(kind=constants.EVIDENCE_FILE_KIND)
        self.assertGreater(file_evidence.count(), 0)
        for evidence in file_evidence:
            self.assertTrue(evidence.file, f"Evidence {evidence.pk} claims kind=file but has no file")
