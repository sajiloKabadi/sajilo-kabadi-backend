"""User-facing strings for the auth endpoints, in both app languages."""

from apps.common.i18n import translate

AUTH_MESSAGES = {
    "otp_sent": {
        "en": "We sent a {length}-digit code to {phone}",
        "ne": "हामीले {phone} मा {length} अङ्कको कोड पठाएका छौं",
    },
    "invalid_phone": {
        "en": "Enter a valid 10-digit mobile number",
        "ne": "मान्य १० अङ्कको मोबाइल नम्बर राख्नुहोस्",
    },
    "account_blocked": {
        "en": "Your account has been suspended. Please contact support.",
        "ne": "तपाईंको खाता निलम्बन गरिएको छ। कृपया सहायता टोलीलाई सम्पर्क गर्नुहोस्।",
    },
    "otp_rate_limited": {
        "en": "Too many attempts. Try again in {wait}.",
        "ne": "धेरै पटक प्रयास भयो। {wait} पछि फेरि प्रयास गर्नुहोस्।",
    },
    "resend_too_soon": {
        "en": "Please wait {wait} before requesting a new code.",
        "ne": "नयाँ कोड माग्नु अघि {wait} पर्खनुहोस्।",
    },
    "otp_request_not_found": {
        "en": "This code is no longer valid. Please request a new one.",
        "ne": "यो कोड अब मान्य छैन। कृपया नयाँ कोड माग्नुहोस्।",
    },
    "invalid_otp": {
        "en": "That code is not right. {attempts} left.",
        "ne": "कोड मिलेन। अझै {attempts} प्रयास बाँकी छ।",
    },
    "invalid_otp_field": {
        "en": "Invalid code",
        "ne": "अमान्य कोड",
    },
    "otp_expired": {
        "en": "This code has expired. Please request a new one.",
        "ne": "यो कोडको म्याद सकियो। कृपया नयाँ कोड माग्नुहोस्।",
    },
    "role_mismatch": {
        "en": "This number is registered with a different account type.",
        "ne": "यो नम्बर अर्को प्रकारको खातामा दर्ता छ।",
    },
    "otp_attempts_exceeded": {
        "en": "Too many wrong codes. Try again in {wait}.",
        "ne": "धेरै पटक गलत कोड हालियो। {wait} पछि फेरि प्रयास गर्नुहोस्।",
    },
    "signed_in": {
        "en": "Signed in",
        "ne": "साइन इन भयो",
    },
    "token_refreshed": {
        "en": "Token refreshed",
        "ne": "टोकन नवीकरण भयो",
    },
    "refresh_invalid": {
        "en": "Your session has expired. Please sign in again.",
        "ne": "तपाईंको सत्र समाप्त भयो। कृपया फेरि साइन इन गर्नुहोस्।",
    },
    "profile": {
        "en": "Profile",
        "ne": "प्रोफाइल",
    },
    "profile_updated": {
        "en": "Profile updated",
        "ne": "प्रोफाइल अद्यावधिक भयो",
    },
}


def msg(key: str, lang: str, **kwargs) -> str:
    return translate(AUTH_MESSAGES, key, lang, **kwargs)


def attempts_left_text(count: int, lang: str) -> str:
    if lang == "ne":
        return f"{count} पटक"
    return f"{count} attempt" + ("" if count == 1 else "s")
