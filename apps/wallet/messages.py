from apps.common.i18n import translate

WALLET_MESSAGES = {
    "wallet": {"en": "Wallet", "ne": "वालेट"},
    "transactions": {"en": "Transactions", "ne": "कारोबारहरू"},
    "payout_methods": {"en": "Payout methods", "ne": "भुक्तानी विधिहरू"},
    "payout_method_added": {"en": "Bank account added", "ne": "बैंक खाता थपियो"},
    "payout_method_removed": {"en": "Bank account removed", "ne": "बैंक खाता हटाइयो"},
    "payout_method_not_found": {"en": "This bank account was not found.", "ne": "यो बैंक खाता भेटिएन।"},
    "withdrawal_created": {
        "en": "Withdrawal requested. It reaches your bank shortly.",
        "ne": "निकासी अनुरोध भयो। चाँडै तपाईंको बैंकमा पुग्नेछ।",
    },
    "below_minimum": {"en": "The minimum withdrawal is Rs {minimum}.", "ne": "न्यूनतम निकासी रु {minimum} हो।"},
    "insufficient_balance": {
        "en": "You don't have enough balance for this withdrawal.",
        "ne": "यो निकासीका लागि पर्याप्त ब्यालेन्स छैन।",
    },
    "payout_method_unverified": {
        "en": "This bank account is not verified yet.",
        "ne": "यो बैंक खाता अझै प्रमाणित भएको छैन।",
    },
    "payouts_on_hold": {"en": "Withdrawals are paused right now.", "ne": "निकासी अहिले रोकिएको छ।"},
    "statement": {"en": "Statement ready", "ne": "विवरण तयार छ"},
    "statement_link_invalid": {
        "en": "This statement link has expired. Open the statement again from the app.",
        "ne": "यो विवरणको लिङ्कको म्याद सकियो। एपबाट फेरि खोल्नुहोस्।",
    },
    "title_pickup": {"en": "Pickup", "ne": "पिकअप"},
    "title_dropoff": {"en": "Drop-off", "ne": "ड्रप-अफ"},
    "title_job_earning": {"en": "Job earning", "ne": "कामको कमाइ"},
    "title_adjustment": {"en": "Adjustment", "ne": "मिलान"},
    "title_withdrawal": {"en": "Withdraw to {bank}", "ne": "{bank} मा निकासी"},
    "bank": {"en": "bank", "ne": "बैंक"},
    "method_wallet": {"en": "Wallet", "ne": "वालेट"},
    "method_cash": {"en": "Cash", "ne": "नगद"},
    "method_bank": {"en": "Bank", "ne": "बैंक"},
}

# bank_code -> display name for POST /me/payout-methods/.
BANKS = {
    "NABIL": "Nabil Bank",
    "NIMB": "Nepal Investment Mega Bank",
    "GLOBAL": "Global IME Bank",
    "NIC": "NIC Asia Bank",
    "NMB": "NMB Bank",
    "EVEREST": "Everest Bank",
    "HBL": "Himalayan Bank",
    "SANIMA": "Sanima Bank",
    "PRABHU": "Prabhu Bank",
    "KUMARI": "Kumari Bank",
    "LAXMI": "Laxmi Sunrise Bank",
    "SCB": "Standard Chartered Nepal",
    "NBL": "Nepal Bank",
    "RBB": "Rastriya Banijya Bank",
    "ADBL": "Agricultural Development Bank",
    "MBL": "Machhapuchchhre Bank",
    "PCBL": "Prime Commercial Bank",
    "SBL": "Siddhartha Bank",
    "CZBIL": "Citizens Bank International",
}


def msg(key: str, lang: str, **kwargs) -> str:
    return translate(WALLET_MESSAGES, key, lang, **kwargs)
