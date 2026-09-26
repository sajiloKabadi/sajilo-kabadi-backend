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
    "apps.common.middleware.MinAppVersionMiddleware",
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
# Reuse DB connections across requests instead of reconnecting every time.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Per-process cache: rate board, throttling. Point at Redis when running
# several app servers so they share it.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "sajilokabadi",
        "OPTIONS": {"MAX_ENTRIES": 5000},
    }
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
    "DEFAULT_AUTHENTICATION_CLASSES": ("apps.accounts.authentication.ActiveUserJWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # JSON only: no browsable-API HTML rendering on every response.
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="60/min"),
        "user": env("THROTTLE_USER", default="300/min"),
    },
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
    "DESCRIPTION": "Sajilo Kabadi API v2 (contract 2026-09-24). Every response uses the success/error envelope.",
    "VERSION": "2.0.0",
    "COMPONENT_SPLIT_REQUEST": True,
    # Listed first in Swagger; untagged endpoints stay under "api".
    "TAGS": [
        {
            "name": "Authentication",
            "description": "Phone + SMS OTP sign-in. Call in order: request, (resend), verify; refresh on 401 token_invalid.",
        },
        {"name": "Account", "description": "The signed-in user: profile, avatar, device, notification settings."},
        {"name": "Seller dashboard", "description": "Seller Home in one call."},
        {"name": "Rates", "description": "Today's material rates."},
        {"name": "Addresses", "description": "Seller pickup addresses."},
        {"name": "Pickups", "description": "Selling: availability, quote, booking, tracking."},
        {"name": "Weigh-in", "description": "Seller side of the weighing sheet."},
        {"name": "Drop-off centers", "description": "Kabadi centers near a point."},
        {"name": "Wallet", "description": "Balance, history, payout methods, withdrawals, statement."},
        {"name": "Collector", "description": "Collector home, jobs, status, location, weights."},
        {"name": "Disputes", "description": "Help & disputes."},
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
OTP_IP_LIMIT_PER_HOUR = env.int("OTP_IP_LIMIT_PER_HOUR", default=20)

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

# Old builds get 426 app_update_required (contract 1.4). Empty disables it.
MIN_APP_VERSION = env("MIN_APP_VERSION", default="")

# --- Marketplace rules (contract v2) ----------------------------------------

DEFAULT_CITY = env("DEFAULT_CITY", default="Kathmandu")
# Kathmandu valley as (min_lat, min_lng, max_lat, max_lng).
SERVICE_AREA_BBOX = tuple(env.list("SERVICE_AREA_BBOX", cast=float, default=[27.55, 85.18, 27.82, 85.55]))
RATE_CACHE_SECONDS = env.int("RATE_CACHE_SECONDS", default=600)

PICKUP_SLOTS = env.list(
    "PICKUP_SLOTS",
    default=[
        "08:00-09:00",
        "09:00-10:00",
        "10:30-11:00",
        "11:00-12:00",
        "13:00-14:00",
        "14:00-15:00",
        "15:00-16:00",
        "16:00-17:00",
    ],
)
PICKUP_DAYS_AHEAD = env.int("PICKUP_DAYS_AHEAD", default=6)
PICKUP_SLOT_CAPACITY = env.int("PICKUP_SLOT_CAPACITY", default=5)
PICKUP_MIN_LEAD_MINUTES = env.int("PICKUP_MIN_LEAD_MINUTES", default=30)
MAX_ACTIVE_PICKUPS = env.int("MAX_ACTIVE_PICKUPS", default=3)

# Delivery fees (contract 8.3).
PICKUP_FREE_ABOVE_KG = env.int("PICKUP_FREE_ABOVE_KG", default=10)
PICKUP_SMALL_LOAD_FEE = env.int("PICKUP_SMALL_LOAD_FEE", default=60)
TRUCK_BASE_FEE = env.int("TRUCK_BASE_FEE", default=400)
TRUCK_FEE_PER_KM = env.int("TRUCK_FEE_PER_KM", default=30)

# Collector's cut shown as "You earn (estimate)": per kg (with a floor) + delivery fee.
COLLECTOR_EARNING_PER_KG = env.float("COLLECTOR_EARNING_PER_KG", default=8)
COLLECTOR_EARNING_MIN = env.int("COLLECTOR_EARNING_MIN", default=50)
COLLECTOR_AVG_SPEED_KMH = env.float("COLLECTOR_AVG_SPEED_KMH", default=18)
COLLECTOR_OFFLINE_AFTER_SECONDS = env.int("COLLECTOR_OFFLINE_AFTER_SECONDS", default=600)
JOB_RADIUS_KM = env.float("JOB_RADIUS_KM", default=5)
PHONE_VISIBLE_HOURS_AFTER = env.int("PHONE_VISIBLE_HOURS_AFTER", default=24)

DROPOFF_DEFAULT_RADIUS_KM = env.float("DROPOFF_DEFAULT_RADIUS_KM", default=2)
DROPOFF_MAX_RADIUS_KM = env.float("DROPOFF_MAX_RADIUS_KM", default=20)

# Poll intervals the API tells the app to use (contract 8.6, 9.1).
POLL_ON_THE_WAY_SECONDS = 15
POLL_DEFAULT_SECONDS = 60
POLL_WEIGH_LIVE_SECONDS = 5

MIN_WITHDRAWAL = env.int("MIN_WITHDRAWAL", default=100)
PAYOUTS_ON_HOLD = env.bool("PAYOUTS_ON_HOLD", default=False)

# --- Push notifications (contract 15) --------------------------------------

PUSH_BACKEND = env("PUSH_BACKEND", default="apps.notifications.backends.push_console.ConsolePushBackend")
FCM_PROJECT_ID = env("FCM_PROJECT_ID", default="")
FCM_CREDENTIALS_FILE = env("FCM_CREDENTIALS_FILE", default="")

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
