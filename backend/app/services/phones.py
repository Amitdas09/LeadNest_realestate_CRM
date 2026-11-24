import hashlib

import phonenumbers

from app.core.config import get_settings


def normalize_phone(raw: object) -> str | None:
    """Return the number in E.164 (+919876543210) or None if it is not a valid number.

    Accepts Meta export values like "p:+919876543210", local numbers like
    "98765 43210" (default region from settings), and "919876543210".
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower().startswith("p:"):
        s = s[2:].strip()
    if not s:
        return None
    candidates = [s]
    digits = "".join(ch for ch in s if ch.isdigit())
    if not s.startswith("+") and len(digits) > 10:
        candidates.append("+" + digits)  # country code without "+"
    for cand in candidates:
        try:
            num = phonenumbers.parse(cand, None if cand.startswith("+") else get_settings().default_phone_region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    return None


def mask_phone(e164: str | None) -> str:
    """+919876543210 -> +91 98•••• 3210"""
    if not e164:
        return ""
    try:
        num = phonenumbers.parse(e164, None)
        cc = f"+{num.country_code}"
        national = str(num.national_number)
    except phonenumbers.NumberParseException:
        return "•••"
    if len(national) <= 6:
        return f"{cc} ••••"
    return f"{cc} {national[:2]}•••• {national[-4:]}"


def phone_hash(e164: str) -> str:
    return hashlib.sha256(e164.encode()).hexdigest()


def wa_id_to_e164(wa_id: str) -> str:
    """WhatsApp sends numbers as digits without '+'."""
    return wa_id if wa_id.startswith("+") else "+" + wa_id
