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
    path("classes/", include("step.classes_urls")),
    path("activities/", include("step.activities_urls")),
]


# admin_urls.py's own patterns already carry the "manage/" prefix (spec: the
# admin screens live at /manage/, /manage/review/, /manage/teachers/), so
# this include is unprefixed to avoid doubling it to /manage/manage/.
urlpatterns += [path("", include("step.admin_urls"))]
