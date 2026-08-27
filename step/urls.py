"""URL map for the educator-facing screens.

Paths are readable rather than terse: a teacher who ends up looking at the
address bar should still recognise where they are.
"""

from django.urls import include, path

from step import views

app_name = "step"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("work/<int:pk>/", views.obligation, name="obligation"),
    path("submissions/", views.submissions, name="submissions"),
    path("feedback/", views.feedback, name="feedback"),
]


# admin_urls.py's own patterns already carry the "admin/" prefix (spec: the
# admin screens live at /step/admin/, /step/admin/review/, /step/admin/teachers/),
# so this include is unprefixed to avoid doubling it to /step/admin/admin/.
urlpatterns += [path("", include("step.admin_urls"))]
