"""Tiny message catalog for API `message` strings.

The app sends `Accept-Language: en` or `ne` and shows `message` verbatim in a
snackbar, so every string we return has to exist in both languages. Each app
keeps its own catalog dict and resolves keys through `translate()`.
"""

import math

SUPPORTED_LANGUAGES = ("en", "ne")
DEFAULT_LANGUAGE = "en"

COMMON_MESSAGES = {
    "validation_error": {
        "en": "Please check the details you entered.",
        "ne": "कृपया तपाईंले राख्नुभएको विवरण जाँच गर्नुहोस्।",
    },
    "token_invalid": {
        "en": "Your session has expired. Please sign in again.",
        "ne": "तपाईंको सत्र समाप्त भयो। कृपया फेरि साइन इन गर्नुहोस्।",
    },
    "forbidden": {
        "en": "You do not have permission to do this.",
        "ne": "तपाईंलाई यो काम गर्ने अनुमति छैन।",
    },
    "not_found": {
        "en": "Not found.",
        "ne": "फेला परेन।",
    },
    "method_not_allowed": {
        "en": "This action is not allowed.",
        "ne": "यो कार्य गर्न मिल्दैन।",
    },
    "rate_limited": {
        "en": "Too many requests. Try again in {wait}.",
        "ne": "धेरै अनुरोध भयो। {wait} पछि फेरि प्रयास गर्नुहोस्।",
    },
    "conflict": {
        "en": "This can't be done right now.",
        "ne": "यो काम अहिले गर्न मिल्दैन।",
    },
    "app_update_required": {
        "en": "Please update the app to continue.",
        "ne": "कृपया अगाडि बढ्न एप अपडेट गर्नुहोस्।",
    },
    "server_error": {
        "en": "Something went wrong. Please try again.",
        "ne": "केही गडबड भयो। कृपया फेरि प्रयास गर्नुहोस्।",
    },
}


def get_request_language(request) -> str:
    """Pick `en` or `ne` from the Accept-Language header (first match wins)."""
    header = ""
    if request is not None:
        header = request.META.get("HTTP_ACCEPT_LANGUAGE", "") or ""
    for part in header.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in SUPPORTED_LANGUAGES:
            return code
    return DEFAULT_LANGUAGE


def format_wait(seconds: int, lang: str) -> str:
    """Human wait time for rate-limit messages: seconds under a minute,
    otherwise whole minutes rounded up."""
    seconds = max(int(seconds), 1)
    if seconds < 60:
        if lang == "ne":
            return f"{seconds} सेकेन्ड"
        return f"{seconds} second" + ("" if seconds == 1 else "s")
    minutes = math.ceil(seconds / 60)
    if lang == "ne":
        return f"{minutes} मिनेट"
    return f"{minutes} minute" + ("" if minutes == 1 else "s")


def translate(catalog: dict, key: str, lang: str, **kwargs) -> str:
    entry = catalog.get(key) or COMMON_MESSAGES[key]
    text = entry.get(lang) or entry[DEFAULT_LANGUAGE]
    return text.format(**kwargs) if kwargs else text
