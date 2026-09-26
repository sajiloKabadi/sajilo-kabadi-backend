from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.views import APIView

from apps.common.i18n import get_request_language
from apps.common.responses import success_response

from . import services
from .messages import city_label, msg
from .models import Material


class RateBoardView(APIView):
    """GET /rates/?category=metal (contract 6.1). Any role."""

    @extend_schema(
        tags=["Rates"],
        summary="Rate board",
        parameters=[OpenApiParameter("category", str, enum=Material.Category.values, required=False)],
        responses={200: None},
    )
    def get(self, request):
        lang = get_request_language(request)
        category = request.query_params.get("category") or None
        if category and category not in Material.Category.values:
            raise serializers.ValidationError({"category": [f"Must be one of {', '.join(Material.Category.values)}."]})

        rows = services.board()
        visible = [r for r in rows if category is None or r.category == category]
        city = settings.DEFAULT_CITY
        return success_response(
            msg("rates", lang),
            {
                "city": city_label(city, lang),
                "updated_at": services.updated_at(rows),
                "note": msg("rates_note", lang, city=city_label(city, lang)),
                "categories": services.categories(lang),
                "items": [services.rate_dict(r, lang) for r in visible],
            },
        )
