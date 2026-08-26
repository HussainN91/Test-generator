"""Claiming a roster row at signup.

Uses `step.identity` — the same resolver the importer uses — so a teacher can
never sign up and create a duplicate of a row that already exists.

An unmatched or ambiguous signup produces a PendingSignup rather than an
Educator. Creating a roster row from a signup would make the spreadsheet stop
being the source of truth, which is the one thing this design relies on.
"""

from dataclasses import dataclass
from django.db import transaction

from step import constants, identity, roles
from step.models import Educator, PendingSignup


@dataclass
class ClaimResult:
    matched: bool
    educator: Educator | None = None
    pending: PendingSignup | None = None
    reason: str = ""


def _hold(user, full_name, email, passport_no, pinfl, reason) -> ClaimResult:
    pending = PendingSignup.objects.create(
        full_name=full_name, email=email or "", passport_no=passport_no or "",
        pinfl=pinfl or "", note=reason,
    )
    return ClaimResult(matched=False, pending=pending, reason=reason)


@transaction.atomic
def claim(user, *, full_name="", email="", passport_no="", pinfl="") -> ClaimResult:
    try:
        educator, _key = identity.resolve(email=email, passport_no=passport_no, pinfl=pinfl)
    except identity.AmbiguousIdentity as exc:
        return _hold(user, full_name, email, passport_no, pinfl, str(exc))

    if educator is None:
        return _hold(
            user, full_name, email, passport_no, pinfl,
            "No roster row matched these details.",
        )

    if educator.user_id and educator.user_id != user.pk:
        return _hold(
            user, full_name, email, passport_no, pinfl,
            "That roster row has already been claimed by another account.",
        )

    educator.user = user
    educator.save(update_fields=["user"])
    roles.assign(user, constants.ROLE_EDUCATOR)
    return ClaimResult(matched=True, educator=educator)


@transaction.atomic
def resolve_pending(pending: PendingSignup, educator: Educator, user) -> Educator:
    """An administrator decides which roster row a pending signup belongs to."""
    educator.user = user
    educator.save(update_fields=["user"])
    roles.assign(user, constants.ROLE_EDUCATOR)
    pending.resolved = True
    pending.save(update_fields=["resolved"])
    return educator
