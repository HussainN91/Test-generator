"""Guessing what a spreadsheet column means.

The client's roster sheet exists but its headers are unknown and will change
between terms. Rather than hardcode column positions, the importer proposes a
mapping and a human confirms it before any row is written (spec §4.2).

Everything here is a pure function: no database, no Django models. That makes
the guessing logic cheap to test against real header spellings as they turn up.
"""

import re

#: Canonical field name -> the normalised header spellings that mean it.
#: Ordered most-specific first so "email address" wins over a bare "address".
ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": ("fullname", "teachername", "educatorname", "name", "fio", "surnameandname"),
    "email": ("emailaddress", "email", "email", "gmail", "mail"),
    "passport_no": ("passportnumber", "passportno", "passport", "passportseries"),
    "pinfl": ("pinfl", "pnfl", "jshshir", "personalnumber"),
    "region": ("region", "viloyat", "province", "oblast", "viloyati"),
    "district": ("district", "tuman", "tumani", "rayon"),
    "school": ("schoolname", "school", "maktab", "institution", "workplace"),
}

#: One of these must be mapped for a row to be identifiable.
IDENTITY_FIELDS = ("email", "passport_no", "pinfl")

#: One of these must be mapped for a row to be placeable on the map.
GEOGRAPHIC_FIELDS = ("region", "district", "school")


def normalise(value) -> str:
    """Lowercase and strip everything that is not a letter or digit.

    Deliberately keeps non-ASCII letters so Cyrillic and Uzbek Latin headers
    survive; only punctuation and spacing are discarded.
    """
    if value is None:
        return ""
    return re.sub(r"[^\w]", "", str(value), flags=re.UNICODE).lower().replace("_", "")


def propose_mapping(headers) -> dict:
    """Return {original header: canonical field or None}.

    Blank headers are skipped entirely. A canonical field is claimed by at most
    one header — the first that matches — because two columns mapping to
    `email` would silently overwrite each other during import.
    """
    proposed: dict = {}
    claimed: set[str] = set()

    for header in headers:
        if header is None or not str(header).strip():
            continue
        key = normalise(header)
        match = None
        for field, aliases in ALIASES.items():
            if field in claimed:
                continue
            if key in aliases:
                match = field
                break
        if match:
            claimed.add(match)
        proposed[header] = match

    return proposed


def check_sufficiency(mapping_dict) -> tuple[bool, list[str]]:
    """Is this mapping enough to import from?

    Enforces *minimum sufficiency* rather than a fixed column list, matching
    the convention already used by the diagnostics import commands.
    """
    targets = {v for v in mapping_dict.values() if v}
    missing = []
    if not targets & set(IDENTITY_FIELDS):
        missing.append("an identity key (email, passport_no or pinfl)")
    if not targets & set(GEOGRAPHIC_FIELDS):
        missing.append("a geographic anchor (region, district or school)")
    return (not missing), missing
