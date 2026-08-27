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

urlpatterns += [path("admin/", include("step.admin_urls"))]
