"""Default question flows.

Every question has 2–3 options so WhatsApp shows them as tap buttons under the
message (button titles max 20 characters). Each option has a stable `id`
(the WhatsApp reply id), a `title` the customer sees and a `value` saved on
the lead. Budget options carry `max` in INR for the "budget below property
price" rule.

All flows use the keys `timeline` and `next_step` so the HOT/WARM/COLD rules
work the same everywhere.
"""

TIMELINE = {
    "key": "timeline",
    "label": "Buying timeline",
    "prompt": "When are you planning to buy?",
    "options": [
        {"id": "within_3_months", "title": "Within 3 months", "value": "within_3_months"},
        {"id": "3_6_months", "title": "In 3–6 months", "value": "3_6_months"},
        {"id": "exploring", "title": "Just exploring", "value": "exploring"},
    ],
}

# Each option can say where the chat goes next (`next`: a later question key,
# "__end__" = closing message, "__handoff__" = hand to a person) and send its own
# short `reply` first. Without `next`, the flow moves to the following question.
NEXT_STEP = {
    "key": "next_step",
    "label": "Next step",
    "prompt": "How would you like our team to help you?",
    "options": [
        {"id": "site_visit", "title": "Book site visit", "value": "site_visit", "next": "visit_day"},
        {"id": "call", "title": "Call me", "value": "call", "next": "call_time"},
        {"id": "details", "title": "Send details", "value": "details", "next": "__end__",
         "reply": "Here are the details of *{property}* 👇\n{property_details}{brochure}"},
    ],
}

VISIT_DAY = {
    "key": "visit_day",
    "label": "Visit preference",
    "prompt": "When would you like to visit the site? 🏠",
    "options": [
        {"id": "visit_weekend", "title": "This weekend", "value": "weekend", "next": "__end__",
         "reply": "📅 Great! We'll plan your site visit for this weekend."},
        {"id": "visit_weekday", "title": "On a weekday", "value": "weekday", "next": "__end__",
         "reply": "📅 Great! We'll plan your site visit on a weekday."},
        {"id": "visit_fix", "title": "Call me to fix", "value": "call_to_fix", "next": "__end__",
         "reply": "📞 Sure! We'll call you to fix a convenient visit time."},
    ],
}

CALL_TIME = {
    "key": "call_time",
    "label": "Best time to call",
    "prompt": "When is a good time to call you? 📞",
    "options": [
        {"id": "call_morning", "title": "Morning (9–12)", "value": "morning", "next": "__end__"},
        {"id": "call_afternoon", "title": "Afternoon (12–4)", "value": "afternoon", "next": "__end__"},
        {"id": "call_evening", "title": "Evening (4–8)", "value": "evening", "next": "__end__"},
    ],
}
RULES = {
    # HOT: buying within 3 months AND wants a visit or a call.
    "hot": {"timeline_in": ["within_3_months"], "next_step_in": ["site_visit", "call"]},
    # WARM: buying within 6 months.
    "warm": {"timeline_in": ["within_3_months", "3_6_months"]},
    # Everything else is COLD. Budget below the property's starting price drops one level.
    "budget_below_min_downgrade": True,
}

# Sent after the customer taps "Yes, go ahead", right before the first question.
INTRO = "Great, thank you {name}! 🙏\n\nHere's a quick look at *{property}*:\n{property_details}\n\n"
CLOSING = (
    "Thank you, {name}! 🙏 We've noted your requirements.\n\n"
    "Our team will reach out to you within the next 24 hours. "
    "We're available 24/7 — just reply here anytime if you have a question.\n\n"
    "Reply STOP anytime to end this chat."
)

