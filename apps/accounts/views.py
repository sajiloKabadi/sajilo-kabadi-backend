import contextlib
import io
import uuid

from django.core.files.base import ContentFile
from django.db import transaction
from drf_spectacular.utils import extend_schema
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenBackendError, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.exceptions import ApiError
from apps.common.i18n import get_request_language
from apps.common.responses import success_response
from apps.common.utils import get_client_ip

from . import otp as otp_service
from .messages import msg
from .models import RevokedTokenFamily, User, UserDevice
from .presenters import avatar_url, user_dict
from .profile import me_payload
from .serializers import (
    FAMILY_CLAIM,
    AvatarUploadSerializer,
    LogoutSerializer,
    ProfileUpdateSerializer,
    RegisterDeviceSerializer,
    RequestOTPSerializer,
    ResendOTPSerializer,
    TokenRefreshRequestSerializer,
    VerifyOTPSerializer,
    access_lifetime_seconds,
    refresh_lifetime_seconds,
    tokens_for_user,
)

AUTH_TAG = "Authentication"
ACCOUNT_TAG = "Account"
AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_SIZE = 512


class PublicAuthView(APIView):
    """Base for /auth/* endpoints: no Bearer auth, so a stale access token
    in the header can never turn these into a 401."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def validated(self, serializer_class, lang):
        serializer = serializer_class(data=self.request.data, context={"request": self.request, "lang": lang})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class RequestOTPView(PublicAuthView):
    """POST /auth/otp/request/ (contract 3.1)."""

    @extend_schema(tags=[AUTH_TAG], summary="1. Request an OTP", request=RequestOTPSerializer, responses={200: None})
    def post(self, request):
        lang = get_request_language(request)
        data = self.validated(RequestOTPSerializer, lang)
        payload = otp_service.request_otp(
            phone=data["phone"],
            country_code=data["country_code"],
            role=data["role"],
            language=data.get("language"),
            ip=get_client_ip(request),
            lang=lang,
        )
        return success_response(
            msg("otp_sent", lang, length=payload["otp_length"], phone=payload["phone_masked"]),
            payload,
        )


class ResendOTPView(PublicAuthView):
    """POST /auth/otp/resend/ (contract 3.2)."""

    @extend_schema(tags=[AUTH_TAG], summary="2. Resend the OTP", request=ResendOTPSerializer, responses={200: None})
    def post(self, request):
        lang = get_request_language(request)
        data = self.validated(ResendOTPSerializer, lang)
        payload = otp_service.resend_otp(otp_request_id=data["otp_request_id"], ip=get_client_ip(request), lang=lang)
        return success_response(
            msg("otp_sent", lang, length=payload["otp_length"], phone=payload["phone_masked"]),
            payload,
        )


class VerifyOTPView(PublicAuthView):
    """POST /auth/otp/verify/ (contract 3.3): the only endpoint that mints tokens."""

    @extend_schema(
        tags=[AUTH_TAG], summary="3. Verify the OTP and sign in", request=VerifyOTPSerializer, responses={200: None}
    )
    def post(self, request):
        lang = get_request_language(request)
        data = self.validated(VerifyOTPSerializer, lang)
        result = otp_service.verify_otp(
            otp_request_id=data["otp_request_id"],
            phone=data["phone"],
            otp=data["otp"],
            role=data["role"],
            device=data.get("device"),
            lang=lang,
        )
        return success_response(
            msg("signed_in", lang),
            {
                "tokens": tokens_for_user(result.user),
                "is_new_user": result.is_new_user,
                "user": user_dict(result.user, request),
            },
        )


def _revoke_family_if_reused(raw: str) -> None:
    """A correctly signed refresh token that was already rotated is being
    replayed: revoke every token of that sign-in (contract 14)."""
    try:
        payload = token_backend.decode(raw, verify=True)
    except TokenBackendError:
        return
    family, jti = payload.get(FAMILY_CLAIM), payload.get("jti")
    user_id = payload.get(jwt_settings.USER_ID_CLAIM)
    if family and jti and user_id and BlacklistedToken.objects.filter(token__jti=jti).exists():
        RevokedTokenFamily.objects.get_or_create(family=family, defaults={"user_id": user_id})


class TokenRefreshView(PublicAuthView):
    """POST /auth/token/refresh/ (contract 3.4): rotates both tokens; the old
    refresh token stops working immediately. Any failure is 401 refresh_invalid."""

    @extend_schema(
        tags=[AUTH_TAG],
        summary="4. Refresh the access token",
        request=TokenRefreshRequestSerializer,
        responses={200: None},
    )
    def post(self, request):
        lang = get_request_language(request)
        data = self.validated(TokenRefreshRequestSerializer, lang)
        invalid = ApiError(status.HTTP_401_UNAUTHORIZED, "refresh_invalid", msg("refresh_invalid", lang))

        try:
            token = RefreshToken(data["refresh"])
        except TokenError:
            _revoke_family_if_reused(data["refresh"])
            raise invalid from None

        family = token.payload.get(FAMILY_CLAIM)
        user_id = token.payload.get(jwt_settings.USER_ID_CLAIM)
        if family and RevokedTokenFamily.objects.filter(family=family).exists():
            raise invalid
        if not User.objects.filter(id=user_id, is_active=True).exists():
            raise invalid

        serializer = TokenRefreshSerializer(data={"refresh": data["refresh"]})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken):
            raise invalid from None

        tokens = serializer.validated_data
        return success_response(
            msg("token_refreshed", lang),
            {
                "access": tokens["access"],
                "refresh": tokens.get("refresh", data["refresh"]),
                "access_expires_in": access_lifetime_seconds(),
                "refresh_expires_in": refresh_lifetime_seconds(),
            },
        )


class LogoutView(PublicAuthView):
    """POST /auth/logout/ (contract 3.5): revoke the refresh token (and its
    session), detach the device's push token. Always 200, data null."""

    @extend_schema(tags=[AUTH_TAG], summary="Sign out", request=LogoutSerializer, responses={200: None})
    def post(self, request):
        lang = get_request_language(request)
        data = self.validated(LogoutSerializer, lang)
        raw = data.get("refresh") or ""
        try:
            payload = token_backend.decode(raw, verify=True) if raw else None
        except TokenBackendError:
            payload = None

        if payload:
            user_id = payload.get(jwt_settings.USER_ID_CLAIM)
            with contextlib.suppress(TokenError):
                RefreshToken(raw).blacklist()
            if payload.get(FAMILY_CLAIM) and user_id:
                RevokedTokenFamily.objects.get_or_create(family=payload[FAMILY_CLAIM], defaults={"user_id": user_id})
            if data.get("device_id") and user_id:
                UserDevice.objects.filter(user_id=user_id, device_id=data["device_id"]).update(fcm_token=None)
        return success_response(msg("signed_out", lang), None)


