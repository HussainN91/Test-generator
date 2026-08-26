"""Messy region strings must resolve to seeded regions, and a human decision
must only ever be needed once (spec §4.2).
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from step.models import AliasMapping, District, Region
from step.roster import geo


class ResolveRegionTests(TestCase):
    def setUp(self):
        call_command("seed_geography", stdout=StringIO())

    def test_exact_name_resolves(self):
        self.assertEqual(geo.resolve_region("Samarkand").code, "samarkand")

    def test_case_and_spacing_are_ignored(self):
        self.assertEqual(geo.resolve_region("  samarkand ").code, "samarkand")

    def test_uzbek_spelling_resolves(self):
        self.assertEqual(geo.resolve_region("Samarqand").code, "samarkand")

    def test_tashkent_city_and_region_do_not_collide(self):
        self.assertEqual(geo.resolve_region("Tashkent City").code, "tashkent-city")
        self.assertEqual(geo.resolve_region("Tashkent Region").code, "tashkent-region")

    def test_an_unknown_string_returns_none_rather_than_guessing(self):
        self.assertIsNone(geo.resolve_region("Atlantis"))

    def test_a_bare_tashkent_is_ambiguous_and_returns_none(self):
        """Refusing to guess is the point: guessing wrong silently splits a chart."""
        self.assertIsNone(geo.resolve_region("Tashkent"))

    def test_a_learned_alias_resolves_afterwards(self):
        self.assertIsNone(geo.resolve_region("Tash. city"))
        geo.learn_region_alias("Tash. city", Region.objects.get(code="tashkent-city"))
        self.assertEqual(geo.resolve_region("Tash. city").code, "tashkent-city")

    def test_learning_the_same_alias_twice_is_harmless(self):
        region = Region.objects.get(code="samarkand")
        geo.learn_region_alias("Smrkd", region)
        geo.learn_region_alias("Smrkd", region)
        self.assertEqual(AliasMapping.objects.filter(normalised="smrkd").count(), 1)


class ResolveDistrictTests(TestCase):
    def setUp(self):
        call_command("seed_geography", stdout=StringIO())

    def test_district_resolves_within_its_region(self):
        region = Region.objects.get(code="fergana")
        self.assertEqual(geo.resolve_district("Kokand", region).code, "kokand")

    def test_district_from_the_wrong_region_does_not_resolve(self):
        region = Region.objects.get(code="bukhara")
        self.assertIsNone(geo.resolve_district("Kokand", region))

    def test_district_resolves_without_a_region_when_unambiguous(self):
        district = geo.resolve_district("Kokand", None)
        self.assertIsNotNone(district)
        self.assertEqual(district.region.code, "fergana")

    def test_an_ambiguous_district_without_a_region_returns_none(self):
        region = Region.objects.get(code="bukhara")
        District.objects.create(region=region, name="Kokand", code="kokand-dup")
        self.assertIsNone(geo.resolve_district("Kokand", None))
