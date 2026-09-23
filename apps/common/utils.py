import secrets

from django.conf import settings


def generate_numeric_code(length: int = 6) -> str:
    """Generate a numeric code, used for OTPs. Uses the OS CSPRNG."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def get_client_ip(request) -> str | None:
    """Caller IP. X-Forwarded-For is only trusted when the app runs behind a
    proxy that sets it (USE_X_FORWARDED_FOR=True); otherwise it is spoofable."""
    if getattr(settings, "USE_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None
