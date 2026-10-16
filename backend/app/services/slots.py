from datetime import date, datetime, time, timedelta

from ..database import json_loads

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_LABELS = {
    "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
    "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
}

DEFAULT_WORKING_DAYS = {
    "mon": {"enabled": True, "start": "09:00", "end": "19:00"},
    "tue": {"enabled": True, "start": "09:00", "end": "19:00"},
    "wed": {"enabled": True, "start": "09:00", "end": "19:00"},
    "thu": {"enabled": True, "start": "09:00", "end": "19:00"},
    "fri": {"enabled": True, "start": "09:00", "end": "19:00"},
    "sat": {"enabled": True, "start": "09:00", "end": "18:00"},
    "sun": {"enabled": False, "start": "09:00", "end": "17:00"},
}


def get_availability_row(row: dict | None) -> dict:
    """Normalise an availability DB row into a full availability dict."""
    if row is None:
        return {
            "working_days": DEFAULT_WORKING_DAYS,
            "blocked_dates": [],
            "blocked_slots": {},
            "slot_interval": 30,
        }
    working = json_loads(row.get("working_days"), {})
    merged = dict(DEFAULT_WORKING_DAYS)
    merged.update(working or {})
    return {
        "working_days": merged,
        "blocked_dates": json_loads(row.get("blocked_dates"), []),
        "blocked_slots": json_loads(row.get("blocked_slots"), {}),
        "slot_interval": int(row.get("slot_interval") or 30),
    }


def get_day_key(date_str: str) -> str:
    return date.fromisoformat(date_str).strftime("%a").lower()


def is_date_blocked(date_str: str, availability: dict) -> bool:
    if date_str in availability["blocked_dates"]:
        return True
    day_key = get_day_key(date_str)
    day = availability["working_days"].get(day_key)
    if day and not day["enabled"]:
        return True
    if date_str < date.today().isoformat():
        return True
    return False


def get_available_time_slots(
    date_str: str,
    availability: dict,
    confirmed_bookings: list[dict],
    service_duration_minutes: int = 60,
    buffer_minutes: int = 30,
) -> list[str]:
    """Generate available time slots for a date, mirroring the legacy PHP prototype logic."""
    day_key = get_day_key(date_str)
    day = availability["working_days"].get(day_key)
    if not day or not day["enabled"]:
        return []
    if date_str in availability["blocked_dates"]:
        return []

    start = day["start"]
    end = day["end"]
    interval = max(5, int(availability["slot_interval"]))
    duration = max(1, int(service_duration_minutes))

    # Blocked ranges from confirmed bookings + buffer
    blocked_ranges = []
    for b in confirmed_bookings:
        b_start = datetime.combine(date.fromisoformat(date_str), time.fromisoformat(b["time"]))
        b_duration = int(b.get("service_duration_minutes") or 60)
        b_end = b_start + timedelta(minutes=b_duration + buffer_minutes)
        blocked_ranges.append((b_start, b_end))

    # Manually blocked slots
    for slot in availability["blocked_slots"].get(date_str, []):
        s_start = datetime.combine(date.fromisoformat(date_str), time.fromisoformat(slot))
        blocked_ranges.append((s_start, s_start + timedelta(minutes=duration)))

    start_dt = datetime.combine(date.fromisoformat(date_str), time.fromisoformat(start))
    end_dt = datetime.combine(date.fromisoformat(date_str), time.fromisoformat(end))

    slots = []
    current = start_dt
    while current < end_dt:
        slot_end = current + timedelta(minutes=duration)
        if slot_end > end_dt:
            current += timedelta(minutes=interval)
            continue

        overlaps = any(current < r_end and slot_end > r_start for r_start, r_end in blocked_ranges)
        if not overlaps:
            slots.append(current.strftime("%H:%M"))

        current += timedelta(minutes=interval)

    # Remove past times for today
    if date_str == date.today().isoformat():
        now = datetime.now()
        slots = [s for s in slots if datetime.combine(date.today(), time.fromisoformat(s)) >= now]

    return slots


def blocked_dates_json(availability: dict, months: int = 3) -> list[str]:
    """Explicitly blocked dates plus all dates of disabled weekdays."""
    blocked = list(availability["blocked_dates"])
    disabled_days = [
        k for k, v in availability["working_days"].items() if not v["enabled"]
    ]
    if disabled_days:
        today = date.today()
        end = today + timedelta(days=months * 31)
        current = today
        while current <= end:
            if current.strftime("%a").lower() in disabled_days:
                blocked.append(current.isoformat())
            current += timedelta(days=1)
    return sorted(set(blocked))
