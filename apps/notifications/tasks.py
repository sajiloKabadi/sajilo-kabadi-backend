from celery import shared_task

from .services import send_sms


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def send_sms_task(self, to: str, message: str) -> None:
    try:
        send_sms(to, message)
    except Exception as exc:  # retry any gateway failure
        raise self.retry(exc=exc) from exc
