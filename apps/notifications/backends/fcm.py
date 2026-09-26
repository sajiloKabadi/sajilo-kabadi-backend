"""Firebase Cloud Messaging, HTTP v1 API.

Needs FCM_PROJECT_ID and FCM_CREDENTIALS_FILE (a Firebase service-account
JSON). Tokens that FCM reports as unregistered are removed from the user's
devices, so dead phones stop costing a request each time.
"""

import logging
import threading

import requests
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]
_lock = threading.Lock()
_credentials = None


def _access_token() -> str:
    global _credentials
    with _lock:
        if _credentials is None:
            _credentials = service_account.Credentials.from_service_account_file(
                settings.FCM_CREDENTIALS_FILE, scopes=SCOPES
            )
        if not _credentials.valid:
            _credentials.refresh(Request())
        return _credentials.token


class FCMPushBackend:
    def send(self, tokens, title, body, data):
        url = f"https://fcm.googleapis.com/v1/projects/{settings.FCM_PROJECT_ID}/messages:send"
        headers = {"Authorization": f"Bearer {_access_token()}"}
        dead = []
        with requests.Session() as session:
            for token in tokens:
                message = {
                    "message": {
                        "token": token,
                        "notification": {"title": title, "body": body},
                        "data": data,
                        "android": {"priority": "high"},
                        "apns": {"headers": {"apns-priority": "10"}},
                    }
                }
                response = session.post(url, json=message, headers=headers, timeout=10)
                if response.status_code == 404 or "UNREGISTERED" in response.text:
                    dead.append(token)
                elif response.status_code >= 400:
                    logger.warning("FCM rejected a push (HTTP %s)", response.status_code)
        if dead:
            from apps.accounts.models import UserDevice

            UserDevice.objects.filter(fcm_token__in=dead).update(fcm_token=None)
