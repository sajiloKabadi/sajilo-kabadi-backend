import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SMSDeliveryError(Exception):
    pass


class AakashSMSBackend:
    """Aakash SMS v3: POST auth_token, to, text to /sms/v3/send.

    `to` is the 10-digit Nepali number without country code, which is the
    format the rest of the app stores. The message text is never logged,
    because for OTPs it contains the code.
    """

    def send(self, to: str, message: str) -> None:
        token = settings.AAKASH_SMS_AUTH_TOKEN
        if not token:
            raise SMSDeliveryError("AAKASH_SMS_AUTH_TOKEN is not configured")

        try:
            response = requests.post(
                settings.AAKASH_SMS_API_URL,
                data={"auth_token": token, "to": to, "text": message},
                timeout=settings.AAKASH_SMS_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise SMSDeliveryError(f"Aakash SMS request failed: {exc.__class__.__name__}") from None

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if response.status_code >= 400 or payload.get("error") is True:
            raise SMSDeliveryError(
                f"Aakash SMS rejected the message (HTTP {response.status_code}): {payload.get('message', '')}"
            )

        invalid = (payload.get("data") or {}).get("invalid") or []
        if invalid:
            raise SMSDeliveryError("Aakash SMS reported the recipient number as invalid")

        logger.info("SMS queued with Aakash for ***%s", to[-4:])
