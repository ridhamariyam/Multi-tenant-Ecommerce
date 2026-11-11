from __future__ import annotations

import re

from app.core.config import get_settings

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(raw: str) -> str:
    settings = get_settings()
    value = (raw or "").strip()

    if value.count("+") > 1 or ("+" in value and not value.startswith("+")):
        raise ValueError("Not a valid phone number")

    digits = re.sub(r"\D", "", value)

    if not value.startswith("+"):
        if value.startswith("00"):
            digits = digits[2:]
        else:
            digits = digits.lstrip("0")
            if len(digits) <= settings.phone_national_number_length:
                digits = settings.phone_default_country_code + digits

    normalized = "+" + digits
    if not E164_PATTERN.match(normalized):
        raise ValueError("Not a valid phone number")

    return normalized