class MeView(APIView):
    """GET/PATCH /me/ (contract 4.1, 4.2)."""

    @extend_schema(tags=[ACCOUNT_TAG], summary="My profile", responses={200: None})
    def get(self, request):
        lang = get_request_language(request)
        return success_response(msg("profile", lang), me_payload(request.user, lang, request))

    @extend_schema(
        tags=[ACCOUNT_TAG], summary="Update my profile", request=ProfileUpdateSerializer, responses={200: None}
    )
    def patch(self, request):
        lang = get_request_language(request)
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        changed = []
        if "full_name" in data:
            user.full_name = data["full_name"]
            changed.append("full_name")
        if "first_name" in data:
            user.first_name = data["first_name"]
            changed.append("first_name")
        elif not user.first_name.strip() and user.full_name.split():
            # "If first_name is empty, the server takes the first word of full_name."
            user.first_name = user.full_name.split()[0][:24]
            changed.append("first_name")
        for field in ("language", "email"):
            if field in data:
                setattr(user, field, data[field])
                changed.append(field)
        if changed:
            user.save(update_fields=[*changed, "updated_at"])
        return success_response(msg("profile_updated", lang), {"user": user_dict(user, request)})


class AvatarView(APIView):
    """POST/DELETE /me/avatar/ (contract 4.3): JPEG/PNG up to 5 MB, re-encoded
    to a 512 px square JPEG with EXIF stripped."""

    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=[ACCOUNT_TAG],
        summary="Upload avatar",
        request={"multipart/form-data": AvatarUploadSerializer},
        responses={200: None},
    )
    def post(self, request):
        lang = get_request_language(request)
        upload = request.FILES.get("file")
        invalid = ApiError(
            status.HTTP_400_BAD_REQUEST,
            "validation_error",
            msg("avatar_invalid", lang),
            errors={"file": [msg("avatar_invalid", lang)]},
        )
        if upload is None or upload.size > AVATAR_MAX_BYTES:
            raise invalid
        try:
            image = Image.open(upload)
            if image.format not in ("JPEG", "PNG"):
                raise invalid
            image = ImageOps.exif_transpose(image).convert("RGB")
        except (UnidentifiedImageError, OSError):
            raise invalid from None

        image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85, optimize=True)  # no exif= -> metadata dropped

        user = request.user
        old = user.avatar.name if user.avatar else None
        with transaction.atomic():
            user.avatar.save(f"{uuid.uuid4().hex}.jpg", ContentFile(buffer.getvalue()), save=False)
            user.save(update_fields=["avatar", "updated_at"])
        if old:
            user.avatar.storage.delete(old)
        return success_response(msg("avatar_updated", lang), {"avatar_url": avatar_url(user, request)})

    @extend_schema(tags=[ACCOUNT_TAG], summary="Remove avatar", responses={200: None})
    def delete(self, request):
        lang = get_request_language(request)
        user = request.user
        if user.avatar:
            name = user.avatar.name
            user.avatar = None
            user.save(update_fields=["avatar", "updated_at"])
            user.avatar.storage.delete(name)
        return success_response(msg("avatar_removed", lang), {"avatar_url": None})


class DeviceView(APIView):
    """PUT /me/device/ (contract 4.4): upsert by device_id."""

    @extend_schema(
        tags=[ACCOUNT_TAG], summary="Register device", request=RegisterDeviceSerializer, responses={200: None}
    )
    def put(self, request):
        from django.utils import timezone

        lang = get_request_language(request)
        serializer = RegisterDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        token = data.get("fcm_token") or None
        with transaction.atomic():
            if token:
                # A push token belongs to one signed-in user at a time.
                UserDevice.objects.filter(fcm_token=token).exclude(
                    user=request.user, device_id=data["device_id"]
                ).update(fcm_token=None)
            device, _ = UserDevice.objects.update_or_create(
                user=request.user,
                device_id=data["device_id"],
                defaults={
                    "platform": data["platform"],
                    "fcm_token": token,
                    "app_version": data.get("app_version", ""),
                    "last_seen_at": timezone.now(),
                },
            )
        return success_response(
            msg("device_registered", lang),
            {"device_id": device.device_id, "platform": device.platform, "app_version": device.app_version or None},
        )
