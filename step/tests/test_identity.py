"""No single identifier is safe here (spec §4.3): PINFL is an Uzbek citizen
number foreign educators may not hold, passports change on renewal, and email
gets mistyped. So the resolver tries keys in a configured order and refuses to
answer when two roster rows both match.
"""

from django.test import TestCase, override_settings

from step import identity
from step.models import Educator, Region


class ResolveTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(
            full_name="Maria Santos",
            region=self.region,
            email="maria@example.com",
            passport_no="P1234567",
            pinfl="12345678901234",
        )

    @override_settings(STEP_ROSTER_MATCH_KEYS=["pinfl", "passport_no", "email"])
    def test_matches_on_the_first_configured_key(self):
        educator, key = identity.resolve(pinfl="12345678901234")
        self.assertEqual(educator, self.maria)
        self.assertEqual(key, "pinfl")

    @override_settings(STEP_ROSTER_MATCH_KEYS=["pinfl", "passport_no", "email"])
    def test_falls_back_to_a_later_key(self):
        educator, key = identity.resolve(email="maria@example.com")
        self.assertEqual(educator, self.maria)
        self.assertEqual(key, "email")

    @override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
    def test_a_key_not_in_the_configured_order_is_ignored(self):
        educator, key = identity.resolve(pinfl="12345678901234")
        self.assertIsNone(educator)
        self.assertIsNone(key)

    @override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
    def test_email_matching_is_case_insensitive_and_trimmed(self):
        educator, _ = identity.resolve(email="  MARIA@EXAMPLE.COM ")
        self.assertEqual(educator, self.maria)

    @override_settings(STEP_ROSTER_MATCH_KEYS=["passport_no"])
    def test_blank_values_never_match_blank_roster_fields(self):
        Educator.objects.create(full_name="Blank Person", region=self.region)
        educator, key = identity.resolve(passport_no="")
        self.assertIsNone(educator)
        self.assertIsNone(key)

    @override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
    def test_two_rows_matching_the_same_key_is_a_conflict_not_a_match(self):
        Educator.objects.create(
            full_name="Maria Santos (duplicate)", region=self.region, email="maria@example.com"
        )
        with self.assertRaises(identity.AmbiguousIdentity):
            identity.resolve(email="maria@example.com")

    @override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
    def test_no_candidates_returns_none(self):
        educator, key = identity.resolve()
        self.assertIsNone(educator)
        self.assertIsNone(key)


class RequiredSignupFieldsTests(TestCase):
    @override_settings(STEP_ROSTER_MATCH_KEYS=["pinfl", "email"])
    def test_signup_asks_for_the_configured_keys(self):
        self.assertEqual(identity.required_signup_fields(), ["pinfl", "email"])

    @override_settings(STEP_ROSTER_MATCH_KEYS=["nonsense", "email"])
    def test_unknown_configured_keys_are_rejected_loudly(self):
        with self.assertRaises(ValueError):
            identity.required_signup_fields()
