from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.exceptions import ApiError
from apps.common.i18n import get_request_language
from apps.common.responses import success_response
from apps.common.utils import get_client_ip

from . import otp as otp_service
from .messages import msg
from .models import User
from .serializers import (
    RequestOTPSerializer,
    ResendOTPSerializer,
    TokenRefreshRequestSerializer,
    UserSerializer,
    UserUpdateSerializer,
    VerifyOTPSerializer,
    access_lifetime_seconds,
    refresh_lifetime_seconds,
    tokens_for_user,
)

AUTH_TAG = "Authentication"
ACCOUNT_TAG = "Account"


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
    """POST /auth/otp/request/"""

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
    """POST /auth/otp/resend/"""

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
    """POST /auth/otp/verify/ - the only endpoint that mints tokens."""

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
                "user": UserSerializer(result.user, context={"request": request}).data,
            },
        )


class TokenRefreshView(PublicAuthView):
    """POST /auth/token/refresh/ - rotates the refresh token; the old one is
    blacklisted. Any failure is 401 refresh_invalid, which signs the app out."""

    @extend_schema(
        tags=[AUTH_TAG],
        summary="4. Refresh the access token",
        request=TokenRefreshRequestSerializer,
        responses={200: None},
    )
    def post(self, request):
        lang = get_request_language(request)
        data = self.validated(TokenRefreshRequestSerializer, lang)

        try:
            token = RefreshToken(data["refresh"])
            user_id = token.payload.get(jwt_settings.USER_ID_CLAIM)
            if not User.objects.filter(id=user_id, is_active=True).exists():
                raise TokenError("user inactive or missing")

            serializer = TokenRefreshSerializer(data={"refresh": data["refresh"]})
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken):
            raise ApiError(status.HTTP_401_UNAUTHORIZED, "refresh_invalid", msg("refresh_invalid", lang)) from None

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


class MeView(APIView):
    """GET/PATCH /accounts/me/ - the signed-in user, same shape as on verify."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=[ACCOUNT_TAG], summary="Get the signed-in user", responses={200: None})
    def get(self, request):
        lang = get_request_language(request)
        return success_response(msg("profile", lang), UserSerializer(request.user, context={"request": request}).data)

    @extend_schema(
        tags=[ACCOUNT_TAG], summary="Update the signed-in user", request=UserUpdateSerializer, responses={200: None}
    )
    def patch(self, request):
        lang = get_request_language(request)
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return success_response(msg("profile_updated", lang), UserSerializer(user, context={"request": request}).data)
