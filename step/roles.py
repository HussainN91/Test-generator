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
    return set(user.groups.values_list("name", flat=True)) & set(constants.ROLE_NAMES)


def assign(user, role_name: str) -> None:
    if role_name not in constants.ROLE_NAMES:
        raise ValueError(f"Unknown role: {role_name!r}. Known roles: {constants.ROLE_NAMES}")
    user.groups.add(Group.objects.get(name=role_name))


def is_educator(user) -> bool:
    return constants.ROLE_EDUCATOR in role_names(user)


def is_staff_role(user) -> bool:
    return bool(role_names(user) & constants.STAFF_ROLES)
