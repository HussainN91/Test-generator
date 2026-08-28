"""Announcements and RSVP — the CPD Online vertical.

The third of three peer concepts alongside Obligation (owed) and
Activity/Session (done): CPD Online is run by the Ministry and merely
*announced* here, with the teacher's only interaction being an RSVP
(fix step plan.md §2, §5). There is no obligation row, no evidence, no
review queue entry — the whole interaction is "I will attend" or "I will
not attend".

Publishing is gated to the Programme Admin role, enforced in the view layer
(step/roles.py) rather than here, matching how every other permission check
in this codebase lives outside the models. Up to five people hold the role
by operational policy; that is deliberately not a hard cap in code — an
arbitrary limit that blocks a legitimate sixth appointment at the wrong
moment is worse than the problem it prevents (fix step plan.md §5.2).
"""

from django.conf import settings
from django.db import models

from step.models.roster import Educator


class Announcement(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="announcements",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    published_at = models.DateTimeField(auto_now_add=True)
    respond_by = models.DateField(
        null=True, blank=True, help_text="Last day a teacher may change their RSVP.",
    )
    requires_response = models.BooleanField(
        default=False, help_text="Off means pure news: nothing for the teacher to answer.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return self.title

    def responding_has_closed(self, today) -> bool:
        """Past the last day to answer. No `respond_by` means it never closes."""
        return self.respond_by is not None and self.respond_by < today


class AnnouncementResponse(models.Model):
    """One answer per teacher, changeable until `respond_by` — enforced by
    the unique constraint below, which doubles as the (announcement, educator)
    lookup index the regional activity report needs (fix step plan.md §6)."""

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="responses")
    educator = models.ForeignKey(Educator, on_delete=models.CASCADE, related_name="announcement_responses")
    attending = models.BooleanField()
    responded_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-responded_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "educator"], name="step_announcement_response_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.educator.full_name} — {'attending' if self.attending else 'not attending'}"
