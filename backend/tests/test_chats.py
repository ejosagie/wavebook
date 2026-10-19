from app.routers import bookings as bookings_router
from app.services import notifier
from conftest import auth


def _open_slot(monkeypatch):
    monkeypatch.setattr(bookings_router, "get_available_time_slots", lambda *a, **k: ["10:00"])
    monkeypatch.setattr(bookings_router, "is_date_blocked", lambda *a, **k: False)


# ---- Customer chat ----


def test_chat_start_creates_chat_and_reconnects(client, make_business):
    biz = make_business("chatco")
    res = client.post(
        "/t/chatco/api/chat/start",
        json={"name": "Jane Customer", "phone": "07123456789"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["chat_id"] == 1
    assert data["token"]
    assert data["messages"] == []

    # Same phone within 24h reconnects to the same chat
    res2 = client.post(
        "/t/chatco/api/chat/start",
        json={"name": "Jane Customer", "phone": "07123456789"},
    )
    assert res2.status_code == 200
    assert res2.json()["chat_id"] == data["chat_id"]


def test_chat_start_requires_name_and_phone(client, make_business):
    make_business("chatreq")
    res = client.post("/t/chatreq/api/chat/start", json={"name": "", "phone": ""})
    assert res.status_code == 400


def test_customer_sends_and_polls_messages(client, make_business):
    biz = make_business("chatmsg")
    start = client.post(
        "/t/chatmsg/api/chat/start",
        json={"name": "Jane", "phone": "07123456789"},
    ).json()
    token = start["token"]

    sent = client.post(
        f"/t/chatmsg/api/chat/{token}/messages",
        json={"body": "Hi, do you have availability on Friday?"},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["sender"] == "customer"

    poll = client.get(f"/t/chatmsg/api/chat/{token}/messages?since=0")
    assert poll.status_code == 200
    messages = poll.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["body"] == "Hi, do you have availability on Friday?"

    # Empty message rejected
    empty = client.post(f"/t/chatmsg/api/chat/{token}/messages", json={"body": "  "})
    assert empty.status_code == 400


def test_customer_chat_creates_owner_notification(client, make_business):
    biz = make_business("chatnotif")
    token = client.post(
        "/t/chatnotif/api/chat/start",
        json={"name": "Jane", "phone": "07123456789"},
    ).json()["token"]
    client.post(f"/t/chatnotif/api/chat/{token}/messages", json={"body": "Hello!"})
    res = client.get("/api/notifications", headers=auth(biz["owner_token"]))
    assert res.status_code == 200
    titles = [n["title"] for n in res.json()]
    assert "New chat message" in titles


# ---- Owner chat ----


def test_owner_lists_chats_replies_and_unread(client, make_business):
    biz = make_business("chatowner")
    token = client.post(
        "/t/chatowner/api/chat/start",
        json={"name": "Jane", "phone": "07123456789"},
    ).json()["token"]
    client.post(f"/t/chatowner/api/chat/{token}/messages", json={"body": "Hello there"})

    unread = client.get("/api/chats/unread-count", headers=auth(biz["owner_token"]))
    assert unread.json()["count"] == 1

    chats = client.get("/api/chats", headers=auth(biz["owner_token"]))
    assert chats.status_code == 200
    data = chats.json()
    assert len(data) == 1
    assert data[0]["customer_name"] == "Jane"
    assert data[0]["last_message"] == "Hello there"
    assert data[0]["unread"] == 1

    chat_id = data[0]["id"]
    thread = client.get(f"/api/chats/{chat_id}/messages", headers=auth(biz["owner_token"]))
    assert thread.status_code == 200
    assert len(thread.json()["messages"]) == 1

    reply = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"body": "Yes, Friday at 2pm works!"},
        headers=auth(biz["owner_token"]),
    )
    assert reply.status_code == 200
    assert reply.json()["sender"] == "owner"

    # Customer polls and sees the owner reply
    poll = client.get(f"/t/chatowner/api/chat/{token}/messages?since=1")
    assert poll.json()["messages"][0]["body"] == "Yes, Friday at 2pm works!"

    # Unread cleared after viewing
    unread2 = client.get("/api/chats/unread-count", headers=auth(biz["owner_token"]))
    assert unread2.json()["count"] == 0


def test_owner_cannot_access_other_business_chat(client, make_business):
    biz_a = make_business("chata")
    biz_b = make_business("chatb")
    token = client.post(
        "/t/chata/api/chat/start",
        json={"name": "Jane", "phone": "07123456789"},
    ).json()["token"]
    chats = client.get("/api/chats", headers=auth(biz_b["owner_token"])).json()
    assert chats == []
    res = client.get("/api/chats/1/messages", headers=auth(biz_b["owner_token"]))
    assert res.status_code == 404


# ---- Non-UK phone handling ----


def test_non_uk_customer_phone_accepted_at_booking(client, make_business, make_service, monkeypatch):
    _open_slot(monkeypatch)
    biz = make_business("nonukco")
    service_id = make_service(biz["id"])
    res = client.post(
        "/api/bookings",
        json={
            "customer_name": "Jane Customer",
            "customer_email": "jane@wavebook.com",
            "customer_phone": "+12025550123",
            "service_id": service_id,
            "date": "2030-06-01",
            "time": "10:00",
        },
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 201, res.text
    assert res.json()["customer_phone"] == "+12025550123"


def test_send_sms_skips_non_uk_number():
    result = notifier.send_sms("+12025550123", "hello")
    assert result["status"] == "skipped"
    assert result["reason"] == "non_uk_phone"


def test_send_sms_queues_uk_number(monkeypatch):
    monkeypatch.setattr(notifier.settings, "SMSWORKS_API_KEY", "")
    result = notifier.send_sms("07123456789", "hello")
    assert result["status"] == "queued"  # dev-mode log when no API key
    assert result["provider"] == "dev-log"
