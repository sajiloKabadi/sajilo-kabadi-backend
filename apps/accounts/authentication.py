from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.settings import api_settings

from apps.common.i18n import get_request_language

from .messages import msg
from .models import User


class ActiveUserJWTAuthentication(JWTAuthentication):
    """JWT auth where a suspended user gets 403 account_blocked (the app signs
    out) instead of simplejwt's generic 401, as contract 1.4 requires."""

    def authenticate(self, request):
        self._lang = get_request_language(request)
        return super().authenticate(request)

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken("Token contained no recognizable user identification") from None

        user = User.objects.filter(id=user_id).first()
        if user is None:
            raise InvalidToken("User not found")
        if not user.is_active:
            # Imported here: DRF loads this class while apps.common.exceptions
            # is itself importing DRF.
            from apps.common.exceptions import ApiError

            lang = getattr(self, "_lang", "en")
            raise ApiError(status.HTTP_403_FORBIDDEN, "account_blocked", msg("account_blocked", lang))
        return user
