from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import get_current_business, require_owner
from ..phone import validate_uk_phone
from ..schemas import SendTextRequest
from ..services.notifier import send_booking_confirmation_sms, send_sms

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def add_notification(
    conn,
    business_id: int,
    title: str,
    message: str = "",
    booking_id: int | None = None,
    type_: str = "booking",
) -> int:
    cur = conn.execute(
        "INSERT INTO notifications (business_id, type, title, message, booking_id) VALUES (?, ?, ?, ?, ?)",
        (business_id, type_, title, message, booking_id),
    )
    return cur.lastrowid


@router.get("")
def list_notifications(
    business: dict = Depends(get_current_business),
    since: int | None = Query(default=None),
    unread_only: bool = Query(default=False),
):
    """List notifications. Pass ?since=<id> to get only newer ones (for polling)."""
    query = "SELECT * FROM notifications WHERE business_id = ?"
    params: list = [business["id"]]
    if since is not None:
        query += " AND id > ?"
        params.append(since)
    if unread_only:
        query += " AND read = 0"
    query += " ORDER BY id DESC LIMIT 100"
    conn = get_connection()
    try:
        rows = rows_to_dicts(conn.execute(query, params).fetchall())
    finally:
        conn.close()
    return rows


@router.get("/unread-count")
def unread_count(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE business_id = ? AND read = 0",
            (business["id"],),
        ).fetchone()["c"]
    finally:
        conn.close()
    return {"count": count}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE notifications SET read = 1 WHERE id = ? AND business_id = ?",
            (notification_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE notifications SET read = 1 WHERE business_id = ? AND read = 0",
            (business["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/send-text")
def send_text(
    data: SendTextRequest,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    try:
        phone = validate_uk_phone(data.phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    """Send an SMS texsage to any phone number (owner only)."""
    result = send_sms(data.phone, data.message)
    return {"ok": True, **result}


@router.post("/send-booking-confirmation/{booking_id}")
def send_booking_confirmation(
    booking_id: int,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    """Send the customer a confirmation text for a booking (owner only)."""
    conn = get_connection()
    try:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE id = ? AND business_id = ?",
            (booking_id, business["id"]),
        ).fetchone()
    finally:
        conn.close()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    result = send_booking_confirmation_sms(row_to_dict(booking), business)
    return {"ok": True, **result}
