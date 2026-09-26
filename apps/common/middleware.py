from django.conf import settings
from django.http import JsonResponse
from django.middleware.common import CommonMiddleware

from .i18n import COMMON_MESSAGES, get_request_language, translate
from .responses import error_body


class ApiCommonMiddleware(CommonMiddleware):
    """CommonMiddleware without APPEND_SLASH for /api/ paths.

    A POST to a slashless path would otherwise get a 301 to the slashed one,
    and most HTTP clients follow it as a body-less GET, so the request shows
    up empty and looks like a validation bug. For the API we answer 404
    instead so the mistake is loud. Admin and other HTML pages keep the
    redirect.
    """

    def should_redirect_with_slash(self, request):
        if request.path_info.startswith("/api/"):
            return False
        return super().should_redirect_with_slash(request)


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for piece in value.strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


class MinAppVersionMiddleware:
    """426 app_update_required when X-App-Version is below MIN_APP_VERSION
    (contract 1.4). Requests without the header (Swagger, curl) pass."""

    def __init__(self, get_response):
        self.get_response = get_response
        minimum = getattr(settings, "MIN_APP_VERSION", "")
        self.minimum = _version_tuple(minimum) if minimum else None
        self.minimum_label = minimum

    def __call__(self, request):
        if self.minimum and request.path_info.startswith("/api/"):
            version = request.headers.get("X-App-Version")
            if version and _version_tuple(version) < self.minimum:
                lang = get_request_language(request)
                return JsonResponse(
                    error_body(
                        translate(COMMON_MESSAGES, "app_update_required", lang),
                        "app_update_required",
                        data={"min_version": self.minimum_label},
                    ),
                    status=426,
                )
        return self.get_response(request)
