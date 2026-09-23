"""Django-level 404/500 handlers. Requests that never reach a DRF view (an
unknown /api/ path) still get the JSON envelope instead of an HTML page."""

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.defaults import page_not_found, server_error

from .i18n import COMMON_MESSAGES, get_request_language, translate
from .responses import error_body


@require_GET
def health(request):
    """GET /health/ for the deploy pipeline and the container healthcheck.
    200 only when the app can reach the database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def not_found(request, exception=None):
    if not request.path_info.startswith("/api/"):
        return page_not_found(request, exception)
    lang = get_request_language(request)
    return JsonResponse(error_body(translate(COMMON_MESSAGES, "not_found", lang), "not_found"), status=404)


def internal_error(request):
    if not request.path_info.startswith("/api/"):
        return server_error(request)
    lang = get_request_language(request)
    return JsonResponse(error_body(translate(COMMON_MESSAGES, "server_error", lang), "server_error"), status=500)
