"""Seller-side pickup endpoints (contract 8, 9) and disputes (13)."""

from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.exceptions import ApiError
from apps.common.i18n import get_request_language
from apps.common.idempotency import idempotent
from apps.common.pagination import paginate
from apps.common.permissions import IsSeller
from apps.common.responses import success_response
from apps.sellers.models import Address, default_address

from . import availability, pricing, services
from .messages import msg
from .models import ACTIVE_STATUSES, Dispute, Pickup
from .presenters import delivery_options, detail_dict, dispute_dict, sheet_dict, summary_dict
from .selectors import base_queryset, expire_overdue
from .serializers import (
    AcceptSheetSerializer,
    BookSerializer,
    CancelSerializer,
    DisputeCreateSerializer,
    FlagSerializer,
    QuoteSerializer,
    RatingSerializer,
)

SELLER = [IsAuthenticated, IsSeller]


def _address(user, address_id, lang, required: bool) -> Address | None:
    if address_id:
        address = Address.objects.filter(id=address_id, user=user).first()
        if address is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "address_not_found", msg("address_not_found", lang))
        return address
    address = default_address(user)
    if address is None and required:
        raise ApiError(status.HTTP_404_NOT_FOUND, "address_not_found", msg("address_required", lang))
    return address


def _distance(address: Address | None, option: str):
    """km from the address to the nearest center; only the truck fee uses it."""
    if address is None or option != Pickup.DeliveryOption.TRUCK_HELPER:
        return None
    from apps.dropoff.services import nearest_center

    center = nearest_center(address.lat, address.lng)
    return center["distance_km"] if center else None


def _seller_pickup(request, pk, lang) -> Pickup:
    expire_overdue(seller=request.user, id=pk)
    pickup = base_queryset().prefetch_related("items__material").filter(id=pk, seller=request.user).first()
    if pickup is None:
        raise services.not_found(lang)
    return pickup


class AvailabilityView(APIView):
    """GET /pickups/availability/?address_id= (contract 8.2)."""

    permission_classes = SELLER

    @extend_schema(
        tags=["Pickups"],
        summary="Available days, slots and delivery options",
        parameters=[OpenApiParameter("address_id", str, required=False)],
        responses={200: None},
    )
    def get(self, request):
        from apps.dropoff.services import nearest_center

        lang = get_request_language(request)
        address_id = request.query_params.get("address_id") or None
        if address_id:
            try:
                serializers.UUIDField().to_internal_value(address_id)
            except serializers.ValidationError:
                raise serializers.ValidationError({"address_id": ["Must be a valid UUID."]}) from None
        address = _address(request.user, address_id, lang, required=False)
        return success_response(
            msg("availability", lang),
            {
                "days": availability.days(lang),
                "delivery_options": delivery_options(lang),
                "default_delivery_option": Pickup.DeliveryOption.COLLECTOR_PICKUP,
                "nearest_center": nearest_center(address.lat, address.lng) if address else None,
            },
        )


class QuoteView(APIView):
    """POST /pickups/quote/ (contract 8.3). Stateless."""

    permission_classes = SELLER

    @extend_schema(tags=["Pickups"], summary="Quote a draft", request=QuoteSerializer, responses={200: None})
    def post(self, request):
        lang = get_request_language(request)
        serializer = QuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        option = data["delivery_option"]
        address = (
            _address(request.user, data.get("address_id"), lang, required=False)
            if option == Pickup.DeliveryOption.TRUCK_HELPER
            else None
        )
        lines = pricing.price_items(data["items"], lang)
        return success_response(msg("quote", lang), pricing.quote(lines, option, _distance(address, option), lang))


class PickupListCreateView(APIView):
    """GET /pickups/?status=active|past (8.5) and POST /pickups/ (8.4)."""

    permission_classes = SELLER

    @extend_schema(
        tags=["Pickups"],
        summary="My pickups",
        operation_id="pickups_list",
        parameters=[
            OpenApiParameter("status", str, enum=["active", "past"], required=False),
            OpenApiParameter("page", int, required=False),
            OpenApiParameter("page_size", int, required=False),
        ],
        responses={200: None},
    )
    def get(self, request):
        lang = get_request_language(request)
        which = request.query_params.get("status") or "active"
        if which not in ("active", "past"):
            raise serializers.ValidationError({"status": ["Must be active or past."]})
        expire_overdue(seller=request.user)

        queryset = base_queryset().filter(seller=request.user).annotate(item_count=Count("items"))
        if which == "active":
            queryset = queryset.filter(status__in=ACTIVE_STATUSES).order_by("scheduled_date", "slot_start")
        else:
            queryset = queryset.exclude(status__in=ACTIVE_STATUSES).order_by("-created_at")

        def row(pickup):
            data = summary_dict(pickup, lang, request)
            data["total_amount"] = pickup.final_total
            return data

        return success_response(msg("pickups", lang), paginate(request, queryset, row))

    @extend_schema(tags=["Pickups"], summary="Book a pickup", request=BookSerializer, responses={201: None})
    @idempotent
    def post(self, request):
        lang = get_request_language(request)
        serializer = BookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        option = data["delivery_option"]

        address = _address(request.user, data["address_id"], lang, required=True)
        slot = None
        if option != Pickup.DeliveryOption.SELF_DROPOFF:
            if not data.get("slot_id"):
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "validation_error",
                    msg("slot_required", lang),
                    errors={"slot_id": [msg("slot_required", lang)]},
                )
            slot = availability.parse_slot(data["slot_id"])
            if slot is None:
                raise services.conflict("slot_unavailable", lang)

        lines = pricing.price_items(data["items"], lang)
        pickup = services.book(
            request.user,
            address=address,
            option=option,
            slot=slot,
            lines=lines,
            note=data.get("note", "").strip(),
            distance=_distance(address, option),
            lang=lang,
        )
        pickup = base_queryset().prefetch_related("items__material").get(id=pickup.id)
        return success_response(
            msg("booked", lang, ref=pickup.ref), detail_dict(pickup, lang, request), status=status.HTTP_201_CREATED
        )


