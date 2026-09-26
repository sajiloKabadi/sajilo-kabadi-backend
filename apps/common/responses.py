from rest_framework import status as http_status
from rest_framework.response import Response

_EMPTY = object()


def success_response(message: str, data=_EMPTY, status: int = http_status.HTTP_200_OK) -> Response:
    """Success envelope: { "success": true, "message": ..., "data": ... }.
    Omitting `data` sends {}; pass None explicitly to send null."""
    return Response(
        {"success": True, "message": message, "data": {} if data is _EMPTY else data},
        status=status,
    )


def error_body(message: str, error_code: str, errors=None, data=None) -> dict:
    """Error envelope (contract 1.2). `data` is always present: null unless
    the error documents extra values such as retry_after."""
    return {
        "success": False,
        "message": message,
        "error_code": error_code,
        "errors": errors or {},
        "data": data,
    }
