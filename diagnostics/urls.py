"""Diagnostics URLs, included under /diagnostics/ by config/urls.py."""

from django.urls import path

from diagnostics import views

app_name = "diagnostics"

urlpatterns = [
    path("", views.paper_index, name="paper_index"),
    path("listening/", views.listening_bank, name="listening_bank"),
    path("<int:grade>/", views.grade_detail, name="grade_detail"),
    path("<int:grade>/class/<int:number>/", views.class_pack, name="class_pack"),
    path("<int:grade>/<str:variant>/", views.paper_detail, name="paper_detail"),
    path(
        "<int:grade>/<str:variant>/download/<str:kind>/",
        views.paper_file,
        name="paper_file",
    ),
]
