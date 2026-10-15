"""UK phone number normalisation and validation.

The SMS Works API expects destinations in international format
(e.g. 44777777777), so numbers entered as 07xxx are converted to 44xxx
at the point of entry and again before sending.
"""
import re


def normalise_uk_number(phone: str) -> str:
    """Convert a UK phone number to international format (e.g. 07xxx -> 447xxx)."""
    digits = re.sub(r"[^0-9+]", "", phone or "")
    if digits.startswith("+44"):
        return digits[1:]  # 44...
    if digits.startswith("44") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 11:
        return "44" + digits[1:]
    return digits


def validate_uk_phone(phone: str) -> str:
    """Validate and normalise a UK mobile number.

    Raises ValueError if the number is not a valid UK mobile number.
    """
    normalized = normalise_uk_number(phone)
    if not re.fullmatch(r"44\d{10}", normalized):
        raise ValueError("Enter a valid UK mobile number, e.g. 07123 456789")
    return normalized
