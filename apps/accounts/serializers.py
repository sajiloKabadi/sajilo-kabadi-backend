import re
import uuid

from django.conf import settings
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .messages import msg
from .models import User, UserDevice

PHONE_RE = re.compile(r"^9[0-9]{9}$")
OTP_ROLES = [User.Role.SELLER, User.Role.COLLECTOR]
FAMILY_CLAIM = "fam"


class PhoneField(serializers.CharField):
    """10 digits, starts with 9. Any failure (including missing) carries the
    `invalid_phone` code, which the exception handler surfaces as the
    response's error_code."""

    def run_validation(self, data=serializers.empty):
        lang = self.context.get("lang", "en")
        try:
            value = super().run_validation(data)
        except serializers.ValidationError:
            raise serializers.ValidationError(msg("invalid_phone", lang), code="invalid_phone") from None
        if not PHONE_RE.match(value):
            raise serializers.ValidationError(msg("invalid_phone", lang), code="invalid_phone")
        return value


class RequestOTPSerializer(serializers.Serializer):
    country_code = serializers.ChoiceField(choices=["+977"])
    phone = PhoneField()
    role = serializers.ChoiceField(choices=OTP_ROLES)
    language = serializers.ChoiceField(choices=User.Language.values, required=False, allow_null=True)


class ResendOTPSerializer(serializers.Serializer):
    otp_request_id = serializers.UUIDField()


class DeviceSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(
        choices=UserDevice.Platform.values, required=False, allow_null=True, allow_blank=True
    )
    device_id = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    fcm_token = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    app_version = serializers.CharField(max_length=32, required=False, allow_null=True, allow_blank=True)


class VerifyOTPSerializer(serializers.Serializer):
    otp_request_id = serializers.UUIDField()
    phone = PhoneField()
    otp = serializers.CharField(max_length=8)
    role = serializers.ChoiceField(choices=OTP_ROLES)
    device = DeviceSerializer(required=False, allow_null=True)

    def validate_otp(self, value):
        if not (value.isascii() and value.isdigit()) or len(value) != settings.OTP_LENGTH:
            raise serializers.ValidationError(f"Enter the {settings.OTP_LENGTH}-digit code.")
        return value


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ProfileUpdateSerializer(serializers.Serializer):
    """PATCH /me/ (contract 4.2). Only sent fields change."""

    first_name = serializers.CharField(required=False, max_length=64)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=80)
    language = serializers.ChoiceField(choices=User.Language.values, required=False)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)

    def validate_first_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("At least 2 characters")
        if len(value) > 24:
            raise serializers.ValidationError("At most 24 characters")
        return value

    def validate_full_name(self, value):
        return " ".join(value.split())

    def validate_email(self, value):
        return value or None


class RegisterDeviceSerializer(serializers.Serializer):
    """PUT /me/device/ (contract 4.4)."""

    device_id = serializers.CharField(max_length=255)
    platform = serializers.ChoiceField(choices=UserDevice.Platform.values)
    fcm_token = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    app_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class LogoutSerializer(serializers.Serializer):
    """POST /auth/logout/ (contract 3.5)."""

    refresh = serializers.CharField(required=False, allow_blank=True)
    device_id = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)


class AvatarUploadSerializer(serializers.Serializer):
    file = serializers.ImageField()


def tokens_for_user(user) -> dict:
    """Mint a new sign-in session. Every refresh token rotated from this one
    keeps the same `fam` claim (see RevokedTokenFamily)."""
    refresh = RefreshToken.for_user(user)
    refresh[FAMILY_CLAIM] = uuid.uuid4().hex
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "token_type": "Bearer",
        "access_expires_in": access_lifetime_seconds(),
        "refresh_expires_in": refresh_lifetime_seconds(),
    }


def access_lifetime_seconds() -> int:
    return int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())


def refresh_lifetime_seconds() -> int:
    return int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
