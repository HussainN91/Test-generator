"""Role membership, expressed as Django Groups.

Groups rather than a `role` column because permission checks, the admin, and
`user.has_perm` all already understand groups. A column would mean reinventing
that plumbing.
"""

from django.contrib.auth.models import Group

from step import constants


def role_names(user) -> set[str]:
    if not user or not user.is_authenticated:
        return set()
    names = set(user.groups.values_list("name", flat=True)) & set(constants.ROLE_NAMES)
    # A Django superuser is a System Administrator here too. Without this the
    # person who deployed the site can reach the Django admin and diagnostics
    # (both gate on the built-in `is_staff`) but gets a 403 from every STEP
    # staff screen, which gates on these groups — one account trusted by half
    # the site and invisible to the other.
    if getattr(user, "is_superuser", False):
        names.add(constants.ROLE_SYSTEM_ADMIN)
    return names


def assign(user, role_name: str) -> None:
    if role_name not in constants.ROLE_NAMES:
        raise ValueError(f"Unknown role: {role_name!r}. Known roles: {constants.ROLE_NAMES}")
    user.groups.add(Group.objects.get(name=role_name))


def is_educator(user) -> bool:
    return constants.ROLE_EDUCATOR in role_names(user)


def is_staff_role(user) -> bool:
    return bool(role_names(user) & constants.STAFF_ROLES)
