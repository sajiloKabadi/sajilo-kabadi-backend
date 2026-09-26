"""Periodic server jobs. Run every minute from cron on the server:

    * * * * * cd /opt/sajilokabadi && ./compose.sh exec -T api python manage.py housekeeping

Reads also do the time-critical parts lazily (expiry, offline), so a missed
run delays pushes, never correctness.
"""

import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Expire unaccepted pickups, set silent collectors offline, prune old rows."

    def handle(self, *args, **options):
        from apps.accounts.models import OTPRequest
        from apps.collectors.models import LocationPing
        from apps.collectors.services import expire_stale_online
        from apps.common.models import IdempotencyKey
        from apps.pickups.selectors import expire_overdue

        now = timezone.now()
        expired = 0
        while True:
            batch = expire_overdue()
            expired += batch
            if batch < 500:
                break
        offline = expire_stale_online()
        pings, _ = LocationPing.objects.filter(recorded_at__lt=now - dt.timedelta(hours=24)).delete()
        keys, _ = IdempotencyKey.objects.filter(created_at__lt=now - dt.timedelta(days=2)).delete()
        otps, _ = OTPRequest.objects.filter(created_at__lt=now - dt.timedelta(days=30)).delete()
        self.stdout.write(
            f"expired={expired} offline={offline} pings_deleted={pings} idempotency_deleted={keys} otp_deleted={otps}"
        )
