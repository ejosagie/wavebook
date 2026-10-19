"""Rule-based booking assistant.

Parses natural-language booking requests ("a haircut tomorrow afternoon")
into a service match, candidate dates and a time-of-day preference, then
surfaces real available slots from the business's availability engine.
No LLM calls — deterministic and free to run.
"""
import re
from datetime import date, timedelta

from .slots import get_available_time_slots, is_date_blocked

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
STOPWORDS = {"and", "the", "for", "with", "your", "our", "deluxe", "luxury", "classic", "signature", "full", "half"}


def _next_weekday(target: int, from_day: date) -> date:
    days_ahead = (target - from_day.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return from_day + timedelta(days=days_ahead)


def parse_date_request(text: str, today: date) -> list[date]:
    """Return candidate dates for a request, defaulting to today."""
    t = text.lower()
    if "today" in t:
        return [today]
    if "tomorrow" in t:
        return [today + timedelta(days=1)]
    m = re.search(
        r"next\s+(mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)",
        t,
    )
    if m:
        target = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].index(m.group(1)[:3])
        return [_next_weekday(target, today)]
    for i, day in enumerate(WEEKDAYS):
        if day in t:
            return [_next_weekday(i, today)]
    if "this week" in t:
        return [today + timedelta(days=i) for i in range(7)]
    if "next week" in t:
        start = today + timedelta(days=(7 - today.weekday()))
        return [start + timedelta(days=i) for i in range(7)]
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t)
    if m:
        return _specific_date(int(m.group(1)), m.group(2), today)
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?", t)
    if m:
        return _specific_date(int(m.group(2)), m.group(1), today)
    m = re.search(r"(\d{1,2})/(\d{1,2})", t)
    if m:
        try:
            return [date(today.year, int(m.group(2)), int(m.group(1)))]
        except ValueError:
            return []
    return [today]


def _specific_date(day_num: int, month_abbr: str, today: date) -> list[date]:
    month = MONTHS.index(month_abbr) + 1
    try:
        return [date(today.year, month, day_num)]
    except ValueError:
        return []


def parse_time_preference(text: str) -> tuple[int, int] | None:
    """Return an (start_hour, end_hour) window, or None for any time."""
    t = text.lower()
    if "morning" in t:
        return (9, 12)
    if "afternoon" in t:
        return (12, 17)
    if "evening" in t:
        return (17, 21)
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", t)
    if m:
        hour = int(m.group(1))
        if m.group(3) == "pm" and hour < 12:
            hour += 12
        if m.group(3) == "am" and hour == 12:
            hour = 0
        return (max(0, hour - 1), min(24, hour + 2))
    return None


def match_service(text: str, services: list[dict]) -> dict | None:
    """Best-effort service match against name and description keywords."""
    t = text.lower()
    best: dict | None = None
    best_score = 0
    for svc in services:
        name = (svc.get("name") or "").lower()
        desc = (svc.get("description") or "").lower()
        score = 0
        if name and name in t:
            score = 20 + len(name)
        elif desc and desc in t:
            score = 10
        words = [w for w in re.split(r"\W+", name) if len(w) > 2 and w not in STOPWORDS]
        hits = [w for w in words if w in t]
        if hits:
            # Shorter names win ties: a one-word name is a more precise match.
            score = max(score, 5 + len(hits) * 3 + (10 - len(words)))
        if score > best_score:
            best_score = score
            best = svc
    return best


def _hour(slot: str) -> int:
    return int(slot.split(":")[0])


def _display_slot(d: date, slot: str) -> str:
    h, m = slot.split(":")
    hour = int(h)
    ampm = "PM" if hour >= 12 else "AM"
    display_hour = hour % 12 or 12
    return f"{d.strftime('%a %d %b')} at {display_hour}:{m} {ampm}"


def build_assistant_response(
    message: str,
    services: list[dict],
    business: dict,
    availability: dict,
    today: date,
    slots_for,
) -> dict:
    """Build the assistant reply.

    slots_for(date_str, duration_minutes) -> list[str] of "HH:MM" slots.
    """
    service = match_service(message, services)
    if service is None:
        if not services:
            return {
                "reply": "This business hasn't added any services yet. Please check back later.",
                "services": [],
                "slots": [],
            }
        picks = [
            {
                "id": s["id"],
                "name": s["name"],
                "price": s.get("price"),
                "duration": s.get("duration_minutes"),
            }
            for s in services
        ]
        return {
            "reply": "I can help you book. Which service would you like?",
            "services": picks,
            "slots": [],
        }

    dates = parse_date_request(message, today)
    start_hour, end_hour = parse_time_preference(message) or (0, 24)
    duration = int(service.get("duration_minutes") or 60)
    slot_picks: list[dict] = []
    for d in dates:
        if is_date_blocked(d.isoformat(), availability):
            continue
        slots = slots_for(d.isoformat(), duration)
        for s in slots:
            if start_hour <= _hour(s) < end_hour:
                slot_picks.append({"date": d.isoformat(), "time": s, "display": _display_slot(d, s)})
                if len(slot_picks) >= 5:
                    break
        if len(slot_picks) >= 5:
            break

    if slot_picks:
        return {
            "reply": f"Great — {service['name']}. Here are some available times:",
            "service_id": service["id"],
            "slots": slot_picks,
        }

    # No slots on the requested dates — offer the next available day.
    for offset in range(1, 15):
        d = today + timedelta(days=offset)
        if is_date_blocked(d.isoformat(), availability):
            continue
        slots = slots_for(d.isoformat(), duration)
        if slots:
            s = slots[0]
            return {
                "reply": (
                    f"Sorry, there are no {service['name']} slots on those dates. "
                    f"The next available is {_display_slot(d, s)}."
                ),
                "service_id": service["id"],
                "slots": [{"date": d.isoformat(), "time": s, "display": _display_slot(d, s)}],
            }
    return {
        "reply": f"Sorry, I couldn't find any available {service['name']} slots in the next two weeks. Please try another date.",
        "service_id": service["id"],
        "slots": [],
    }
