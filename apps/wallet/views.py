import datetime as dt

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.common.exceptions import ApiError
from apps.common.formatting import iso
from apps.common.i18n import get_request_language
from apps.common.idempotency import idempotent
from apps.common.pagination import paginate
from apps.common.responses import success_response

from . import services
from .messages import BANKS, msg
from .models import PayoutMethod, WalletTransaction
from .statement import render_statement

STATEMENT_SALT = "wallet.statement"
STATEMENT_TTL_SECONDS = 600


class WalletView(APIView):
    """GET /wallet/ (contract 11.1). Any role."""

    @extend_schema(tags=["Wallet"], summary="Wallet summary", responses={200: None})
    def get(self, request):
        lang = get_request_language(request)
        return success_response(msg("wallet", lang), services.summary(request.user))


class TransactionListView(APIView):
    """GET /wallet/transactions/?page= (contract 11.2). Paginated, newest first."""

    @extend_schema(
        tags=["Wallet"],
        summary="Transaction history",
        parameters=[OpenApiParameter("page", int, required=False), OpenApiParameter("page_size", int, required=False)],
        responses={200: None},
    )
    def get(self, request):
        lang = get_request_language(request)
        wallet = services.get_wallet(request.user)
        queryset = (
            WalletTransaction.objects.filter(wallet=wallet)
            .select_related("pickup", "payout_method")
            .order_by("-created_at")
        )
        return success_response(
            msg("transactions", lang), paginate(request, queryset, lambda t: services.transaction_dict(t, lang))
        )


class PayoutMethodSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=PayoutMethod.Type.values)
    bank_code = serializers.ChoiceField(choices=sorted(BANKS))
    account_name = serializers.CharField(max_length=120)
    account_number = serializers.RegexField(r"^[0-9]{6,20}$", error_messages={"invalid": "6 to 20 digits."})
    is_default = serializers.BooleanField(required=False, default=False)


class PayoutMethodListView(APIView):
    """GET/POST /me/payout-methods/ (contract 11.3). Any role."""

    @extend_schema(tags=["Wallet"], summary="Payout methods", responses={200: None})
    def get(self, request):
        lang = get_request_language(request)
        items = [m.as_dict() for m in PayoutMethod.objects.filter(user=request.user, is_removed=False)]
        return success_response(msg("payout_methods", lang), {"items": items})

    @extend_schema(tags=["Wallet"], summary="Add a bank account", request=PayoutMethodSerializer, responses={201: None})
    def post(self, request):
        lang = get_request_language(request)
        serializer = PayoutMethodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            existing = PayoutMethod.objects.select_for_update().filter(user=request.user, is_removed=False)
            make_default = data["is_default"] or not existing.exists()
            if make_default:
                existing.filter(is_default=True).update(is_default=False)
            method = PayoutMethod.objects.create(
                user=request.user,
                type=data["type"],
                bank_code=data["bank_code"],
                bank_name=BANKS[data["bank_code"]],
                account_name=" ".join(data["account_name"].split()),
                account_number=data["account_number"],
                is_default=make_default,
            )
        return success_response(msg("payout_method_added", lang), method.as_dict(), status=status.HTTP_201_CREATED)


class PayoutMethodDetailView(APIView):
    """DELETE /me/payout-methods/{id}/ (contract 11.3)."""

    @extend_schema(tags=["Wallet"], summary="Remove a bank account", responses={200: None})
    def delete(self, request, pk):
        lang = get_request_language(request)
        with transaction.atomic():
            method = PayoutMethod.objects.select_for_update().filter(id=pk, user=request.user, is_removed=False).first()
            if method is None:
                raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", msg("payout_method_not_found", lang))
            method.is_removed = True
            was_default, method.is_default = method.is_default, False
            method.save(update_fields=["is_removed", "is_default", "updated_at"])
            if was_default:
                replacement = PayoutMethod.objects.filter(user=request.user, is_removed=False).first()
                if replacement:
                    replacement.is_default = True
                    replacement.save(update_fields=["is_default", "updated_at"])
        return success_response(msg("payout_method_removed", lang), None)


class WithdrawSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1)
    payout_method_id = serializers.UUIDField()


class WithdrawView(APIView):
    """POST /wallet/withdrawals/ (contract 11.4). Idempotent."""

    @extend_schema(tags=["Wallet"], summary="Withdraw", request=WithdrawSerializer, responses={201: None})
    @idempotent
    def post(self, request):
        lang = get_request_language(request)
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        if amount < settings.MIN_WITHDRAWAL:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "below_minimum",
                msg("below_minimum", lang, minimum=settings.MIN_WITHDRAWAL),
                errors={"amount": [msg("below_minimum", lang, minimum=settings.MIN_WITHDRAWAL)]},
            )
        method = PayoutMethod.objects.filter(
            id=serializer.validated_data["payout_method_id"], user=request.user, is_removed=False
        ).first()
        if method is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", msg("payout_method_not_found", lang))
        if not method.verified:
            raise ApiError(status.HTTP_409_CONFLICT, "payout_method_unverified", msg("payout_method_unverified", lang))
        if settings.PAYOUTS_ON_HOLD:
            raise ApiError(status.HTTP_409_CONFLICT, "conflict", msg("payouts_on_hold", lang))

        try:
            txn, wallet = services.withdraw(request.user, amount, method)
        except services.InsufficientBalance:
            raise ApiError(
                status.HTTP_409_CONFLICT, "insufficient_balance", msg("insufficient_balance", lang)
            ) from None

        return success_response(
            msg("withdrawal_created", lang),
            {
                "transaction": {
                    "id": str(txn.id),
                    "type": txn.type,
                    "amount": txn.amount,
                    "status": txn.status,
                    "title": services.title(txn, lang),
                },
                "wallet": {"balance": wallet.balance},
            },
            status=status.HTTP_201_CREATED,
        )


class StatementQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(source="from")
    to = serializers.DateField()

    def to_internal_value(self, data):
        # "from" is a Python keyword; accept it as the query name.
        data = {"date_from": data.get("from"), "to": data.get("to")}
        return super().to_internal_value(data)

    def validate(self, attrs):
        start, end = attrs["from"], attrs["to"]
        if start > end:
            raise serializers.ValidationError({"from": ["Must be on or before 'to'."]})
        if (end - start).days > 366:
            raise serializers.ValidationError({"to": ["At most one year per statement."]})
        return attrs


class StatementView(APIView):
    """GET /wallet/statement/?from=&to= (contract 11.5): a signed PDF link
    valid for 10 minutes."""

    @extend_schema(
        tags=["Wallet"],
        summary="Statement link",
        parameters=[OpenApiParameter("from", dt.date, required=True), OpenApiParameter("to", dt.date, required=True)],
        responses={200: None},
    )
    def get(self, request):
        lang = get_request_language(request)
        query = StatementQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        token = signing.dumps(
            {
                "u": str(request.user.id),
                "f": query.validated_data["from"].isoformat(),
                "t": query.validated_data["to"].isoformat(),
                "l": lang,
            },
            salt=STATEMENT_SALT,
        )
        url = request.build_absolute_uri(reverse("wallet:statement-file") + f"?token={token}")
        expires = timezone.now() + dt.timedelta(seconds=STATEMENT_TTL_SECONDS)
        return success_response(msg("statement", lang), {"url": url, "expires_at": iso(expires)})


class StatementFileView(APIView):
    """The PDF behind the signed link. No bearer token: the link is the key."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def get(self, request):
        from apps.accounts.models import User

        lang = get_request_language(request)
        try:
            payload = signing.loads(
                request.query_params.get("token", ""), salt=STATEMENT_SALT, max_age=STATEMENT_TTL_SECONDS
            )
            user = User.objects.get(id=payload["u"], is_active=True)
            start, end = dt.date.fromisoformat(payload["f"]), dt.date.fromisoformat(payload["t"])
        except (signing.BadSignature, User.DoesNotExist, KeyError, ValueError):
            raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", msg("statement_link_invalid", lang)) from None

        pdf = render_statement(user, start, end, payload.get("l", "en"))
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="sajilo-statement-{start}-{end}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
