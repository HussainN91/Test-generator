"""Turning spreadsheet place-names into seeded Region and District rows.

The governing rule is **refuse to guess**. A wrong region silently splits a bar
in the administration chart and nobody notices; an unresolved row lands in a
queue where somebody fixes it once and the decision is remembered. Ambiguity is
therefore always resolved to None, never to a best effort.
"""

from step.models import AliasMapping, District, Region
from step.roster.mapping import normalise


def _alias(kind: str, raw: str):
    return AliasMapping.objects.filter(kind=kind, normalised=normalise(raw)).first()


def resolve_region(raw):
    """Return a Region, or None if unknown or ambiguous."""
    if not raw or not str(raw).strip():
        return None
    key = normalise(raw)

    learned = _alias(AliasMapping.KIND_REGION, raw)
    if learned and learned.region:
        return learned.region

    for region in Region.objects.all():
        if key in {normalise(region.name), normalise(region.name_uz), normalise(region.code)}:
            return region
    return None


def resolve_district(raw, region=None):
    """Return a District, or None if unknown or ambiguous.

    When `region` is given the search is confined to it. When it is not, a name
    matching districts in two different regions is ambiguous and returns None.
    """
    if not raw or not str(raw).strip():
        return None
    key = normalise(raw)

    learned = _alias(AliasMapping.KIND_DISTRICT, raw)
    if learned and learned.district:
        if region is None or learned.district.region_id == region.pk:
            return learned.district

    queryset = District.objects.select_related("region")
    if region is not None:
        queryset = queryset.filter(region=region)

    matches = [
        d for d in queryset
        if key in {normalise(d.name), normalise(d.name_uz), normalise(d.code)}
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def learn_region_alias(raw: str, region: Region) -> AliasMapping:
    alias, _ = AliasMapping.objects.update_or_create(
        kind=AliasMapping.KIND_REGION,
        normalised=normalise(raw),
        defaults={"raw_value": str(raw), "region": region},
    )
    return alias


def learn_district_alias(raw: str, district: District) -> AliasMapping:
    alias, _ = AliasMapping.objects.update_or_create(
        kind=AliasMapping.KIND_DISTRICT,
        normalised=normalise(raw),
        defaults={"raw_value": str(raw), "district": district},
    )
    return alias
