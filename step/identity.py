"""Matching a person to a roster row.

Used by BOTH the spreadsheet importer and self-signup, deliberately: if they
matched differently, a teacher could sign up and create a duplicate of a row
that already exists. One resolver, one behaviour.

Which identifier is authoritative is a deployment decision the client has not
yet made (spec §4.3), so it lives in settings.STEP_ROSTER_MATCH_KEYS as an
ordered list. Changing it is a settings change, never a migration.
"""

from django.conf import settings

from step.models import Educator

#: The only identifiers the resolver understands. Anything else in the setting
#: is a configuration error worth failing loudly on.
KNOWN_KEYS = ("pinfl", "passport_no", "email")


class AmbiguousIdentity(Exception):
    """Two or more roster rows matched. A human must decide."""


def _configured_keys() -> list[str]:
    keys = list(getattr(settings, "STEP_ROSTER_MATCH_KEYS", ["email"]))
    unknown = [k for k in keys if k not in KNOWN_KEYS]
    if unknown:
        raise ValueError(
            f"STEP_ROSTER_MATCH_KEYS contains unknown keys {unknown}. Known: {list(KNOWN_KEYS)}"
        )
    return keys


def required_signup_fields() -> list[str]:
    """What the signup form must ask for, in order."""
    return _configured_keys()


def _normalise(key: str, value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if key == "email":
        text = text.lower()
    return text


def resolve(*, email=None, passport_no=None, pinfl=None):
    """Return (Educator, key_used), or (None, None) if nothing matched.

    Raises AmbiguousIdentity when one key matches more than one roster row —
    silently picking the first would attach a teacher to the wrong person.
    """
    supplied = {"email": email, "passport_no": passport_no, "pinfl": pinfl}

    for key in _configured_keys():
        value = _normalise(key, supplied.get(key))
        if not value:
            continue
        lookup = f"{key}__iexact" if key == "email" else key
        matches = list(Educator.objects.filter(**{lookup: value})[:2])
        if len(matches) > 1:
            raise AmbiguousIdentity(f"{key}={value!r} matches more than one roster row")
        if matches:
            return matches[0], key

    return None, None
