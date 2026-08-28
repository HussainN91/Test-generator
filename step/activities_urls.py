from django.urls import path

from step import activities_views

urlpatterns = [
    path("", activities_views.activity_list, name="activity_list"),
    path("new/", activities_views.activity_create, name="activity_create"),
    path("<int:pk>/", activities_views.activity_detail, name="activity_detail"),
    path(
        "<int:pk>/participants/new/",
        activities_views.activity_participant_create,
        name="activity_participant_create",
    ),
    path(
        "<int:pk>/sessions/new/",
        activities_views.activity_session_create,
        name="activity_session_create",
    ),
    path(
        "<int:pk>/sessions/<int:session_pk>/log/",
        activities_views.activity_session_log,
        name="activity_session_log",
    ),
]
