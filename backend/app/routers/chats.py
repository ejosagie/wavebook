"""Customer <-> business owner chat.

Customers start a chat from the booking site widget (name + phone) and can
reconnect to the same conversation within 24 hours using the same phone
number. Owners reply from the WaveBook app.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import get_current_business
from ..routers.notifications import add_notification

router = APIRouter(tags=["chats"])

CHAT_REOPEN_HOURS = 24


def _get_business_by_slug(slug: str) -> dict | None:
    conn = get_connection()
    try:
        business = row_to_dict(conn.execute("SELECT * FROM businesses WHERE slug = ?", (slug,)).fetchone())
    finally:
        conn.close()
    return business


def _chat_messages(chat_id: int, since: int = 0) -> list[dict]:
    conn = get_connection()
    try:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT id, sender, body, created_at FROM chat_messages "
                "WHERE chat_id = ? AND id > ? ORDER BY id",
                (chat_id, since),
            ).fetchall()
        )
    finally:
        conn.close()
    return rows


def _get_chat_for_business(chat_id: int, business_id: int) -> dict:
    conn = get_connection()
    try:
        chat = row_to_dict(
            conn.execute(
                "SELECT * FROM chats WHERE id = ? AND business_id = ?", (chat_id, business_id)
            ).fetchone()
        )
    finally:
        conn.close()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


# ---- Customer-facing (public booking site) ----


@router.post("/t/{slug}/api/chat/start")
def chat_start(slug: str, payload: dict):
    """Start a chat, or reconnect to one from the last 24 hours with the same phone."""
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    name = (payload.get("name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not name or not phone:
        raise HTTPException(status_code=400, detail="Name and phone number are required")
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM chats WHERE business_id = ? AND customer_phone = ? "
            "AND last_message_at >= datetime('now', ?) ORDER BY id DESC LIMIT 1",
            (business["id"], phone, f"-{CHAT_REOPEN_HOURS} hours"),
        ).fetchone()
        if existing:
            chat = row_to_dict(existing)
        else:
            token = secrets.token_urlsafe(16)
            cur = conn.execute(
                "INSERT INTO chats (business_id, token, customer_name, customer_phone) VALUES (?, ?, ?, ?)",
                (business["id"], token, name, phone),
            )
            chat = row_to_dict(
                conn.execute("SELECT * FROM chats WHERE id = ?", (cur.lastrowid,)).fetchone()
            )
        conn.commit()
    finally:
        conn.close()
    return {
        "chat_id": chat["id"],
        "token": chat["token"],
        "customer_name": chat["customer_name"],
        "messages": _chat_messages(chat["id"]),
    }


@router.get("/t/{slug}/api/chat/{token}/messages")
def chat_poll(slug: str, token: str, since: int = Query(default=0)):
    """Poll for new messages (customer side)."""
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    conn = get_connection()
    try:
        chat = conn.execute(
            "SELECT * FROM chats WHERE business_id = ? AND token = ?", (business["id"], token)
        ).fetchone()
    finally:
        conn.close()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"messages": _chat_messages(chat["id"], since)}


@router.post("/t/{slug}/api/chat/{token}/messages")
def chat_customer_send(slug: str, token: str, payload: dict):
    """Send a message as the customer."""
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    conn = get_connection()
    try:
        chat = conn.execute(
            "SELECT * FROM chats WHERE business_id = ? AND token = ?", (business["id"], token)
        ).fetchone()
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        cur = conn.execute(
            "INSERT INTO chat_messages (chat_id, sender, body) VALUES (?, 'customer', ?)",
            (chat["id"], body),
        )
        conn.execute(
            "UPDATE chats SET last_message_at = datetime('now') WHERE id = ?", (chat["id"],)
        )
        add_notification(
            conn,
            business["id"],
            "New chat message",
            f"{chat['customer_name']}: {body[:120]}",
            type_="chat",
        )
        conn.commit()
        message = row_to_dict(
            conn.execute("SELECT id, sender, body, created_at FROM chat_messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    finally:
        conn.close()
    return message


# ---- Owner-facing (WaveBook app) ----


@router.get("/api/chats")
def list_chats(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        chats = rows_to_dicts(
            conn.execute(
                "SELECT * FROM chats WHERE business_id = ? ORDER BY last_message_at DESC",
                (business["id"],),
            ).fetchall()
        )
        for chat in chats:
            last = conn.execute(
                "SELECT sender, body, created_at FROM chat_messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
                (chat["id"],),
            ).fetchone()
            chat["last_message"] = last["body"] if last else ""
            chat["last_sender"] = last["sender"] if last else ""
            chat["last_message_at"] = last["created_at"] if last else chat["last_message_at"]
            unread = conn.execute(
                "SELECT COUNT(*) AS n FROM chat_messages WHERE chat_id = ? AND sender = 'customer' AND read = 0",
                (chat["id"],),
            ).fetchone()["n"]
            chat["unread"] = unread
    finally:
        conn.close()
    return chats


@router.get("/api/chats/unread-count")
def chats_unread_count(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM chat_messages m JOIN chats c ON c.id = m.chat_id "
            "WHERE c.business_id = ? AND m.sender = 'customer' AND m.read = 0",
            (business["id"],),
        ).fetchone()["n"]
    finally:
        conn.close()
    return {"count": count}


@router.get("/api/chats/{chat_id}/messages")
def owner_chat_messages(chat_id: int, business: dict = Depends(get_current_business)):
    chat = _get_chat_for_business(chat_id, business["id"])
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE chat_messages SET read = 1 WHERE chat_id = ? AND sender = 'customer' AND read = 0",
            (chat_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return {"chat": chat, "messages": _chat_messages(chat_id)}


@router.post("/api/chats/{chat_id}/messages")
def owner_chat_send(chat_id: int, payload: dict, business: dict = Depends(get_current_business)):
    _get_chat_for_business(chat_id, business["id"])
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO chat_messages (chat_id, sender, body) VALUES (?, 'owner', ?)",
            (chat_id, body),
        )
        conn.execute("UPDATE chats SET last_message_at = datetime('now') WHERE id = ?", (chat_id,))
        conn.commit()
        message = row_to_dict(
            conn.execute("SELECT id, sender, body, created_at FROM chat_messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    finally:
        conn.close()
    return message


@router.post("/api/chats/{chat_id}/read")
def mark_chat_read(chat_id: int, business: dict = Depends(get_current_business)):
    _get_chat_for_business(chat_id, business["id"])
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE chat_messages SET read = 1 WHERE chat_id = ? AND sender = 'customer' AND read = 0",
            (chat_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
