"""GET /me/ (contract 4.1): the User plus lifetime stats and the one-line
summaries the Profile settings rows show, in the request language."""

from apps.pickups.selectors import open_dispute_titles, user_stats

from .messages import msg
from .presenters import user_dict


def me_payload(user, lang: str, request=None) -> dict:
    from apps.sellers.models import Address

    addresses = list(Address.objects.filter(user=user).values_list("area", "is_default")) if user.is_seller else []
    default_area = next((area for area, is_default in addresses if is_default), None)

    data = user_dict(user, request)
    data["phone_masked"] = user.phone_masked
    data["area"] = default_area
    return {
        "user": data,
        "stats": user_stats(user),
        "summaries": {
            "address_count": len(addresses) if user.is_seller else None,
            "addresses": ", ".join(dict.fromkeys(area for area, _ in addresses)) or None,
            "payout_method": _payout_summary(user, lang),
            "notifications": _notifications_summary(user, lang),
            "disputes": ", ".join(open_dispute_titles(user, lang)) or None,
        },
    }


def _payout_summary(user, lang: str) -> str:
    from apps.wallet.services import default_payout_method

    method = default_payout_method(user)
    wallet = msg("summary_wallet", lang)
    return f"{wallet} · {method.label}" if method else wallet


def _notifications_summary(user, lang: str) -> str:
    from apps.materials.services import material_names
    from apps.notifications.models import preference_for

    pref = preference_for(user)
    if pref.rate_alerts_enabled and pref.rate_alert_material_ids:
        names = material_names(pref.rate_alert_material_ids, lang)
        ordered = [names[i] for i in pref.rate_alert_material_ids if i in names]
        listed = ", ".join(n.lower() if lang == "en" else n for n in ordered)
        return msg("summary_rate_alerts", lang, names=listed)
    if pref.pickup_updates:
        return msg("summary_pickup_updates", lang)
    return msg("summary_notifications_off", lang)
