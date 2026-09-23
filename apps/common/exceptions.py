import logging

from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .i18n import COMMON_MESSAGES, format_wait, get_request_language, translate
from .responses import error_body

logger = logging.getLogger(__name__)


class ApiError(drf_exceptions.APIException):
    """Raise from views/services to return a contract-shaped error:
    { "success": false, "message", "error_code", "errors", "data"? }
    `message` must already be in the caller's language."""

    def __init__(self, status_code: int, error_code: str, message: str, errors=None, data=None):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.errors = errors or {}
        self.data = data
        super().__init__(detail=message, code=error_code)


def api_exception_handler(exc, context):
    """Render every error in the envelope from docs/api/auth_and_dashboard.md
    section 1.1, with the stable `error_code` values from section 1.2."""
    request = context.get("request")
    lang = get_request_language(request)

    if isinstance(exc, ApiError):
        response = Response(
            error_body(exc.message, exc.error_code, exc.errors, exc.data),
            status=exc.status_code,
        )
        _copy_auth_headers(exc, response)
        return response

    response = exception_handler(exc, context)
    if response is None:
        # Anything DRF does not know about is a 500. Never leak the details.
        logger.exception("Unhandled API error", exc_info=exc)
        return Response(
            error_body(translate(COMMON_MESSAGES, "server_error", lang), "server_error"),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = None
    errors = {}
    if isinstance(exc, drf_exceptions.ValidationError):
        errors = _normalise_errors(response.data)
        error_code = _validation_error_code(exc)
        message = _first_message(errors) or translate(COMMON_MESSAGES, "validation_error", lang)
    elif isinstance(exc, drf_exceptions.ParseError):
        error_code = "validation_error"
        message = translate(COMMON_MESSAGES, "validation_error", lang)
    elif isinstance(exc, (drf_exceptions.NotAuthenticated, drf_exceptions.AuthenticationFailed)):
        # simplejwt's InvalidToken subclasses AuthenticationFailed.
        error_code = "token_invalid"
        message = translate(COMMON_MESSAGES, "token_invalid", lang)
        response.status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, drf_exceptions.PermissionDenied):
        error_code = "forbidden"
        message = translate(COMMON_MESSAGES, "forbidden", lang)
    elif isinstance(exc, drf_exceptions.NotFound):
        error_code = "not_found"
        message = translate(COMMON_MESSAGES, "not_found", lang)
    elif isinstance(exc, drf_exceptions.MethodNotAllowed):
        error_code = "method_not_allowed"
        message = translate(COMMON_MESSAGES, "method_not_allowed", lang)
    elif isinstance(exc, drf_exceptions.Throttled):
        wait = int(exc.wait or 1)
        error_code = "rate_limited"
        message = translate(COMMON_MESSAGES, "rate_limited", lang, wait=format_wait(wait, lang))
        data = {"retry_after": wait}
    else:
        error_code = getattr(exc, "default_code", "error")
        message = _first_message(response.data)

    response.data = error_body(message, error_code, errors, data)
    return response


def _copy_auth_headers(exc, response):
    if getattr(exc, "auth_header", None):
        response["WWW-Authenticate"] = exc.auth_header


def _validation_error_code(exc) -> str:
    """A field error raised with code="invalid_phone" promotes the whole
    response to that error_code; everything else is validation_error."""
    codes = exc.get_codes()
    if isinstance(codes, dict) and "invalid_phone" in _flatten(codes):
        return "invalid_phone"
    return "validation_error"


def _flatten(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _flatten(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _flatten(v)
    else:
        yield value


def _normalise_errors(data) -> dict:
    """Always `{field: [messages]}`. Non-field errors go under
    `non_field_errors`; nested objects are flattened as `parent.child`."""
    if not isinstance(data, dict):
        return {"non_field_errors": [str(m) for m in _flatten(data)]}
    result = {}
    for field, value in data.items():
        if isinstance(value, dict):
            for sub_field, messages in _normalise_errors(value).items():
                result[f"{field}.{sub_field}"] = messages
        else:
            result[field] = [str(m) for m in _flatten(value)]
    return result


def _first_message(data):
    if isinstance(data, dict):
        for value in data.values():
            return _first_message(value)
        return ""
    if isinstance(data, (list, tuple)):
        return _first_message(data[0]) if data else ""
    return str(data)
