"""Collector endpoints (contract 12)."""

import datetime as dt

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.exceptions import ApiError
from apps.common.geo import bounding_box, distance_km
from apps.common.i18n import get_request_language
from apps.common.idempotency import idempotent
from apps.common.permissions import IsCollector
from apps.common.responses import success_response
from apps.pickups import services as pickups
from apps.pickups.messages import msg
from apps.pickups.models import COLLECTOR_WORKING_STATUSES, Pickup, PickupDecline, WeighSheet
from apps.pickups.presenters import job_detail_dict, job_dict, ratings_for, sheet_dict, when_label
from apps.pickups.selectors import completed_today, expire_overdue
from apps.pickups.serializers import (
    CollectorStatusSerializer,
    DeclineSerializer,
    JobStatusSerializer,
    LocationSerializer,
    WeighSheetSerializer,
)

from .models import CollectorProfile, profile_for
from .services import record_location

COLLECTOR = [IsAuthenticated, IsCollector]


def _origin(request, profile):
    lat, lng = request.query_params.get("lat"), request.query_params.get("lng")
    if lat not in (None, "") or lng not in (None, ""):
        try:
            return float(lat), float(lng)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"lat": ["lat and lng must both be numbers."]}) from None
    if profile.has_location:
        return float(profile.last_lat), float(profile.last_lng)
    return None, None


def _open_jobs(collector, profile, origin) -> list:
    """Requested jobs within JOB_RADIUS_KM, not declined, soonest slot first."""
    if not profile.effectively_online or origin[0] is None:
        return []
    expire_overdue(**bounding_box(origin[0], origin[1], settings.JOB_RADIUS_KM))
    declined = PickupDecline.objects.filter(collector=collector).values("pickup_id")
    candidates = (
        Pickup.objects.filter(
            status=Pickup.Status.REQUESTED,
            collector__isnull=True,
            slot_end__gt=timezone.now(),
            delivery_option__in=[Pickup.DeliveryOption.COLLECTOR_PICKUP, Pickup.DeliveryOption.TRUCK_HELPER],
            **bounding_box(origin[0], origin[1], settings.JOB_RADIUS_KM),
        )
        .exclude(id__in=declined)
        .select_related("seller")
        .prefetch_related("items__material")
        .order_by("slot_start")
    )
    return [p for p in candidates if distance_km(origin[0], origin[1], p.lat, p.lng) <= settings.JOB_RADIUS_KM]


def _collector_pickup(collector, pk, lang, *, allow_open=False) -> Pickup:
    queryset = Pickup.objects.select_related("seller", "collector").prefetch_related("items__material")
    pickup = queryset.filter(id=pk).first()
    if pickup is None:
        raise pickups.not_found(lang)
    mine = pickup.collector_id == collector.id
    open_job = (
        allow_open
        and pickup.status == Pickup.Status.REQUESTED
        and pickup.collector_id is None
        and pickup.delivery_option != Pickup.DeliveryOption.SELF_DROPOFF
    )
    if not (mine or open_job):
        raise pickups.not_found(lang)  # 404, not 403, so ids can't be probed
    return pickup


