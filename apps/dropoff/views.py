from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.views import APIView

from apps.common.i18n import get_request_language, translate
from apps.common.responses import success_response

from .services import center_dict, centers_near

MESSAGES = {"centers": {"en": "Drop-off centers", "ne": "ड्रप-अफ केन्द्रहरू"}}


class CentersQuerySerializer(serializers.Serializer):
    lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, min_value=-180, max_value=180)
    radius_km = serializers.FloatField(required=False, min_value=0.1)

    def validate(self, attrs):
        if ("lat" in attrs) != ("lng" in attrs):
            raise serializers.ValidationError({"lat": ["Send both lat and lng."]})
        return attrs


class DropoffCenterListView(APIView):
    """GET /dropoff-centers/?lat=&lng=&radius_km= (contract 10.1). Any role.
    Without lat/lng a seller's default address is used."""

    @extend_schema(
        tags=["Drop-off centers"],
        summary="Centers near me",
        parameters=[
            OpenApiParameter("lat", float, required=False),
            OpenApiParameter("lng", float, required=False),
            OpenApiParameter("radius_km", float, required=False, description="Default 2, capped at 20"),
        ],
        responses={200: None},
    )
    def get(self, request):
        lang = get_request_language(request)
        query = CentersQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        radius = min(data.get("radius_km", settings.DROPOFF_DEFAULT_RADIUS_KM), settings.DROPOFF_MAX_RADIUS_KM)

        lat, lng = data.get("lat"), data.get("lng")
        if lat is None:
            from apps.sellers.models import default_address

            address = default_address(request.user)
            if address is None:
                raise serializers.ValidationError({"lat": ["lat and lng are required."]})
            lat, lng = address.lat, address.lng

        now = timezone.localtime().time()
        items = [center_dict(center, km, now) for center, km in centers_near(lat, lng, radius)]
        return success_response(translate(MESSAGES, "centers", lang), {"items": items})
