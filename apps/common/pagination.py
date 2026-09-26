"""Pagination in the contract shape (1.3):
{"items": [...], "page": 1, "page_size": 20, "total": 57, "has_next": true}"""

from rest_framework import serializers

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


def _positive_int(request, name: str, default: int) -> int:
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise serializers.ValidationError({name: ["A valid integer is required."]}) from None
    if value < 1:
        raise serializers.ValidationError({name: ["Must be 1 or more."]})
    return value


def paginate(request, queryset, serialize) -> dict:
    """Slice `queryset` for ?page=&page_size= and serialize each row with
    `serialize(obj)`. `serialize` may also take the whole page list when it
    has a `batch` attribute, so callers can prefetch per page."""
    page = _positive_int(request, "page", 1)
    page_size = min(_positive_int(request, "page_size", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
    total = queryset.count()
    offset = (page - 1) * page_size
    rows = list(queryset[offset : offset + page_size]) if offset < total else []
    items = serialize.batch(rows) if hasattr(serialize, "batch") else [serialize(row) for row in rows]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_next": offset + len(rows) < total,
    }
