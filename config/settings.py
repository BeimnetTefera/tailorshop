"""Django settings for the tailor shop web app."""
import os
import tempfile
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Running on Vercel (set by Vercel itself, and by api/index.py). Only /tmp is writable there.
ON_VERCEL = os.environ.get("VERCEL") == "1" or os.environ.get("ON_VERCEL") == "1"
# PostgreSQL connection string (Supabase, or Vercel's Neon Postgres, which may name it
# POSTGRES_URL). Without it the app uses SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL", "")
# Throwaway demo: on Vercel without a real database. The SQLite file lives in /tmp, is
# wiped whenever an instance restarts, and is re-seeded with demo data.
DEMO_MODE = ON_VERCEL and not DATABASE_URL
# With a real database on Vercel the demo data is loaded once into an empty database,
# and the demo accounts are kept working; set DEMO_DATA=0 when the shop goes live.
DEMO_DATA = os.environ.get("DEMO_DATA", "1") == "1"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "0" if ON_VERCEL else "1") == "1"
ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", ".vercel.app" if ON_VERCEL else "localhost,127.0.0.1"
).split(",")
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "https://*.vercel.app" if ON_VERCEL else ""
).split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Every page needs a signed-in user except the login page (Django 5.1+).
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "shop.pin.SessionGuardMiddleware",
    "shop.middleware.UserLanguageMiddleware",
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shop.context_processors.navigation",
                "shop.context_processors.demo",
                "shop.context_processors.roles",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if DATABASE_URL:
    # Serverless functions open a fresh connection per request; use Supabase's pooler
    # (port 6543, transaction mode), which doesn't support server-side cursors.
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=0,
                                                  ssl_require=DATABASE_URL.startswith("postgres"))}
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# English by default; each person can switch to Amharic (saved on their profile).
# Translations live in locale/am/LC_MESSAGES/django.po; build the .mo with
# `python scripts/compile_translations.py` after editing it.
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("am", "አማርኛ")]
LOCALE_PATHS = [BASE_DIR / "locale"]
LANGUAGE_COOKIE_NAME = "language"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
TIME_ZONE = "Africa/Addis_Ababa"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Photos are always served through the app (shop.views.media_file) so only signed-in
# users can see them, whether they live on disk or in Supabase Storage.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Supabase Storage through its S3-compatible API: Storage > Settings > S3 connection.
STORAGE_BUCKET = os.environ.get("STORAGE_BUCKET", "")
if STORAGE_BUCKET:
    STORAGES = {
        "default": {
            "BACKEND": "shop.storage.PrivateS3Storage",
            "OPTIONS": {
                "bucket_name": STORAGE_BUCKET,
                "endpoint_url": os.environ.get("STORAGE_ENDPOINT_URL", ""),
                "region_name": os.environ.get("STORAGE_REGION", ""),
                "access_key": os.environ.get("STORAGE_ACCESS_KEY_ID", ""),
                "secret_key": os.environ.get("STORAGE_SECRET_ACCESS_KEY", ""),
                "file_overwrite": False,
            },
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
elif DATABASE_URL and ON_VERCEL:
    # A database but no file storage: keep photos in the database (shrunk on upload), so
    # every server instance sees them. Fine for one shop; Supabase Storage scales further.
    STORAGES = {
        "default": {"BACKEND": "shop.storage.DatabaseStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "shop:dashboard"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if ON_VERCEL:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    # WhiteNoise serves /static/ straight from the app folders (no collectstatic step).
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    WHITENOISE_USE_FINDERS = True
    STATIC_ROOT = None

if DEMO_MODE:
    DATABASES["default"]["NAME"] = Path(tempfile.gettempdir()) / "tailorshop-demo.sqlite3"
    MEDIA_ROOT = Path(tempfile.gettempdir()) / "tailorshop-media"
    # Instances don't share /tmp, so keep logins in a signed cookie instead of the database.
    SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
