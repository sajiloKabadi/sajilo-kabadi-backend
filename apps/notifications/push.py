"""Push notifications (contract 15).

Every push is a small data message (`type` plus ids; the app refetches on
tap) with a `notification` block localised to the recipient's saved
language. Sending happens after the DB commit and off the request thread,
like SMS. Preferences are honoured: pickup updates can be switched off,
rate alerts are opt-in, money and dispute messages always go out.
"""

import logging
import threading

from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string

from apps.common.i18n import translate

from .models import NotificationPreference

logger = logging.getLogger(__name__)

# Types gated by the "pickup updates" switch.
PICKUP_UPDATE_TYPES = {
    "collector_matched",
    "pickup_status",
    "weigh_sheet_ready",
    "pickup_expired",
    "pickup_cancelled",
    "new_job",
    "line_flagged",
}

PUSH_MESSAGES = {
    "collector_matched.title": {"en": "{name} is your collector", "ne": "{name} तपाईंको सङ्कलक"},
    "collector_matched.body": {"en": "Pickup {ref} · {when}", "ne": "पिकअप {ref} · {when}"},
    "pickup_status.on_the_way.title": {"en": "{name} is on the way", "ne": "{name} आउँदै हुनुहुन्छ"},
    "pickup_status.on_the_way.body": {
        "en": "Arriving in about {eta} minutes",
        "ne": "करिब {eta} मिनेटमा आइपुग्नुहुन्छ",
    },
    "pickup_status.on_the_way.body_no_eta": {"en": "Pickup {ref} is on its way", "ne": "पिकअप {ref} आउँदैछ"},
    "pickup_status.arrived.title": {"en": "{name} has arrived", "ne": "{name} आइपुग्नुभयो"},
    "pickup_status.arrived.body": {"en": "Please bring your items out", "ne": "कृपया सामान बाहिर ल्याउनुहोस्"},
    "weigh_sheet_ready.title": {"en": "Weighing done", "ne": "तौल सकियो"},
    "weigh_sheet_ready.body": {
        "en": "Check the weights and accept to get paid · {ref}",
        "ne": "तौल जाँचेर भुक्तानी लिन स्वीकार गर्नुहोस् · {ref}",
    },
    "payment_settled.title": {"en": "Payment received", "ne": "भुक्तानी प्राप्त भयो"},
    "payment_settled.body": {"en": "Rs {amount} for {ref}", "ne": "{ref} का लागि रु {amount}"},
    "pickup_expired.title": {"en": "No collector was available", "ne": "कुनै सङ्कलक उपलब्ध भएनन्"},
    "pickup_expired.body": {"en": "Pickup {ref} expired. Book again?", "ne": "पिकअप {ref} को समय सकियो। फेरि बुक गर्ने?"},
    "pickup_cancelled.title": {"en": "Pickup cancelled", "ne": "पिकअप रद्द भयो"},
    "pickup_cancelled.body": {"en": "{ref} was cancelled by the seller", "ne": "बिक्रेताले {ref} रद्द गर्नुभयो"},
    "new_job.title": {"en": "New pickup nearby", "ne": "नजिकै नयाँ पिकअप"},
    "new_job.body": {"en": "{kg} kg · {area} · {when}", "ne": "{kg} केजी · {area} · {when}"},
    "line_flagged.title": {"en": "A weight was flagged", "ne": "एउटा तौलमा आपत्ति"},
    "line_flagged.body": {
        "en": "{material} on {ref} was flagged by the seller",
        "ne": "बिक्रेताले {ref} को {material} मा आपत्ति जनाउनुभयो",
    },
    "dispute_updated.title": {"en": "Dispute updated", "ne": "विवाद अद्यावधिक भयो"},
    "dispute_updated.body": {"en": "{title} on {ref}: {status}", "ne": "{ref} को {title}: {status}"},
    "rate_alert.title": {"en": "{material} rate {direction}", "ne": "{material} को दर {direction}"},
    "rate_alert.body": {"en": "Now Rs {price}/kg ({change}%)", "ne": "अहिले रु {price}/केजी ({change}%)"},
    "rate_alert.up": {"en": "up", "ne": "बढ्यो"},
    "rate_alert.down": {"en": "down", "ne": "घट्यो"},
    "withdrawal_status.title": {"en": "Withdrawal {status}", "ne": "निकासी {status}"},
    "withdrawal_status.body": {"en": "Rs {amount} to {bank}", "ne": "{bank} मा रु {amount}"},
    "status.completed": {"en": "completed", "ne": "सम्पन्न"},
    "status.failed": {"en": "failed", "ne": "असफल"},
    "status.open": {"en": "open", "ne": "खुला"},
    "status.resolved": {"en": "resolved", "ne": "समाधान भयो"},
    "status.rejected": {"en": "rejected", "ne": "अस्वीकृत"},
}


