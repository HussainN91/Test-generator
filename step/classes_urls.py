from django.urls import path

from step import classes_views

urlpatterns = [
    path("", classes_views.class_list, name="class_list"),
    path("new/", classes_views.class_create, name="class_create"),
    path("<int:pk>/", classes_views.class_detail, name="class_detail"),
    path("<int:pk>/students/new/", classes_views.student_create, name="student_create"),
    path("students/<int:pk>/", classes_views.student_detail, name="student_detail"),
    path("students/<int:pk>/notes/new/", classes_views.note_create, name="note_create"),
]
