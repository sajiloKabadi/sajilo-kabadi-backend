import re

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .messages import msg
from .models import User, UserDevice

PHONE_RE = re.compile(r"^9[0-9]{9}$")
OTP_ROLES = [User.Role.SELLER, User.Role.COLLECTOR]


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


class UserSerializer(serializers.ModelSerializer):
    """The `user` object from the contract (section 4, response 200)."""

    phone = serializers.CharField(source="phone_number", read_only=True)
    full_name = serializers.SerializerMethodField()
    first_name = serializers.CharField(read_only=True)
    initials = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    is_profile_complete = serializers.BooleanField(read_only=True)
    created_at = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "country_code",
            "full_name",
            "first_name",
            "initials",
            "email",
            "avatar_url",
            "role",
            "language",
            "is_profile_complete",
            "created_at",
        ]
        read_only_fields = fields

    def get_full_name(self, user):
        return user.full_name.strip() or None

    def get_avatar_url(self, user):
        if not user.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(user.avatar.url) if request else user.avatar.url

    def get_created_at(self, user):
        # Local (Asia/Kathmandu) time, whole seconds: "2026-08-01T09:15:00+05:45"
        return timezone.localtime(user.created_at).replace(microsecond=0).isoformat()


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["full_name", "email", "language", "avatar"]


def tokens_for_user(user) -> dict:
    refresh = RefreshToken.for_user(user)
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