DEFAULT_FLOWS = [
    {
        "key": "apartment",
        "name": "Apartment / Flat",
        "intro_message": INTRO,
        "closing_message": CLOSING,
        "rules": RULES,
        "questions": [
            {
                "key": "configuration",
                "label": "Configuration",
                "prompt": "Which home size are you looking for?",
                "options": [
                    {"id": "2bhk", "title": "2 BHK", "value": "2BHK"},
                    {"id": "3bhk", "title": "3 BHK", "value": "3BHK"},
                    {"id": "4bhk", "title": "4 BHK or bigger", "value": "4BHK+"},
                ],
            },
            {
                "key": "budget",
                "label": "Budget",
                "prompt": "What is your budget?",
                "options": [
                    {"id": "b_u80l", "title": "Under ₹80 Lakh", "value": "under_80l", "max": 8_000_000},
                    {"id": "b_80l_12c", "title": "₹80 Lakh – 1.2 Cr", "value": "80l_1_2cr", "max": 12_000_000},
                    {"id": "b_12c_plus", "title": "Above ₹1.2 Cr", "value": "above_1_2cr"},
                ],
            },
            TIMELINE,
            NEXT_STEP,
            VISIT_DAY,
            CALL_TIME,
        ],
    },
    {
        "key": "plot",
        "name": "Residential plot",
        "intro_message": INTRO,
        "closing_message": CLOSING,
        "rules": RULES,
        "questions": [
            {
                "key": "plot_size",
                "label": "Plot size",
                "prompt": "What plot size are you looking for?",
                "options": [
                    {"id": "ps_1500", "title": "Up to 1,500 sq ft", "value": "upto_1500"},
                    {"id": "ps_3000", "title": "1,500–3,000 sq ft", "value": "1500_3000"},
                    {"id": "ps_3000p", "title": "Above 3,000 sq ft", "value": "above_3000"},
                ],
            },
            {
                "key": "budget",
                "label": "Budget",
                "prompt": "What is your budget?",
                "options": [
                    {"id": "pb_u30l", "title": "Under ₹30 Lakh", "value": "under_30l", "max": 3_000_000},
                    {"id": "pb_30_60l", "title": "₹30–60 Lakh", "value": "30_60l", "max": 6_000_000},
                    {"id": "pb_60l_plus", "title": "Above ₹60 Lakh", "value": "above_60l"},
                ],
            },
            TIMELINE,
            NEXT_STEP,
            VISIT_DAY,
            CALL_TIME,
        ],
    },
    {
        "key": "commercial",
        "name": "Commercial property",
        "intro_message": INTRO,
        "closing_message": CLOSING,
        "rules": RULES,
        "questions": [
            {
                "key": "space_type",
                "label": "Space type",
                "prompt": "What type of space do you need?",
                "options": [
                    {"id": "office", "title": "Office", "value": "office"},
                    {"id": "shop", "title": "Shop / Showroom", "value": "shop"},
                    {"id": "warehouse", "title": "Warehouse", "value": "warehouse"},
                ],
            },
            {
                "key": "deal_type",
                "label": "Buy or lease",
                "prompt": "Are you looking to buy or lease?",
                "options": [
                    {"id": "buy", "title": "Buy", "value": "buy"},
                    {"id": "lease", "title": "Lease", "value": "lease"},
                ],
            },
            {
                "key": "budget",
                "label": "Budget",
                "prompt": "What is your budget?",
                "options": [
                    {"id": "cb_u1c", "title": "Under ₹1 Cr", "value": "under_1cr", "max": 10_000_000},
                    {"id": "cb_1_3c", "title": "₹1–3 Cr", "value": "1_3cr", "max": 30_000_000},
                    {"id": "cb_3c_plus", "title": "Above ₹3 Cr", "value": "above_3cr"},
                ],
            },
            TIMELINE,
            NEXT_STEP,
            VISIT_DAY,
            CALL_TIME,
        ],
    },
]


def guess_flow_key(text: str | None) -> str:
    t = (text or "").lower()
    if "plot" in t or "land" in t:
        return "plot"
    if any(w in t for w in ("commercial", "office", "shop", "warehouse", "showroom")):
        return "commercial"
    return "apartment"
