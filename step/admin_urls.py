"""URLs for the administration screens, included from step/urls.py under
`manage/`. Kept in a separate module so the file that owns the teacher-facing
routes (step/urls.py, owned by another session working in parallel) only
ever needs one `include()` line added to it, never a merge of two people's
url patterns.

Mounted at "manage/", not "admin/": STEP now owns the site root (config/urls.py),
and Django's own admin.site.urls already claims "/admin/" for the built-in
backend. Reusing that segment here would put this dashboard behind Django's
admin login instead of its own — the URL *names* below are unchanged, so
every `{% url %}`/`reverse()` call elsewhere kept working across the rename.
"""

from django.urls import path

from step import admin_views

urlpatterns = [
    path("manage/", admin_views.dashboard, name="admin-dashboard"),
    path("manage/review/", admin_views.review_queue, name="admin-review-queue"),
    path("manage/review/<int:pk>/", admin_views.review_detail, name="admin-review-detail"),
    path("manage/teachers/", admin_views.teacher_directory, name="admin-teachers"),
    path("manage/teachers/<int:pk>/", admin_views.teacher_detail, name="admin-teacher-detail"),
    path("manage/announcements/", admin_views.announcement_list, name="admin-announcements"),
    path("manage/announcements/new/", admin_views.announcement_create, name="admin-announcement-new"),
]
