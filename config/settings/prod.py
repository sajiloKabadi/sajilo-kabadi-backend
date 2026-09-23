from .base import *

DEBUG = False

# Nginx terminates TLS and forwards plain HTTP to gunicorn; trust its
# X-Forwarded-Proto so Django knows the original request was HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
# The container healthcheck and deploy script call /health/ over plain HTTP
# on 127.0.0.1, so it must not be redirected.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Needed for form POSTs such as the Django admin login over HTTPS.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# A fixed test code for every number would let anyone sign in as anyone.
if OTP_TEST_CODE and not OTP_TEST_PHONES:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("OTP_TEST_CODE in production requires OTP_TEST_PHONES")

# Everything to stdout/stderr so `docker logs` shows it.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
