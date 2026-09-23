import logging
import threading

from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


def send_sms(to: str, message: str) -> None:
    """Send synchronously through the configured backend. Blocks on the
    gateway; request handlers should use `send_sms_async` instead."""
    backend_path = getattr(settings, "SMS_BACKEND", "apps.notifications.backends.console.ConsoleSMSBackend")
    backend_class = import_string(backend_path)
    backend_class().send(to, message)


def send_sms_async(to: str, message: str) -> None:
    """Queue an SMS without blocking the response.

    Runs after the current transaction commits, so a rolled-back request
    never sends a code. SMS_DISPATCH picks the mechanism: "celery" (needs a
    running worker) or "thread" (in-process, for dev and small deployments).
    """
    mode = getattr(settings, "SMS_DISPATCH", "thread")

    def dispatch():
        if mode == "celery":
            from .tasks import send_sms_task

            send_sms_task.delay(to, message)
        elif mode == "sync":
            _send_logged(to, message)
        else:
            threading.Thread(target=_send_logged, args=(to, message), daemon=True).start()

    transaction.on_commit(dispatch)


def _send_logged(to: str, message: str) -> None:
    try:
        send_sms(to, message)
    except Exception:
        # Log without the message body: for OTPs it holds the code.
        logger.exception("SMS delivery failed for ***%s", to[-4:])