class PickupDetailView(APIView):
    """GET /pickups/{id}/ (contract 8.6), polled every poll_after seconds."""

    permission_classes = SELLER

    @extend_schema(tags=["Pickups"], summary="Pickup detail and live tracking", responses={200: None})
    def get(self, request, pk):
        lang = get_request_language(request)
        pickup = _seller_pickup(request, pk, lang)
        return success_response(msg("pickup", lang), detail_dict(pickup, lang, request))


class CancelPickupView(APIView):
    """POST /pickups/{id}/cancel/ (contract 8.7)."""

    permission_classes = SELLER

    @extend_schema(tags=["Pickups"], summary="Cancel a pickup", request=CancelSerializer, responses={200: None})
    def post(self, request, pk):
        lang = get_request_language(request)
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel(
            request.user, pk, serializer.validated_data["reason"], serializer.validated_data["note"].strip(), lang
        )
        pickup = _seller_pickup(request, pk, lang)
        return success_response(msg("cancelled_ok", lang), detail_dict(pickup, lang, request))


class RatePickupView(APIView):
    """POST /pickups/{id}/rating/ (contract 8.8). Seller or collector."""

    @extend_schema(tags=["Pickups"], summary="Rate the other side", request=RatingSerializer, responses={201: None})
    def post(self, request, pk):
        lang = get_request_language(request)
        serializer = RatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rating = services.rate(
            request.user, pk, serializer.validated_data["stars"], serializer.validated_data["comment"].strip(), lang
        )
        return success_response(
            msg("rated", lang),
            {"stars": rating.stars, "comment": rating.comment or None},
            status=status.HTTP_201_CREATED,
        )


class WeighSheetView(APIView):
    """GET /pickups/{id}/weigh-sheet/ (contract 9.1), polled while live."""

    permission_classes = SELLER

    @extend_schema(tags=["Weigh-in"], summary="Live weighing sheet", responses={200: None})
    def get(self, request, pk):
        lang = get_request_language(request)
        pickup, sheet = services.seller_sheet(request.user, pk, lang)
        pickup = base_queryset().get(id=pickup.id)
        return success_response(msg("weigh_sheet", lang), sheet_dict(pickup, sheet, lang))


class FlagLineView(APIView):
    """POST /pickups/{id}/weigh-sheet/flags/ (contract 9.2)."""

    permission_classes = SELLER

    @extend_schema(tags=["Weigh-in"], summary="Flag a line", request=FlagSerializer, responses={201: None})
    def post(self, request, pk):
        lang = get_request_language(request)
        serializer = FlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = {k: v.strip() if isinstance(v, str) else v for k, v in serializer.validated_data.items()}
        flag, dispute = services.flag_line(request.user, pk, data, lang)
        from apps.common.formatting import iso

        return success_response(
            msg("flagged", lang),
            {
                "flag": {
                    "id": str(flag.id),
                    "line_id": flag.line_id,
                    "reason": flag.reason,
                    "status": flag.status,
                    "created_at": iso(flag.created_at),
                },
                "dispute_id": str(dispute.id),
            },
            status=status.HTTP_201_CREATED,
        )


class AcceptSheetView(APIView):
    """POST /pickups/{id}/weigh-sheet/accept/ (contract 9.3). Idempotent."""

    permission_classes = SELLER

    @extend_schema(
        tags=["Weigh-in"], summary="Accept and get paid", request=AcceptSheetSerializer, responses={200: None}
    )
    @idempotent
    def post(self, request, pk):
        lang = get_request_language(request)
        serializer = AcceptSheetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.accept_sheet(
            request.user,
            pk,
            serializer.validated_data["sheet_version"],
            serializer.validated_data["payout_method"],
            lang,
        )
        settlement = result["settlement"]
        if settlement["status"] == Pickup.Settlement.HELD:
            message = msg("held", lang)
        elif settlement["payout_method"] == "cash":
            message = msg("paid_cash", lang, amount=settlement["amount"])
        else:
            message = msg("paid", lang, amount=settlement["amount"])
        return success_response(message, result)


class DisputeListCreateView(APIView):
    """GET/POST /disputes/ (contract 13.1). Any role, paginated."""

    @extend_schema(
        tags=["Disputes"],
        summary="My disputes",
        parameters=[OpenApiParameter("page", int, required=False), OpenApiParameter("page_size", int, required=False)],
        responses={200: None},
    )
    def get(self, request):
        lang = get_request_language(request)
        user = request.user
        queryset = (
            Dispute.objects.filter(Q(pickup__seller=user) | Q(pickup__collector=user) | Q(opened_by=user))
            .select_related("pickup")
            .distinct()
            .order_by("-created_at")
        )
        return success_response(msg("disputes", lang), paginate(request, queryset, lambda d: dispute_dict(d, lang)))

    @extend_schema(
        tags=["Disputes"], summary="Report a problem", request=DisputeCreateSerializer, responses={201: None}
    )
    def post(self, request):
        lang = get_request_language(request)
        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dispute = services.open_dispute(request.user, data["pickup_id"], data["type"], data["note"].strip(), lang)
        dispute = Dispute.objects.select_related("pickup").get(id=dispute.id)
        return success_response(
            msg("dispute_opened", lang), dispute_dict(dispute, lang), status=status.HTTP_201_CREATED
        )
