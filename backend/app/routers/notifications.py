from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import settings
from ..database import get_connection, rows_to_dicts
from ..deps import get_current_business
from ..services.notifier import sms_balance

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/sms-balance")
def sms_balance_endpoint(business: dict = Depends(get_current_business)):
    balance = sms_balance(business)
    balance["topup_price_gbp"] = settings.SMS_TOPUP_PRICE_GBP
    balance["topup_credits"] = settings.SMS_TOPUP_CREDITS
    return balance


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