class CollectorDashboardView(APIView):
    """GET /collector/dashboard/ (contract 12.1)."""

    permission_classes = COLLECTOR

    @extend_schema(tags=["Collector"], summary="Collector home", responses={200: None})
    def get(self, request):
        from apps.wallet.models import WalletTransaction
        from apps.wallet.services import get_wallet

        lang = get_request_language(request)
        user = request.user
        profile = profile_for(user)
        _sync_online(profile)

        start = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time.min))
        earned_today = (
            WalletTransaction.objects.filter(
                wallet=get_wallet(user),
                type=WalletTransaction.Type.JOB_EARNING,
                status=WalletTransaction.Status.COMPLETED,
                created_at__gte=start,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        active = (
            Pickup.objects.filter(collector=user, status__in=(*COLLECTOR_WORKING_STATUSES, Pickup.Status.DISPUTED))
            .exclude(status=Pickup.Status.DISPUTED, weigh_sheet__status=WeighSheet.Status.ACCEPTED)
            .exclude(status=Pickup.Status.DISPUTED, weigh_sheet__status=WeighSheet.Status.DISPUTED)
            .select_related("seller")
            .order_by("matched_at")
            .first()
        )
        return success_response(
            msg("dashboard", lang),
            {
                "user": {
                    "id": str(user.id),
                    "first_name": user.display_first_name,
                    "full_name": user.full_name.strip() or None,
                    "initials": user.initials,
                    "role": user.role,
                },
                "is_online": profile.effectively_online,
                "is_verified": profile.is_verified,
                "earned_today": earned_today,
                "jobs_done_today": completed_today(user),
                "open_jobs_count": len(_open_jobs(user, profile, _origin(request, profile))),
                "active_job": (
                    {
                        "pickup_id": str(active.id),
                        "ref": active.ref,
                        "status": active.status,
                        "seller_first_name": active.seller.display_first_name,
                        "area": active.area,
                        "when_label": when_label(active, lang),
                    }
                    if active
                    else None
                ),
            },
        )


def _sync_online(profile: CollectorProfile) -> None:
    """No ping for 10 minutes: the server sets the collector offline (12.2)."""
    if profile.is_online and not profile.effectively_online:
        profile.is_online = False
        profile.save(update_fields=["is_online", "updated_at"])


class CollectorStatusView(APIView):
    """PUT /collector/status/ (contract 12.2)."""

    permission_classes = COLLECTOR

    @extend_schema(
        tags=["Collector"], summary="Go online / offline", request=CollectorStatusSerializer, responses={200: None}
    )
    def put(self, request):
        lang = get_request_language(request)
        serializer = CollectorStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        profile = profile_for(request.user)

        if data["is_online"]:
            if not profile.is_verified:
                raise ApiError(status.HTTP_403_FORBIDDEN, "collector_not_verified", msg("collector_not_verified", lang))
            if data.get("lat") is None or data.get("lng") is None:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "location_required",
                    msg("location_required", lang),
                    errors={"lat": [msg("location_required", lang)]},
                )
            profile = record_location(request.user, data["lat"], data["lng"])
        profile.is_online = data["is_online"]
        profile.save(update_fields=["is_online", "updated_at"])
        return success_response(
            msg("online" if profile.is_online else "offline", lang), {"is_online": profile.is_online}
        )


class JobListView(APIView):
    """GET /collector/jobs/?lat=&lng= (contract 12.3)."""

    permission_classes = COLLECTOR

    @extend_schema(
        tags=["Collector"],
        summary="Open jobs near me",
        operation_id="collector_jobs_list",
        parameters=[OpenApiParameter("lat", float, required=False), OpenApiParameter("lng", float, required=False)],
        responses={200: None},
    )
    def get(self, request):
        lang = get_request_language(request)
        profile = profile_for(request.user)
        _sync_online(profile)
        origin = _origin(request, profile)
        jobs = _open_jobs(request.user, profile, origin)
        ratings = ratings_for([job.seller_id for job in jobs])
        return success_response(msg("jobs", lang), {"items": [job_dict(job, lang, origin, ratings) for job in jobs]})


class JobDetailView(APIView):
    """GET /collector/jobs/{id}/ (contract 12.4)."""

    permission_classes = COLLECTOR

    @extend_schema(tags=["Collector"], summary="Job detail", responses={200: None})
    def get(self, request, pk):
        lang = get_request_language(request)
        profile = profile_for(request.user)
        pickup = _collector_pickup(request.user, pk, lang, allow_open=True)
        return success_response(
            msg("job", lang), job_detail_dict(pickup, lang, request.user, _origin(request, profile))
        )


class AcceptJobView(APIView):
    """POST /collector/jobs/{id}/accept/ (contract 12.5). Idempotent."""

    permission_classes = COLLECTOR

    @extend_schema(tags=["Collector"], summary="Accept a job", request=None, responses={200: None})
    @idempotent
    def post(self, request, pk):
        lang = get_request_language(request)
        profile = profile_for(request.user)
        _sync_online(profile)
        pickups.accept_job(request.user, profile, pk, lang)
        pickup = _collector_pickup(request.user, pk, lang)
        return success_response(
            msg("job_accepted", lang), job_detail_dict(pickup, lang, request.user, _origin(request, profile))
        )


class DeclineJobView(APIView):
    """POST /collector/jobs/{id}/decline/ (contract 12.6)."""

    permission_classes = COLLECTOR

    @extend_schema(tags=["Collector"], summary="Decline a job", request=DeclineSerializer, responses={200: None})
    def post(self, request, pk):
        lang = get_request_language(request)
        serializer = DeclineSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        pickups.decline_job(request.user, pk, serializer.validated_data.get("reason", ""), lang)
        return success_response(msg("job_declined", lang), None)


class JobStatusView(APIView):
    """POST /collector/pickups/{id}/status/ (contract 12.7)."""

    permission_classes = COLLECTOR

    @extend_schema(tags=["Collector"], summary="Update job status", request=JobStatusSerializer, responses={200: None})
    def post(self, request, pk):
        lang = get_request_language(request)
        serializer = JobStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("lat") is not None and data.get("lng") is not None:
            record_location(request.user, data["lat"], data["lng"])
        pickups.advance(request.user, pk, data["status"], lang)
        profile = profile_for(request.user)
        pickup = _collector_pickup(request.user, pk, lang)
        return success_response(
            msg("status_updated", lang), job_detail_dict(pickup, lang, request.user, _origin(request, profile))
        )


class LocationView(APIView):
    """POST /collector/location/ (contract 12.8). Response data: null."""

    permission_classes = COLLECTOR

    @extend_schema(tags=["Collector"], summary="Location ping", request=LocationSerializer, responses={200: None})
    def post(self, request):
        lang = get_request_language(request)
        serializer = LocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        recorded_at = data.get("recorded_at")
        if recorded_at and recorded_at > timezone.now() + dt.timedelta(minutes=5):
            recorded_at = None  # clock skew: trust the server
        record_location(
            request.user, data["lat"], data["lng"], data.get("heading"), data.get("accuracy_m"), recorded_at
        )
        return success_response(msg("location_saved", lang), None)


class CollectorWeighSheetView(APIView):
    """PUT /collector/pickups/{id}/weigh-sheet/ (contract 12.9)."""

    permission_classes = COLLECTOR

    @extend_schema(tags=["Collector"], summary="Enter weights", request=WeighSheetSerializer, responses={200: None})
    def put(self, request, pk):
        lang = get_request_language(request)
        serializer = WeighSheetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pickup, sheet = pickups.save_sheet(request.user, pk, serializer.validated_data["lines"], lang)
        pickup = Pickup.objects.select_related("collector").get(id=pickup.id)
        return success_response(msg("weights_saved", lang), sheet_dict(pickup, sheet, lang))


class SubmitWeighSheetView(APIView):
    """POST /collector/pickups/{id}/weigh-sheet/submit/ (contract 12.10)."""

    permission_classes = COLLECTOR

    @extend_schema(tags=["Collector"], summary="Submit weights", request=None, responses={200: None})
    def post(self, request, pk):
        lang = get_request_language(request)
        pickup, sheet = pickups.submit_sheet(request.user, pk, lang)
        pickup = Pickup.objects.select_related("collector").get(id=pickup.id)
        return success_response(msg("weights_submitted", lang), sheet_dict(pickup, sheet, lang))
