"""Django settings for the English Test Generator.

Deployment note (spec 6): this app has **no LLM dependency at runtime**. It
reads from the item bank only. No API key is read here, and none is needed to
run the server.

Environment variables (all optional in development):
    TESTGEN_SECRET_KEY   required in production
    TESTGEN_DEBUG        "1"/"0", defaults to "1"
    TESTGEN_ALLOWED_HOSTS  comma-separated
    TESTGEN_DB_PATH      SQLite file location
    TESTGEN_DB_ENGINE    "sqlite" (default) or "postgres"/"postgresql"
    TESTGEN_DB_NAME      Postgres database name, when TESTGEN_DB_ENGINE=postgres
    TESTGEN_DB_USER      Postgres user, when TESTGEN_DB_ENGINE=postgres
    TESTGEN_DB_PASSWORD  Postgres password, when TESTGEN_DB_ENGINE=postgres
    TESTGEN_DB_HOST      Postgres host, when TESTGEN_DB_ENGINE=postgres
    TESTGEN_DB_PORT      Postgres port, when TESTGEN_DB_ENGINE=postgres
    STEP_ROSTER_MATCH_KEYS  comma-separated identity keys, in priority order
                            (STEP Platform; see step/identity.py)
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = _env_bool("TESTGEN_DEBUG", True)

SECRET_KEY = os.environ.get(
    "TESTGEN_SECRET_KEY",
    "django-insecure-dev-only-replace-me-before-deploying-to-the-vps",
)
if not DEBUG and SECRET_KEY.startswith("django-insecure"):
    raise RuntimeError("Set TESTGEN_SECRET_KEY before running with TESTGEN_DEBUG=0.")

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("TESTGEN_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("TESTGEN_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "content",
    "bank",
    "assembly",
    "diagnostics",
    "step",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite is the default so a developer machine, and the existing test suite,
# need no database server. Production sets TESTGEN_DB_ENGINE=postgres — see
# the spine spec §8. The cutover is a deployment step, never a code change.
if os.environ.get("TESTGEN_DB_ENGINE", "sqlite").strip().lower() in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("TESTGEN_DB_NAME", "testgen"),
            "USER": os.environ.get("TESTGEN_DB_USER", "testgen"),
            "PASSWORD": os.environ.get("TESTGEN_DB_PASSWORD", ""),
            "HOST": os.environ.get("TESTGEN_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("TESTGEN_DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("TESTGEN_DB_PATH", BASE_DIR / "db.sqlite3"),
            "OPTIONS": {"init_command": "PRAGMA journal_mode=WAL;"},
        }
    }

# --- STEP Platform --------------------------------------------------------
# Which identifiers match a signup to a roster row, in priority order.
# The client has not yet decided what signup asks for (email + passport, or
# email + PINFL), so this is configuration rather than schema. Known values:
# "pinfl", "passport_no", "email".
STEP_ROSTER_MATCH_KEYS = [
    k.strip()
    for k in os.environ.get("STEP_ROSTER_MATCH_KEYS", "email").split(",")
    if k.strip()
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Plain (non-manifest) so collectstatic doesn't hard-fail on a template
    # referencing a static file that doesn't exist yet — see whitenoise docs.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Read-only client source material for the diagnostic test bank.
DIAGNOSTICS_SOURCE_DIR = Path(
    os.environ.get("DIAGNOSTICS_SOURCE_DIR", r"D:\Diagnostics Gate")
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "builder"
LOGOUT_REDIRECT_URL = "login"

#: Where `import_guide` looks for the source .txt guides by default.
GUIDE_SOURCE_DIR = Path(os.environ.get("TESTGEN_GUIDE_DIR", BASE_DIR))

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"

    # Off by default: turning these on before TLS actually works locks you out
    # of your own server. Set TESTGEN_SSL=1 once HTTPS is serving.
    if _env_bool("TESTGEN_SSL", False):
        SECURE_SSL_REDIRECT = True
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
        # Behind a reverse proxy, Django needs to be told the original scheme.
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