def text(key: str, lang: str, **kwargs) -> str:
    return translate(PUSH_MESSAGES, key, lang, **kwargs)


def notify(user, push_type: str, data: dict, title_key: str | None = None, body_key: str | None = None, **fmt):
    """Queue one push to every registered device of `user`. `fmt` values may
    be callables taking the language, for per-language parts."""
    notify_many([user], push_type, data, title_key=title_key, body_key=body_key, **fmt)


def notify_many(users, push_type: str, data: dict, title_key=None, body_key=None, **fmt):
    users = [u for u in users if u is not None]
    if not users:
        return
    from apps.accounts.models import UserDevice

    user_ids = [u.id for u in users]
    prefs = {p.user_id: p for p in NotificationPreference.objects.filter(user_id__in=user_ids)}
    tokens: dict = {}
    for user_id, token in (
        UserDevice.objects.filter(user_id__in=user_ids)
        .exclude(fcm_token__isnull=True)
        .exclude(fcm_token="")
        .values_list("user_id", "fcm_token")
    ):
        tokens.setdefault(user_id, []).append(token)

    title_key = title_key or f"{push_type}.title"
    body_key = body_key or f"{push_type}.body"
    payload = {k: str(v) for k, v in {"type": push_type, **data}.items() if v is not None}

    messages = []
    for user in users:
        pref = prefs.get(user.id)
        if push_type in PICKUP_UPDATE_TYPES and pref is not None and not pref.pickup_updates:
            continue
        if not tokens.get(user.id):
            continue
        lang = user.language
        values = {k: (v(lang) if callable(v) else v) for k, v in fmt.items()}
        messages.append(
            {
                "tokens": tokens[user.id],
                "title": text(title_key, lang, **values),
                "body": text(body_key, lang, **values),
                "data": payload,
            }
        )
    if messages:
        transaction.on_commit(lambda: _dispatch(messages))


def send_rate_alerts(material, price: int, change_percent: float) -> None:
    """Sellers who opted in to alerts for this material (contract 4.5)."""
    from apps.accounts.models import User

    watcher_ids = [
        p.user_id
        for p in NotificationPreference.objects.filter(rate_alerts_enabled=True).only(
            "user_id", "rate_alert_material_ids"
        )
        if material.id in (p.rate_alert_material_ids or [])
    ]
    users = list(User.objects.filter(id__in=watcher_ids, is_active=True, role=User.Role.SELLER))
    direction_key = "rate_alert.up" if change_percent > 0 else "rate_alert.down"
    notify_many(
        users,
        "rate_alert",
        {"material_id": material.id},
        material=material.name,
        direction=lambda lang: text(direction_key, lang),
        price=price,
        change=f"{change_percent:+.1f}",
    )


def _dispatch(messages) -> None:
    mode = getattr(settings, "PUSH_DISPATCH", getattr(settings, "SMS_DISPATCH", "thread"))
    if mode == "sync":
        _send(messages)
    else:
        threading.Thread(target=_send, args=(messages,), daemon=True).start()


def _send(messages) -> None:
    try:
        backend = import_string(settings.PUSH_BACKEND)()
        for message in messages:
            backend.send(**message)
    except Exception:
        logger.exception("Push delivery failed")
