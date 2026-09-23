from rest_framework import status as http_status
from rest_framework.response import Response


def success_response(message: str, data=None, status: int = http_status.HTTP_200_OK) -> Response:
    """Success envelope: { "success": true, "message": ..., "data": {...} }"""
    return Response(
        {"success": True, "message": message, "data": data if data is not None else {}},
        status=status,
    )


def error_body(message: str, error_code: str, errors=None, data=None) -> dict:
    """Error envelope. `data` is only included when the error carries extra
    values the client needs (retry_after, attempts_left)."""
    body = {
        "success": False,
        "message": message,
        "error_code": error_code,
        "errors": errors or {},
    }
    if data is not None:
        body["data"] = data
    return body
