"""`Idempotency-Key` support (contract 1.1) for POSTs that create money or
bookings: Book pickup, Accept & get paid, Withdraw, Accept job.

The key row is inserted in the same transaction as the view's work. A
concurrent duplicate blocks on the unique index until the first commits, then
fails with IntegrityError and replays the stored response. Failed requests
(4xx raised as ApiError) roll back with the key, so the client may retry.
"""

from functools import wraps

from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.response import Response

from .models import IdempotencyKey

HEADER = "Idempotency-Key"


def idempotent(view_method):
    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        key = (request.headers.get(HEADER) or "").strip()
        if not key:
            return view_method(self, request, *args, **kwargs)
        if len(key) > 64:
            raise serializers.ValidationError({HEADER: ["At most 64 characters."]})

        scope = f"{request.method} {request.path}"
        lookup = {"user": request.user, "key": key, "scope": scope}

        stored = IdempotencyKey.objects.filter(**lookup).first()
        if stored is not None:
            return Response(stored.response, status=stored.status_code)

        try:
            with transaction.atomic():
                record = IdempotencyKey.objects.create(**lookup, status_code=0, response={})
                response = view_method(self, request, *args, **kwargs)
                if 200 <= response.status_code < 300:
                    record.status_code = response.status_code
                    record.response = response.data
                    record.save(update_fields=["status_code", "response"])
                else:
                    transaction.set_rollback(True)
                return response
        except IntegrityError:
            stored = IdempotencyKey.objects.filter(**lookup).first()
            if stored is None:
                raise
            return Response(stored.response, status=stored.status_code)

    return wrapper
