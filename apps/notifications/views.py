from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.common.i18n import get_request_language, translate
from apps.common.responses import success_response

from .models import NotificationPreference
from .serializers import NotificationSettingsSerializer

MESSAGES = {
    "settings": {"en": "Notification settings", "ne": "सूचना सेटिङ"},
    "settings_updated": {"en": "Notification settings updated", "ne": "सूचना सेटिङ अद्यावधिक भयो"},
}


class NotificationSettingsView(APIView):
    """GET/PATCH /me/notification-settings/ (contract 4.5). Any role."""

    @extend_schema(tags=["Account"], summary="Notification settings", responses={200: None})
    def get(self, request):
        lang = get_request_language(request)
        pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return success_response(translate(MESSAGES, "settings", lang), pref.as_dict())

    @extend_schema(
        tags=["Account"],
        summary="Update notification settings",
        request=NotificationSettingsSerializer,
        responses={200: None},
    )
    def patch(self, request):
        lang = get_request_language(request)
        serializer = NotificationSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        pref, _ = NotificationPreference.objects.get_or_create(user=request.user)
        for field in ("pickup_updates", "promotions"):
            if field in data:
                setattr(pref, field, data[field])
        alerts = data.get("rate_alerts") or {}
        if "enabled" in alerts:
            pref.rate_alerts_enabled = alerts["enabled"]
        if "material_ids" in alerts:
            pref.rate_alert_material_ids = alerts["material_ids"]
        pref.save()
        return success_response(translate(MESSAGES, "settings_updated", lang), pref.as_dict())
