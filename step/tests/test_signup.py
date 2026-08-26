"""Self-signup matched against the roster (spec §4.3).

No mass invite email is sent, so there are no dead links and no 2,000-message
spam problem: the teacher signs up, and the sheet decides whether they are let
in. An unmatched signup is held for an administrator rather than silently
creating an educator.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from step import constants, roles, signup
from step.models import Educator, PendingSignup, Region


@override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
class SignupTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        from io import StringIO
        call_command("seed_roles", stdout=StringIO())
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(
            full_name="Maria Santos", region=self.region, email="maria@example.com"
        )
        self.user = get_user_model().objects.create_user("maria", password="x")

    def test_a_matching_signup_links_the_user_and_grants_the_role(self):
        result = signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        self.maria.refresh_from_db()
        self.assertTrue(result.matched)
        self.assertEqual(result.educator, self.maria)
        self.assertEqual(self.maria.user, self.user)
        self.assertTrue(roles.is_educator(self.user))

    def test_an_unmatched_signup_creates_a_pending_record_and_no_educator(self):
        before = Educator.objects.count()
        result = signup.claim(self.user, full_name="Nobody", email="nobody@example.com")
        self.assertFalse(result.matched)
        self.assertIsNone(result.educator)
        self.assertEqual(Educator.objects.count(), before)
        self.assertEqual(PendingSignup.objects.count(), 1)
        self.assertFalse(roles.is_educator(self.user))

    def test_claiming_a_roster_row_already_taken_by_someone_else_is_refused(self):
        other = get_user_model().objects.create_user("other", password="x")
        signup.claim(other, full_name="Maria Santos", email="maria@example.com")
        result = signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        self.assertFalse(result.matched)
        self.assertIn("already", result.reason.lower())
        self.assertEqual(PendingSignup.objects.count(), 1)

    def test_reclaiming_the_same_row_by_the_same_user_is_idempotent(self):
        signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        result = signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        self.assertTrue(result.matched)
        self.assertEqual(PendingSignup.objects.count(), 0)

    def test_an_ambiguous_identity_becomes_pending_rather_than_a_wrong_match(self):
        Educator.objects.create(
            full_name="Maria Santos (duplicate)", region=self.region, email="maria@example.com"
        )
        result = signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        self.assertFalse(result.matched)
        self.assertEqual(PendingSignup.objects.count(), 1)

    def test_resolving_a_pending_signup_attaches_the_user(self):
        signup.claim(self.user, full_name="Nobody", email="nobody@example.com")
        pending = PendingSignup.objects.get()
        signup.resolve_pending(pending, self.maria, self.user)
        self.maria.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(self.maria.user, self.user)
        self.assertTrue(pending.resolved)
        self.assertTrue(roles.is_educator(self.user))
