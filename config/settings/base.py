"""
Base settings shared by every environment.
Environment-specific overrides live in dev.py / prod.py.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# --- Applications -----------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

# Every business module lives here. Keep this list as the single map of
# what modules exist in the monolith.
LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.sellers",
    "apps.collectors",
    "apps.materials",
    "apps.pickups",
    "apps.wallet",
    "apps.dropoff",
    "apps.impact",
    "apps.notifications",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.common.middleware.ApiCommonMiddleware",
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

# --- Database ----------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"postgres://{env('DB_USER', default='sajilokabadi')}:"
        f"{env('DB_PASSWORD', default='sajilokabadi')}@"
        f"{env('DB_HOST', default='localhost')}:"
        f"{env('DB_PORT', default='5432')}/"
        f"{env('DB_NAME', default='sajilokabadi')}",
    )
}

# --- Auth ----------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = []  # phone+OTP only — no passwords in this app

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# --- I18N ----------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kathmandu"
USE_I18N = True
USE_TZ = True

# --- Static / media -----------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF / JWT -------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=env.int("JWT_ACCESS_LIFETIME_SECONDS", default=3600)),
    "REFRESH_TOKEN_LIFETIME": timedelta(seconds=env.int("JWT_REFRESH_LIFETIME_SECONDS", default=2592000)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SajiloKabadi API",
    "DESCRIPTION": "Scrap collection marketplace — rates, pickups, wallet, impact.",
    "VERSION": "1.0.0",
    # Listed first in Swagger; untagged endpoints stay under "api".
    "TAGS": [
        {
            "name": "Authentication",
            "description": "Phone + SMS OTP sign-in. Call in order: request, (resend), verify; refresh on 401 token_invalid.",
        },
        {"name": "Account", "description": "The signed-in user. Needs Authorization: Bearer <access>."},
    ],
}

CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=True)

# --- Celery ----------------------------------------------------------------

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# --- Domain-specific settings ------------------------------------------

# OTP values the Flutter client has compiled in: 6 boxes, 5-minute copy,
# 30-second resend countdown. Change them together with the app.
OTP_LENGTH = env.int("OTP_LENGTH", default=6)
OTP_EXPIRY_SECONDS = env.int("OTP_EXPIRY_SECONDS", default=300)
OTP_RESEND_AFTER_SECONDS = env.int("OTP_RESEND_AFTER_SECONDS", default=30)
OTP_MAX_VERIFY_ATTEMPTS = env.int("OTP_MAX_VERIFY_ATTEMPTS", default=5)
OTP_LOCKOUT_SECONDS = env.int("OTP_LOCKOUT_SECONDS", default=600)
OTP_PHONE_LIMIT_PER_HOUR = env.int("OTP_PHONE_LIMIT_PER_HOUR", default=5)
OTP_PHONE_LIMIT_PER_DAY = env.int("OTP_PHONE_LIMIT_PER_DAY", default=20)
OTP_IP_LIMIT_PER_HOUR = env.int("OTP_IP_LIMIT_PER_HOUR", default=30)

# Testing only: a fixed code issued instead of a random one, with no SMS
# sent. Applies to OTP_TEST_PHONES, or to every number when that is empty.
# Leave OTP_TEST_CODE blank to disable.
OTP_TEST_CODE = env("OTP_TEST_CODE", default="")
OTP_TEST_PHONES = env.list("OTP_TEST_PHONES", default=[])
if OTP_TEST_CODE and not (OTP_TEST_CODE.isascii() and OTP_TEST_CODE.isdigit() and len(OTP_TEST_CODE) == OTP_LENGTH):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(f"OTP_TEST_CODE must be exactly {OTP_LENGTH} digits")

# Only enable behind a proxy that overwrites X-Forwarded-For.
USE_X_FORWARDED_FOR = env.bool("USE_X_FORWARDED_FOR", default=False)

# --- SMS -------------------------------------------------------------------

SMS_BACKEND = env("SMS_BACKEND", default="apps.notifications.backends.aakash.AakashSMSBackend")
# "celery" (needs a worker), "thread" (in-process) or "sync" (blocks the request).
SMS_DISPATCH = env("SMS_DISPATCH", default="celery")
# Android SMS Retriever hash (11 chars). Debug and release builds have
# different hashes, so set the one matching the build this server serves.
SMS_APP_HASH = env("SMS_APP_HASH", default="")

AAKASH_SMS_AUTH_TOKEN = env("AAKASH_SMS_AUTH_TOKEN", default="")
AAKASH_SMS_API_URL = env("AAKASH_SMS_API_URL", default="https://sms.aakashsms.com/sms/v3/send")
AAKASH_SMS_TIMEOUT_SECONDS = env.int("AAKASH_SMS_TIMEOUT_SECONDS", default=10)
