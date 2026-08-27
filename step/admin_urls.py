"""URLs for the administration screens, included from step/urls.py under
`admin/`. Kept in a separate module so the file that owns the teacher-facing
routes (step/urls.py, owned by another session working in parallel) only
ever needs one `include()` line added to it, never a merge of two people's
url patterns.
"""

from django.urls import path

from step import admin_views

urlpatterns = [
    path("admin/", admin_views.dashboard, name="admin-dashboard"),
    path("admin/review/", admin_views.dashboard, name="admin-review-queue"),
    path("admin/teachers/", admin_views.dashboard, name="admin-teachers"),
]
