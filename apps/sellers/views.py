from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.exceptions import ApiError
from apps.common.geo import in_service_area
from apps.common.i18n import get_request_language, translate
from apps.common.permissions import IsSeller
from apps.common.responses import success_response

from .models import Address, default_address
from .serializers import AddressSerializer

MESSAGES = {
    "addresses": {"en": "Addresses", "ne": "ठेगानाहरू"},
    "address_saved": {"en": "Address saved", "ne": "ठेगाना सुरक्षित भयो"},
    "address_deleted": {"en": "Address removed", "ne": "ठेगाना हटाइयो"},
    "address_not_found": {"en": "This address was not found.", "ne": "यो ठेगाना भेटिएन।"},
    "outside_service_area": {
        "en": "We don't pick up from there yet. Choose a spot inside Kathmandu valley.",
        "ne": "हामी त्यहाँबाट अहिले पिकअप गर्दैनौं। काठमाडौं उपत्यकाभित्रको ठाउँ छान्नुहोस्।",
    },
    "address_in_use": {
        "en": "This address has an active pickup. Remove it after the pickup is done.",
        "ne": "यो ठेगानामा सक्रिय पिकअप छ। पिकअप सकिएपछि हटाउनुहोस्।",
    },
    "dashboard": {"en": "Home", "ne": "गृह"},
}


def msg(key, lang, **kwargs):
    return translate(MESSAGES, key, lang, **kwargs)


def _check_service_area(data, lang):
    if "lat" in data and "lng" in data and not in_service_area(data["lat"], data["lng"]):
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "outside_service_area",
            msg("outside_service_area", lang),
            errors={"lat": [msg("outside_service_area", lang)]},
        )


def _get_address(request, pk, lang) -> Address:
    address = Address.objects.filter(id=pk, user=request.user).first()
    if address is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", msg("address_not_found", lang))
    return address


def _save(address: Address, data: dict, *, first: bool) -> Address:
    with transaction.atomic():
        for field, value in data.items():
            setattr(address, field, value)
        if first:
            address.is_default = True
        if address.is_default:
            Address.objects.filter(user=address.user, is_default=True).exclude(id=address.id).update(is_default=False)
        address.save()
        if not Address.objects.filter(user=address.user, is_default=True).exists():
            # Unsetting the only default: keep one default at all times.
            address.is_default = True
            address.save(update_fields=["is_default", "updated_at"])
    return address


class AddressListView(APIView):
    """GET/POST /me/addresses/ (contract 7). Seller only."""

    permission_classes = [IsAuthenticated, IsSeller]

    @extend_schema(tags=["Addresses"], summary="My pickup addresses", responses={200: None})
    def get(self, request):
        lang = get_request_language(request)
        items = [a.as_dict() for a in Address.objects.filter(user=request.user)]
        return success_response(msg("addresses", lang), {"items": items})

    @extend_schema(tags=["Addresses"], summary="Add an address", request=AddressSerializer, responses={201: None})
    def post(self, request):
        lang = get_request_language(request)
        serializer = AddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _check_service_area(serializer.validated_data, lang)
        first = not Address.objects.filter(user=request.user).exists()
        address = _save(Address(user=request.user), serializer.validated_data, first=first)
        return success_response(msg("address_saved", lang), address.as_dict(), status=status.HTTP_201_CREATED)


class AddressDetailView(APIView):
    """PATCH/DELETE /me/addresses/{id}/ (contract 7). Seller only."""

    permission_classes = [IsAuthenticated, IsSeller]

    @extend_schema(tags=["Addresses"], summary="Edit an address", request=AddressSerializer, responses={200: None})
    def patch(self, request, pk):
        lang = get_request_language(request)
        address = _get_address(request, pk, lang)
        serializer = AddressSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "lat" in data or "lng" in data:
            _check_service_area({"lat": data.get("lat", address.lat), "lng": data.get("lng", address.lng)}, lang)
        address = _save(address, data, first=False)
        return success_response(msg("address_saved", lang), address.as_dict())

    @extend_schema(tags=["Addresses"], summary="Remove an address", responses={200: None})
    def delete(self, request, pk):
        from apps.pickups.selectors import address_has_active_pickup

        lang = get_request_language(request)
        address = _get_address(request, pk, lang)
        if address_has_active_pickup(address):
            raise ApiError(status.HTTP_409_CONFLICT, "address_in_use", msg("address_in_use", lang))
        with transaction.atomic():
            was_default = address.is_default
            address.delete()
            if was_default:
                replacement = Address.objects.filter(user=request.user).order_by("created_at").first()
                if replacement:
                    replacement.is_default = True
                    replacement.save(update_fields=["is_default", "updated_at"])
        return success_response(msg("address_deleted", lang), None)


class SellerDashboardView(APIView):
    """GET /seller/dashboard/?lat=&lng= (contract 5.1). One call fills Home."""

    permission_classes = [IsAuthenticated, IsSeller]

    @extend_schema(
        tags=["Seller dashboard"],
        summary="Seller home",
        parameters=[
            OpenApiParameter("lat", float, required=False),
            OpenApiParameter("lng", float, required=False),
        ],
        responses={200: None},
    )
    def get(self, request):
        from apps.accounts.presenters import avatar_url
        from apps.dropoff.services import nearby_summary
        from apps.materials import services as rates
        from apps.pickups.selectors import next_pickup
        from apps.wallet.services import wallet_card

        lang = get_request_language(request)
        user = request.user
        lat, lng = _point_from_query(request)
        if lat is None:
            address = default_address(user)
            if address is not None:
                lat, lng = address.lat, address.lng

        rows = rates.board()
        return success_response(
            msg("dashboard", lang),
            {
                "user": {
                    "id": str(user.id),
                    "first_name": user.display_first_name,
                    "initials": user.initials,
                    "avatar_url": avatar_url(user, request),
                    "role": user.role,
                },
                "wallet": wallet_card(user),
                "rates": {
                    "updated_at": rates.updated_at(rows),
                    "total_count": len(rows),
                    "top": [rates.rate_dict(r, lang) for r in rows[:5]],
                },
                "next_pickup": next_pickup(user, lang, request),
                "dropoff": nearby_summary(lat, lng) if lat is not None else None,
            },
        )


def _point_from_query(request):
    lat, lng = request.query_params.get("lat"), request.query_params.get("lng")
    if lat in (None, "") and lng in (None, ""):
        return None, None
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        raise serializers.ValidationError({"lat": ["lat and lng must both be numbers."]}) from None
    if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
        raise serializers.ValidationError({"lat": ["lat/lng out of range."]})
    return lat_f, lng_f
