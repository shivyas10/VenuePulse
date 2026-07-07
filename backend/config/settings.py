"""
Django settings for the ops dashboard backend.

Configuration is environment-driven (12-factor style) so the same codebase
runs against SQLite for quick local iteration and against Postgres + Redis
via docker-compose without any code changes.
"""
from pathlib import Path
import os

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "channels",
    "ops",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---------------------------------------------------------------
# Defaults to local SQLite so the app runs with zero external services.
# docker-compose / production set DATABASE_URL to point at Postgres.
DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
    )
}

# --- Channel layer -----------------------------------------------------------
# Redis-backed layer when REDIS_URL is configured (docker-compose / prod);
# falls back to the in-memory layer for single-process local development.
# In-memory only fans out within one process, which is fine for `daphne`
# running as a single worker, but would NOT work across multiple worker
# processes - that's the reason production must set REDIS_URL.
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# Single group-wide timezone assumption - see README ("Assumptions").
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Daphne (unlike `runserver`) doesn't auto-serve static files, and this
    # app has no separate reverse proxy in front of it - WhiteNoise serves
    # the Django admin's CSS/JS directly from the ASGI app in every
    # environment (native run and docker-compose alike).
    # Plain (non-manifest) storage - simpler for a local/dev deployment:
    # no risk of a template failing to render because collectstatic wasn't
    # re-run after a static asset changed.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ----------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# --- CORS / CSRF ----------------------------------------------------------
# The React dev server runs on a different origin, so cross-origin
# requests need explicit allow-listing with credentials enabled for the
# session cookie to travel with fetch()/WebSocket requests.
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
SESSION_COOKIE_SAMESITE = "Lax"

LOGIN_URL = "/api/auth/login/"

# Shared secret POS terminals present when pushing transactions. Distinct
# from ops-user session auth - see ops/permissions.py.
POS_INGEST_TOKEN = os.environ.get("POS_INGEST_TOKEN", "dev-pos-token-change-me")

# --- Anomaly detection thresholds (tunable) --------------------------------
# Deliberately simple, fixed thresholds rather than per-venue historical
# baselines - see README for the trade-off discussion and what a production
# version (rolling per-venue baseline) would look like instead.
ANOMALY_SALES_DROP_WINDOW_MINUTES = int(os.environ.get("ANOMALY_SALES_DROP_WINDOW_MINUTES", 60))
ANOMALY_SALES_DROP_THRESHOLD = float(os.environ.get("ANOMALY_SALES_DROP_THRESHOLD", 0.4))
ANOMALY_SALES_DROP_MIN_BASELINE = float(os.environ.get("ANOMALY_SALES_DROP_MIN_BASELINE", 50))

ANOMALY_VOID_REFUND_WINDOW_MINUTES = int(os.environ.get("ANOMALY_VOID_REFUND_WINDOW_MINUTES", 60))
ANOMALY_VOID_REFUND_RATIO_THRESHOLD = float(os.environ.get("ANOMALY_VOID_REFUND_RATIO_THRESHOLD", 0.2))
ANOMALY_VOID_REFUND_MIN_COUNT = int(os.environ.get("ANOMALY_VOID_REFUND_MIN_COUNT", 5))

# Minimum seconds between full dashboard recomputes broadcast to all
# connected clients - decouples broadcast cost from transaction volume.
BROADCAST_MIN_INTERVAL_SECONDS = float(os.environ.get("BROADCAST_MIN_INTERVAL_SECONDS", 1.0))
