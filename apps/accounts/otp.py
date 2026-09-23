"""OTP issuing/verification service: the one place other code should call
into for phone-based auth, instead of touching OTPRequest directly.

Contract: docs/api/auth_and_dashboard.md, sections 2-4. Security baseline
(S1-S6 in the auth API PDF):
  S1 send limits per phone (hourly + daily) and per IP (hourly)
  S2 OTP_MAX_VERIFY_ATTEMPTS wrong codes kill the challenge and lock the
     number out for OTP_LOCKOUT_SECONDS
  S3 single-use; issuing a new code invalidates every open one for the number
  S4 only an HMAC of the code is stored
  S5 constant-time comparison
  S6 codes come from the OS CSPRNG
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from apps.common.exceptions import ApiError
from apps.common.i18n import format_wait
from apps.common.utils import generate_numeric_code
from apps.notifications.services import send_sms_async

from .messages import attempts_left_text, msg
from .models import OTPRequest, User, UserDevice

SMS_MAX_BYTES = 140


@dataclass
class VerifyResult:
    user: User
    is_new_user: bool


# --- Public API --------------------------------------------------------------


def request_otp(*, phone: str, country_code: str, role: str, language: str | None, ip: str | None, lang: str) -> dict:
    existing = User.objects.filter(phone_number=phone).first()
    if existing is not None and not existing.is_active:
        raise _error(status.HTTP_403_FORBIDDEN, "account_blocked", msg("account_blocked", lang))

    _check_send_limits(phone, ip, lang)
    otp = _issue(phone=phone, country_code=country_code, role=role, language=language, ip=ip)
    return challenge_payload(otp, is_new_user=existing is None)


def resend_otp(*, otp_request_id, ip: str | None, lang: str) -> dict:
    previous = OTPRequest.objects.filter(id=otp_request_id, purpose=OTPRequest.Purpose.LOGIN).first()
    if previous is None or previous.consumed_at or previous.invalidated_at:
        raise _not_found(lang)

    wait = _seconds_until(previous.created_at + timedelta(seconds=settings.OTP_RESEND_AFTER_SECONDS))
    if wait > 0:
        raise _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "resend_too_soon",
            msg("resend_too_soon", lang, wait=format_wait(wait, lang)),
            data={"retry_after": wait},
        )

    _check_send_limits(previous.phone_number, ip, lang)
    if previous.locked_at:
        # Lockout has run out (the limit check above would have caught it
        # otherwise), but a killed challenge is never revived.
        raise _not_found(lang)

    existing = User.objects.filter(phone_number=previous.phone_number).first()
    if existing is not None and not existing.is_active:
        raise _error(status.HTTP_403_FORBIDDEN, "account_blocked", msg("account_blocked", lang))

    otp = _issue(
        phone=previous.phone_number,
        country_code=previous.country_code,
        role=previous.role,
        language=previous.language,
        ip=ip,
    )
    return challenge_payload(otp, is_new_user=existing is None)


def verify_otp(*, otp_request_id, phone: str, otp: str, role: str, device: dict | None, lang: str) -> VerifyResult:
    # Attempt counting must be committed even when the code is wrong, so the
    # error is decided inside the transaction and raised after it commits.
    failure = None
    with transaction.atomic():
        challenge = (
            OTPRequest.objects.select_for_update().filter(id=otp_request_id, purpose=OTPRequest.Purpose.LOGIN).first()
        )
        failure = _check_challenge(challenge, phone, lang)
        if failure is None and not _code_matches(challenge, otp):
            failure = _record_wrong_code(challenge, lang)

    if failure is not None:
        raise failure

    with transaction.atomic():
        challenge = OTPRequest.objects.select_for_update().get(id=challenge.id)
        if not challenge.is_open:  # consumed by a concurrent request
            raise _not_found(lang)

        user = User.objects.select_for_update().filter(phone_number=phone).first()
        if user is not None and not user.is_active:
            raise _error(status.HTTP_403_FORBIDDEN, "account_blocked", msg("account_blocked", lang))
        if user is not None and user.role != role:
            raise _error(status.HTTP_403_FORBIDDEN, "role_mismatch", msg("role_mismatch", lang))

        challenge.consumed_at = timezone.now()
        challenge.save(update_fields=["consumed_at", "updated_at"])

        is_new_user = user is None
        if is_new_user:
            user = User.objects.create_user(
                phone_number=phone,
                country_code=challenge.country_code,
                role=role,
                language=challenge.language or User.Language.ENGLISH,
                is_phone_verified=True,
            )
        else:
            changed = []
            if not user.is_phone_verified:
                user.is_phone_verified = True
                changed.append("is_phone_verified")
            if challenge.language and challenge.language != user.language:
                user.language = challenge.language
                changed.append("language")
            if changed:
                user.save(update_fields=[*changed, "updated_at"])

        if device:
            _save_device(user, device)
        update_last_login(None, user)

    return VerifyResult(user=user, is_new_user=is_new_user)


def mask_phone(country_code: str, phone: str) -> str:
    return f"{country_code} {phone[:2]}•••• {phone[-4:]}"


def challenge_payload(otp: OTPRequest, *, is_new_user: bool) -> dict:
    return {
        "otp_request_id": str(otp.id),
        "phone_masked": mask_phone(otp.country_code, otp.phone_number),
        "otp_length": settings.OTP_LENGTH,
        "expires_in": settings.OTP_EXPIRY_SECONDS,
        "resend_after": settings.OTP_RESEND_AFTER_SECONDS,
        "is_new_user": is_new_user,
    }


# --- Issuing -----------------------------------------------------------------


def _issue(*, phone: str, country_code: str, role: str, language: str | None, ip: str | None) -> OTPRequest:
    use_test_code = _uses_test_code(phone)
    code = settings.OTP_TEST_CODE if use_test_code else generate_numeric_code(settings.OTP_LENGTH)
    now = timezone.now()
    with transaction.atomic():
        OTPRequest.objects.filter(
            phone_number=phone,
            purpose=OTPRequest.Purpose.LOGIN,
            consumed_at__isnull=True,
            invalidated_at__isnull=True,
        ).update(invalidated_at=now)

        otp = OTPRequest(
            phone_number=phone,
            country_code=country_code,
            role=role,
            language=language,
            purpose=OTPRequest.Purpose.LOGIN,
            ip_address=ip,
            expires_at=now + timedelta(seconds=settings.OTP_EXPIRY_SECONDS),
        )
        otp.code_hash = _hash_code(otp.id, code)
        otp.save()
        if not use_test_code:
            send_sms_async(to=phone, message=_sms_body(code))
    return otp


def _uses_test_code(phone: str) -> bool:
    """Testing shortcut: OTP_TEST_CODE is issued instead of a random code
    and no SMS is sent. Limited to OTP_TEST_PHONES when that list is set
    (production refuses to start without it, see settings/prod.py)."""
    if not settings.OTP_TEST_CODE:
        return False
    return not settings.OTP_TEST_PHONES or phone in settings.OTP_TEST_PHONES


def _sms_body(code: str) -> str:
    """Shaped for Android SMS Retriever (`<#>` prefix, app hash on the last
    line, <= 140 bytes). iOS ignores the markers and reads the code."""
    minutes = max(settings.OTP_EXPIRY_SECONDS // 60, 1)
    expiry = f"{minutes} minute" + ("" if minutes == 1 else "s")
    head = f"<#> {code} is your Sajilo Kabadi code. It expires in {expiry}."
    warning = " Sajilo Kabadi will never call you to ask for this code."
    tail = f"\n{settings.SMS_APP_HASH}" if settings.SMS_APP_HASH else ""

    body = head + warning + tail
    if len(body.encode("utf-8")) > SMS_MAX_BYTES:
        body = head + tail
    return body


def _hash_code(otp_id, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{otp_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _code_matches(challenge: OTPRequest, code: str) -> bool:
    return hmac.compare_digest(challenge.code_hash, _hash_code(challenge.id, code))


# --- Limits ------------------------------------------------------------------


def _check_send_limits(phone: str, ip: str | None, lang: str) -> None:
    now = timezone.now()
    waits = []

    lockout = timedelta(seconds=settings.OTP_LOCKOUT_SECONDS)
    locked = (
        OTPRequest.objects.filter(phone_number=phone, locked_at__gte=now - lockout)
        .order_by("-locked_at")
        .values_list("locked_at", flat=True)
        .first()
    )
    if locked:
        waits.append(_seconds_until(locked + lockout))

    windows = [
        (Q(phone_number=phone), 3600, settings.OTP_PHONE_LIMIT_PER_HOUR),
        (Q(phone_number=phone), 86400, settings.OTP_PHONE_LIMIT_PER_DAY),
    ]
    if ip:
        windows.append((Q(ip_address=ip), 3600, settings.OTP_IP_LIMIT_PER_HOUR))

    for scope, window, limit in windows:
        since = now - timedelta(seconds=window)
        sent = list(
            OTPRequest.objects.filter(scope, created_at__gte=since)
            .order_by("-created_at")
            .values_list("created_at", flat=True)[:limit]
        )
        if len(sent) >= limit:
            # The oldest send counted against the limit has to age out.
            waits.append(_seconds_until(sent[-1] + timedelta(seconds=window)))

    wait = max(waits, default=0)
    if wait > 0:
        raise _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "otp_rate_limited",
            msg("otp_rate_limited", lang, wait=format_wait(wait, lang)),
            data={"retry_after": wait},
        )


def _check_challenge(challenge: OTPRequest | None, phone: str, lang: str) -> ApiError | None:
    if challenge is None or challenge.phone_number != phone:
        return _not_found(lang)
    if challenge.locked_at:
        wait = _seconds_until(challenge.locked_at + timedelta(seconds=settings.OTP_LOCKOUT_SECONDS))
        return _attempts_exceeded(wait, lang) if wait > 0 else _not_found(lang)
    if challenge.consumed_at or challenge.invalidated_at:
        return _not_found(lang)
    if challenge.is_expired:
        return _error(status.HTTP_410_GONE, "otp_expired", msg("otp_expired", lang))
    return None


def _record_wrong_code(challenge: OTPRequest, lang: str) -> ApiError:
    challenge.attempt_count += 1
    attempts_left = settings.OTP_MAX_VERIFY_ATTEMPTS - challenge.attempt_count
    if attempts_left <= 0:
        challenge.locked_at = timezone.now()
        challenge.save(update_fields=["attempt_count", "locked_at", "updated_at"])
        return _attempts_exceeded(settings.OTP_LOCKOUT_SECONDS, lang)

    challenge.save(update_fields=["attempt_count", "updated_at"])
    return _error(
        status.HTTP_400_BAD_REQUEST,
        "invalid_otp",
        msg("invalid_otp", lang, attempts=attempts_left_text(attempts_left, lang)),
        errors={"otp": [msg("invalid_otp_field", lang)]},
        data={"attempts_left": attempts_left},
    )


# --- Helpers -----------------------------------------------------------------


def _save_device(user: User, device: dict) -> None:
    fields = {
        "platform": device.get("platform") or "",
        "fcm_token": device.get("fcm_token"),
        "app_version": device.get("app_version") or "",
        "last_seen_at": timezone.now(),
    }
    device_id = device.get("device_id") or ""
    if device_id:
        UserDevice.objects.update_or_create(user=user, device_id=device_id, defaults=fields)
    elif fields["platform"] or fields["fcm_token"] or fields["app_version"]:
        UserDevice.objects.create(user=user, **fields)


def _seconds_until(moment) -> int:
    remaining = (moment - timezone.now()).total_seconds()
    return max(int(remaining + 0.999), 0)


def _error(status_code: int, error_code: str, message: str, errors=None, data=None) -> ApiError:
    return ApiError(status_code, error_code, message, errors=errors, data=data)


def _not_found(lang: str) -> ApiError:
    return _error(status.HTTP_404_NOT_FOUND, "otp_request_not_found", msg("otp_request_not_found", lang))


def _attempts_exceeded(wait: int, lang: str) -> ApiError:
    return _error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "otp_attempts_exceeded",
        msg("otp_attempts_exceeded", lang, wait=format_wait(wait, lang)),
        data={"retry_after": wait},
    )
