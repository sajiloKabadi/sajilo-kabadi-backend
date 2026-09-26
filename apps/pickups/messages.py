from apps.common.i18n import translate

PICKUP_MESSAGES = {
    # Envelope messages
    "availability": {"en": "Available slots", "ne": "उपलब्ध समय"},
    "quote": {"en": "Estimated payout", "ne": "अनुमानित भुक्तानी"},
    "booked": {"en": "Pickup booked · Booking {ref}", "ne": "पिकअप बुक भयो · बुकिङ {ref}"},
    "pickups": {"en": "Your pickups", "ne": "तपाईंका पिकअपहरू"},
    "pickup": {"en": "Pickup", "ne": "पिकअप"},
    "cancelled_ok": {"en": "Pickup cancelled", "ne": "पिकअप रद्द भयो"},
    "rated": {"en": "Thanks for rating", "ne": "मूल्याङ्कनका लागि धन्यवाद"},
    "weigh_sheet": {"en": "Weighing sheet", "ne": "तौल पाना"},
    "flagged": {
        "en": "Flag sent. Support will review it, usually within a day.",
        "ne": "आपत्ति पठाइयो। सहायता टोलीले प्रायः एक दिनभित्र हेर्नेछ।",
    },
    "paid": {"en": "Rs {amount} added to your wallet", "ne": "रु {amount} तपाईंको वालेटमा थपियो"},
    "paid_cash": {"en": "Rs {amount} recorded as paid in cash", "ne": "रु {amount} नगद भुक्तानीको रूपमा दर्ता भयो"},
    "held": {
        "en": "Accepted. Payment is on hold until support resolves the flag.",
        "ne": "स्वीकार भयो। आपत्ति समाधान नभएसम्म भुक्तानी रोकिएको छ।",
    },
    "disputes": {"en": "Help & disputes", "ne": "सहायता र विवाद"},
    "dispute_opened": {
        "en": "We've received your report and will get back to you.",
        "ne": "तपाईंको गुनासो प्राप्त भयो, हामी सम्पर्क गर्नेछौं।",
    },
    # Errors
    "pickup_not_found": {"en": "This pickup was not found.", "ne": "यो पिकअप भेटिएन।"},
    "address_not_found": {"en": "This address was not found.", "ne": "यो ठेगाना भेटिएन।"},
    "address_required": {
        "en": "Add a pickup address first.",
        "ne": "पहिले पिकअप ठेगाना थप्नुहोस्।",
    },
    "material_not_found": {
        "en": "One of the materials is no longer available. Refresh the list.",
        "ne": "एउटा सामग्री अब उपलब्ध छैन। सूची ताजा गर्नुहोस्।",
    },
    "material_not_found_item": {"en": "Unknown material {id}", "ne": "अज्ञात सामग्री {id}"},
    "slot_required": {"en": "Choose a time slot.", "ne": "समय छान्नुहोस्।"},
    "slot_unavailable": {
        "en": "That time slot is no longer available. Pick another one.",
        "ne": "त्यो समय अब उपलब्ध छैन। अर्को छान्नुहोस्।",
    },
    "too_many_active_pickups": {
        "en": "You already have {limit} active pickups. Finish one before booking another.",
        "ne": "तपाईंका {limit} वटा सक्रिय पिकअप छन्। अर्को बुक गर्नु अघि एउटा सक्नुहोस्।",
    },
    "cannot_cancel": {
        "en": "The collector is already on the way, so this pickup can't be cancelled.",
        "ne": "सङ्कलक आइसक्नुभएकाले यो पिकअप रद्द गर्न मिल्दैन।",
    },
    "pickup_not_completed": {
        "en": "You can rate once the pickup is complete.",
        "ne": "पिकअप सकिएपछि मात्र मूल्याङ्कन गर्न सकिन्छ।",
    },
    "already_rated": {"en": "You've already rated this pickup.", "ne": "तपाईंले यो पिकअप मूल्याङ्कन गरिसक्नुभयो।"},
    "weigh_sheet_not_started": {
        "en": "Weighing hasn't started yet.",
        "ne": "तौल अझै सुरु भएको छैन।",
    },
    "line_not_found": {"en": "This line is not on the sheet.", "ne": "यो लाइन तौल पानामा छैन।"},
    "line_already_flagged": {
        "en": "You've already flagged this line.",
        "ne": "तपाईंले यो लाइनमा पहिले नै आपत्ति जनाउनुभएको छ।",
    },
    "sheet_closed": {"en": "This weighing sheet is closed.", "ne": "यो तौल पाना बन्द भइसकेको छ।"},
    "sheet_not_submitted": {
        "en": "The collector is still weighing. Wait until they finish.",
        "ne": "सङ्कलकले अझै तौल गर्दै हुनुहुन्छ। सकिएसम्म पर्खनुहोस्।",
    },
    "sheet_changed": {
        "en": "The weights just changed. Check the updated sheet before accepting.",
        "ne": "तौल भर्खरै परिवर्तन भयो। स्वीकार गर्नु अघि नयाँ पाना जाँच्नुहोस्।",
    },
    "sheet_empty": {"en": "Add at least one weight.", "ne": "कम्तीमा एउटा तौल थप्नुहोस्।"},
    # Collector
    "jobs": {"en": "Pickups near you", "ne": "नजिकका पिकअपहरू"},
    "job": {"en": "Job", "ne": "काम"},
    "job_accepted": {"en": "Job accepted", "ne": "काम स्वीकार भयो"},
    "job_declined": {"en": "Job hidden", "ne": "काम लुकाइयो"},
    "status_updated": {"en": "Status updated", "ne": "स्थिति अद्यावधिक भयो"},
    "location_saved": {"en": "Location saved", "ne": "स्थान सुरक्षित भयो"},
    "weights_saved": {"en": "Weights saved", "ne": "तौल सुरक्षित भयो"},
    "weights_submitted": {"en": "Weights sent to the seller", "ne": "तौल बिक्रेतालाई पठाइयो"},
    "dashboard": {"en": "Collector home", "ne": "सङ्कलक गृह"},
    "online": {"en": "You're online. Jobs are coming to you.", "ne": "तपाईं अनलाइन हुनुहुन्छ।"},
    "offline": {"en": "You're offline.", "ne": "तपाईं अफलाइन हुनुहुन्छ।"},
    "job_taken": {
        "en": "Another collector took this job first.",
        "ne": "अर्को सङ्कलकले यो काम पहिले लिनुभयो।",
    },
    "has_active_job": {"en": "Finish your current job first.", "ne": "पहिले हालको काम सक्नुहोस्।"},
    "collector_offline": {"en": "Go online first.", "ne": "पहिले अनलाइन हुनुहोस्।"},
    "collector_not_verified": {
        "en": "Your account is waiting for approval. We'll let you know once it's verified.",
        "ne": "तपाईंको खाता स्वीकृतिको पर्खाइमा छ। प्रमाणित भएपछि जानकारी दिनेछौं।",
    },
    "location_required": {
        "en": "Turn on location to go online.",
        "ne": "अनलाइन हुन लोकेसन खोल्नुहोस्।",
    },
    "invalid_transition": {"en": "This step isn't possible right now.", "ne": "यो चरण अहिले सम्भव छैन।"},
    # Delivery options (8.2)
    "opt_self_dropoff_title": {"en": "I'll drop it myself", "ne": "म आफैं पुर्‍याउँछु"},
    "opt_self_dropoff_subtitle": {
        "en": "Take it to the center — nothing deducted",
        "ne": "केन्द्रमा लैजानुहोस् — केही कटौती हुँदैन",
    },
    "opt_collector_pickup_title": {"en": "Collector picks up", "ne": "सङ्कलकले लैजान्छ"},
    "opt_collector_pickup_subtitle": {
        "en": "Free above {free_kg} kg, Rs {fee} below",
        "ne": "{free_kg} केजीभन्दा माथि निःशुल्क, कम भए रु {fee}",
    },
    "opt_truck_helper_title": {"en": "Truck + 1 helper", "ne": "ट्रक + १ सहयोगी"},
    "opt_truck_helper_subtitle": {
        "en": "For heavy loads · Rs {base} + Rs {per_km}/km",
        "ne": "गह्रौं सामानका लागि · रु {base} + रु {per_km}/किमी",
    },
    # Timeline (8.6)
    "tl_requested": {"en": "Pickup confirmed", "ne": "पिकअप पक्का भयो"},
    "tl_matched": {"en": "{name} accepted the job", "ne": "{name}ले काम स्वीकार गर्नुभयो"},
    "tl_matched_anon": {"en": "A collector accepted the job", "ne": "सङ्कलकले काम स्वीकार गर्नुभयो"},
    "tl_on_the_way": {"en": "On the way to you", "ne": "तपाईंतर्फ आउँदै"},
    "tl_arrived": {"en": "{name} has arrived", "ne": "{name} आइपुग्नुभयो"},
    "tl_arrived_anon": {"en": "Collector has arrived", "ne": "सङ्कलक आइपुग्नुभयो"},
    "tl_weighing": {"en": "Weighing & payment", "ne": "तौल र भुक्तानी"},
    "tl_cancelled": {"en": "Pickup cancelled", "ne": "पिकअप रद्द भयो"},
    "tl_expired": {"en": "No collector was available", "ne": "कुनै सङ्कलक उपलब्ध भएनन्"},
    # Dispute titles (13)
    "dispute_weight_disagreement": {"en": "Weight disagreement", "ne": "तौलमा असहमति"},
    "dispute_missed_pickup": {"en": "Missed pickup", "ne": "छुटेको पिकअप"},
    "dispute_payment": {"en": "Payment issue", "ne": "भुक्तानी समस्या"},
    "dispute_behaviour": {"en": "Behaviour", "ne": "व्यवहार"},
    "dispute_other": {"en": "Other issue", "ne": "अन्य समस्या"},
}


def msg(key: str, lang: str, **kwargs) -> str:
    return translate(PICKUP_MESSAGES, key, lang, **kwargs)
