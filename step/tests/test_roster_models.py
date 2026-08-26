"""The roster must survive a spreadsheet whose columns nobody has seen.

Every field except an identity key and a geographic anchor is optional, and
unrecognised columns are preserved in `source_fields` rather than dropped
(spec §4.2). School is nullable because the sheet may not carry usable school
names.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from step.models import District, Educator, PendingSignup, Region, School


class EducatorTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.district = District.objects.create(region=self.region, name="Urgut", code="urgut")

    def test_an_educator_needs_only_a_name_and_a_region(self):
        educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.assertIsNone(educator.school)
        self.assertIsNone(educator.user)
        self.assertEqual(educator.email, "")
        self.assertEqual(educator.source_fields, {})

    def test_unrecognised_columns_are_preserved(self):
        educator = Educator.objects.create(
            full_name="Maria Santos",
            region=self.region,
            source_fields={"Contract Type": "Two year", "Intake": "2025-A"},
        )
        educator.refresh_from_db()
        self.assertEqual(educator.source_fields["Intake"], "2025-A")

    def test_is_active_defaults_true_and_missing_flag_defaults_false(self):
        educator = Educator.objects.create(full_name="A B", region=self.region)
        self.assertTrue(educator.is_active)
        self.assertFalse(educator.missing_from_last_import)

    def test_deleting_a_user_does_not_delete_the_educator(self):
        user = get_user_model().objects.create_user("maria", password="x")
        educator = Educator.objects.create(full_name="Maria", region=self.region, user=user)
        user.delete()
        educator.refresh_from_db()
        self.assertIsNone(educator.user)

    def test_str_is_the_name(self):
        educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.assertEqual(str(educator), "Maria Santos")


class SchoolTests(TestCase):
    def test_school_belongs_to_a_district(self):
        region = Region.objects.create(name="Fergana", code="fergana")
        district = District.objects.create(region=region, name="Kokand", code="kokand")
        school = School.objects.create(name="International School 4", district=district)
        self.assertEqual(school.district.region, region)
        self.assertEqual(str(school), "International School 4")


class PendingSignupTests(TestCase):
    def test_a_signup_that_matches_nobody_is_recorded_for_an_admin(self):
        pending = PendingSignup.objects.create(
            full_name="Unknown Person", email="nobody@example.com"
        )
        self.assertFalse(pending.resolved)
        self.assertIn("Unknown Person", str(pending))
