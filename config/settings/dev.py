from .base import *

DEBUG = True

DATABASES["default"] = env.db(
    "DATABASE_URL",
    default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),
)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# In dev, print the OTP to console unless .env points at a real gateway
# (SMS_BACKEND=apps.notifications.backends.aakash.AakashSMSBackend).
SMS_BACKEND = env("SMS_BACKEND", default="apps.notifications.backends.console.ConsoleSMSBackend")
SMS_DISPATCH = env("SMS_DISPATCH", default="thread")
