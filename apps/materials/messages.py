from apps.common.i18n import translate

MATERIAL_MESSAGES = {
    "rates": {"en": "Today's rates", "ne": "आजका दरहरू"},
    "category_metal": {"en": "Metal", "ne": "धातु"},
    "category_paper_plastic": {"en": "Paper & plastic", "ne": "कागज र प्लास्टिक"},
    "category_other": {"en": "Other", "ne": "अन्य"},
    "rates_note": {
        "en": (
            "Rates are the average paid by verified kabadi centers in {city} valley today. "
            "Your collector may offer a little more or less after weighing."
        ),
        "ne": (
            "यी दरहरू आज {city} उपत्यकाका प्रमाणित कबाडी केन्द्रहरूले तिरेको औसत हुन्। "
            "तौलपछि सङ्कलकले अलि बढी वा कम प्रस्ताव गर्न सक्नुहुन्छ।"
        ),
    },
    "city_Kathmandu": {"en": "Kathmandu", "ne": "काठमाडौं"},
}


def msg(key: str, lang: str, **kwargs) -> str:
    return translate(MATERIAL_MESSAGES, key, lang, **kwargs)


def city_label(city: str, lang: str) -> str:
    entry = MATERIAL_MESSAGES.get(f"city_{city}")
    return (entry.get(lang) or entry["en"]) if entry else city
