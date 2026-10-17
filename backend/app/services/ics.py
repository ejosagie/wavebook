"""iCalendar (.ics) export so bookings can be added to iOS/Google calendars."""
from datetime import datetime


def _escape(value: str) -> str:
    """Escape ICS text-field characters."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold long ICS lines at 75 octets per the spec."""
    if len(line) <= 75:
        return line
    return line[:75] + "\r\n " + _fold(line[75:])


def build_booking_ics(booking: dict, business: dict) -> str:
    """Build an .ics calendar file for a single booking.

    Times are emitted as floating local times (no timezone suffix) so the
    calendar app places the event at the business's local time.
    """
    start = datetime.fromisoformat(f"{booking['date']}T{booking['time']}")
    duration = int(booking.get("service_duration_minutes") or 60)
    end = start.replace(minute=start.minute + duration)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    summary = f"{booking.get('service_name', 'Booking')} - {booking.get('customer_name', '')}"
    description = (
        f"Booking reference: {booking.get('reference', '')}\n"
        f"Business: {business.get('name', '')}\n"
        f"Customer: {booking.get('customer_name', '')}\n"
        f"Phone: {booking.get('customer_phone', '')}\n"
        f"Email: {booking.get('customer_email', '')}"
    )
    if booking.get("notes"):
        description += f"\nNotes: {booking['notes']}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WaveBook//WaveBook//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:wavebook-{booking['id']}@getwavebook.com",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
