"""URL map. Teacher views live at the root; the admin doubles as the review queue."""

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.static import serve as serve_static

from assembly import views as assembly_views
from bank import views as bank_views
from config import views as config_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Not DEBUG-gated: low-traffic internal tool, no separate static-file host
    # in front of it. django.views.static.serve is fine at this volume.
    path("media/<path:path>", serve_static, {"document_root": settings.MEDIA_ROOT}),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Where sign-in lands. A view rather than a fixed LOGIN_REDIRECT_URL
    # because the right destination depends on the role (config/views.py).
    path("after-sign-in/", config_views.post_login, name="post_login"),
    path("", assembly_views.builder, name="builder"),
    path("batch/<int:pk>/", assembly_views.batch_preview, name="batch_preview"),
    path("batch/<int:pk>/print/", assembly_views.batch_print, name="batch_print"),
    path("batch/<int:pk>/docx/", assembly_views.batch_docx, name="batch_docx"),
    path("coverage/", bank_views.coverage, name="coverage"),
    path("diagnostics/", include("diagnostics.urls")),
    path("step/", include("step.urls")),
]
