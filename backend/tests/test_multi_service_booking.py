from app import database
from app.config import settings
from app.routers import payments as payments_router
from app.routers import web
from app.services import flutterwave
from conftest import auth


def _open_slot(monkeypatch):
    monkeypatch.setattr(web, "get_available_time_slots", lambda *a, **k: ["10:00"])
    monkeypatch.setattr(web, "is_date_blocked", lambda *a, **k: False)


def _make_services(client, token, count=2):
    ids = []
    for i in range(count):
        res = client.post(
            "/api/services",
            json={
                "name": f"Service {i + 1}",
                "description": "",
                "price": 30.0 + i * 10,
                "duration_minutes": 30 + i * 15,
                "questions": [],
            },
            headers=auth(token),
        )
        assert res.status_code == 201, res.text
        ids.append(res.json()["id"])
    return ids


def _book(client, slug, service_ids, answers=None):
    data = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "07123456789",
        "service_id": service_ids,
        "date": "2099-01-15",
        "time": "10:00",
        "notes": "",
    }
    if answers:
        data.update(answers)
    return client.post(f"/t/{slug}/booking", data=data, follow_redirects=False)


def test_booking_with_multiple_services_stores_totals_and_items(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("multico", plan="premium_monthly", deposit=25.0)
    ids = _make_services(client, biz["owner_token"])  # 30/45 prices, 30/45 durations

    res = _book(client, "multico", ids)
    assert res.status_code == 200, res.text
    assert "Booking Received" in res.text
    assert "Service 1" in res.text and "Service 2" in res.text  # item list on the page
    assert "Deposit Due Now" in res.text

    conn = database.get_connection()
    try:
        booking = conn.execute("SELECT * FROM bookings WHERE business_id = ?", (biz["id"],)).fetchone()
        items = conn.execute(
            "SELECT * FROM booking_items WHERE booking_id = ? ORDER BY id", (booking["id"],)
        ).fetchall()
    finally:
        conn.close()

    assert booking["service_name"] == "Service 1 + Service 2"
    assert booking["service_price"] == 70.0  # 30 + 40
    assert booking["service_duration_minutes"] == 75  # 30 + 45
    assert len(items) == 2
    assert items[0]["service_name"] == "Service 1"
    assert items[0]["service_price"] == 30.0
    assert items[1]["service_name"] == "Service 2"
    assert items[1]["service_price"] == 40.0


def test_booking_deposit_capped_at_total_price(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("depco", plan="premium_monthly", deposit=100.0)
    ids = _make_services(client, biz["owner_token"])  # total 70

    res = _book(client, "depco", ids)
    assert res.status_code == 200, res.text
    assert "Deposit Due Now: £70.00" in res.text


def test_booking_requires_at_least_one_service(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("nosvc", plan="premium_monthly")
    res = _book(client, "nosvc", [])
    assert res.status_code == 422  # FastAPI requires the service_id field


def test_booking_rejects_unknown_service(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("badsvc", plan="premium_monthly")
    ids = _make_services(client, biz["owner_token"])
    res = _book(client, "badsvc", [ids[0], 999999])
    assert res.status_code == 400
    assert "invalid service" in res.json()["detail"].lower()


def test_slots_uses_combined_duration_for_multiple_services(client, make_business, monkeypatch, tmp_path):
    biz = make_business("slotco", plan="premium_monthly")
    ids = _make_services(client, biz["owner_token"])  # durations 30 + 45 = 75

    captured = {}

    def fake_slots(date, availability, confirmed, duration, buffer):
        captured["duration"] = duration
        return ["10:00"]

    monkeypatch.setattr(web, "get_available_time_slots", fake_slots)
    monkeypatch.setattr(web, "is_date_blocked", lambda *a, **k: False)

    res = client.get(f"/t/slotco/api/slots?date=2099-01-15&service_ids={ids[0]},{ids[1]}")
    assert res.status_code == 200
    assert captured["duration"] == 75

    res = client.get("/t/slotco/api/slots?date=2099-01-15")
    assert res.status_code == 200
    assert captured["duration"] == 60  # default when no services selected


def _disable_online_payments(business_id):
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET online_payments_enabled = 0 WHERE id = ?", (business_id,)
        )
        conn.commit()
    finally:
        conn.close()


def test_booking_completes_with_instructions_when_payments_off(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("offpay", plan="premium_monthly", deposit=25.0)
    _disable_online_payments(biz["id"])
    ids = _make_services(client, biz["owner_token"])

    res = _book(client, "offpay", ids)
    assert res.status_code == 200, res.text
    assert "Booking Submitted" in res.text
    assert "bank details below" in res.text
    assert "Pay Deposit" not in res.text  # no online payment step


def test_booking_page_shows_instructions_notice_when_payments_off(client, make_business, tmp_path):
    biz = make_business("offpage", plan="premium_monthly", deposit=25.0)
    _disable_online_payments(biz["id"])
    res = client.get("/t/offpage/booking")
    assert res.status_code == 200
    assert "instructions by email or text" in res.text
    assert "Minimum Deposit Required" not in res.text


def test_payment_init_blocked_when_payments_off(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("offinit", plan="premium_monthly", deposit=25.0)
    ids = _make_services(client, biz["owner_token"])
    res = _book(client, "offinit", ids)
    assert res.status_code == 200, res.text
    conn = database.get_connection()
    try:
        booking_id = conn.execute(
            "SELECT id FROM bookings WHERE business_id = ?", (biz["id"],)
        ).fetchone()["id"]
    finally:
        conn.close()
    _disable_online_payments(biz["id"])

    res = client.post("/api/payments/init", json={"booking_id": booking_id})
    assert res.status_code == 400


def _admin_cookie(client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-admin-pass")
    res = client.post(
        "/admin/login", data={"password": "test-admin-pass"}, follow_redirects=False
    )
    assert res.status_code == 303
    for k, v in res.cookies.items():
        client.cookies.set(k, v)
    return client.cookies


def test_admin_payment_mode_switches_all_businesses(client, make_business, monkeypatch, tmp_path):
    _admin_cookie(client, monkeypatch)
    make_business("paymode1", plan="premium_monthly")
    make_business("paymode2", plan="premium_monthly")

    # Default: automatic (Flutterwave) for all
    res = client.get("/admin")
    assert res.status_code == 200
    assert "Automatic (Flutterwave)" in res.text

    # Switch to manual for all businesses
    res = client.post("/admin/payment-mode", data={"mode": "manual"}, follow_redirects=False)
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        rows = conn.execute("SELECT online_payments_enabled FROM businesses").fetchall()
    finally:
        conn.close()
    assert all(r["online_payments_enabled"] == 0 for r in rows)

    res = client.get("/admin")
    assert "Manual (bank transfer)" in res.text

    # Switch back to automatic for all businesses
    res = client.post("/admin/payment-mode", data={"mode": "automatic"}, follow_redirects=False)
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        rows = conn.execute("SELECT online_payments_enabled FROM businesses").fetchall()
    finally:
        conn.close()
    assert all(r["online_payments_enabled"] == 1 for r in rows)


def test_customer_deposit_paid_notifies_owner(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("depnotify", plan="premium_monthly", deposit=25.0)
    _disable_online_payments(biz["id"])
    ids = _make_services(client, biz["owner_token"])
    res = _book(client, "depnotify", ids)
    assert res.status_code == 200, res.text
    assert "I've Paid the Deposit" in res.text

    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET contact_phone = '07123456789' WHERE id = ?", (biz["id"],)
        )
        conn.commit()
        booking_id = conn.execute(
            "SELECT id FROM bookings WHERE business_id = ?", (biz["id"],)
        ).fetchone()["id"]
    finally:
        conn.close()

    sms_calls = []
    monkeypatch.setattr(web, "send_business_sms", lambda *a, **k: sms_calls.append(a) or {})
    monkeypatch.setattr(web, "send_owner_deposit_paid_email", lambda *a, **k: {})

    res = client.post(f"/t/depnotify/booking/{booking_id}/deposit-paid")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert len(sms_calls) == 1

    conn = database.get_connection()
    try:
        row = conn.execute("SELECT deposit_paid FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    finally:
        conn.close()
    assert row["deposit_paid"] == 1

    # Idempotent: second call does not re-notify
    res = client.post(f"/t/depnotify/booking/{booking_id}/deposit-paid")
    assert res.status_code == 200
    assert res.json()["already"] is True
    assert len(sms_calls) == 1

    # Success page now shows the paid confirmation instead of the button
    res = client.get(f"/t/depnotify/booking/{booking_id}/paid")
    assert res.status_code == 200
    assert "I've Paid the Deposit" not in res.text


def test_owner_marks_booking_deposit_paid(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("depowner", plan="premium_monthly", deposit=25.0)
    ids = _make_services(client, biz["owner_token"])
    res = _book(client, "depowner", ids)
    assert res.status_code == 200, res.text

    conn = database.get_connection()
    try:
        booking_id = conn.execute(
            "SELECT id FROM bookings WHERE business_id = ?", (biz["id"],)
        ).fetchone()["id"]
    finally:
        conn.close()

    res = client.patch(
        f"/api/bookings/{booking_id}/deposit-paid", headers=auth(biz["owner_token"])
    )
    assert res.status_code == 200
    assert res.json()["deposit_paid"] == 1

    conn = database.get_connection()
    try:
        row = conn.execute("SELECT deposit_paid FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    finally:
        conn.close()
    assert row["deposit_paid"] == 1


def _new_booking_notification_count(business_id):
    conn = database.get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE business_id = ? AND title = 'New booking received'",
            (business_id,),
        ).fetchone()["c"]
    finally:
        conn.close()


def _set_contact_phone(business_id):
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET contact_phone = '07123456789' WHERE id = ?", (business_id,)
        )
        conn.commit()
    finally:
        conn.close()


def test_automatic_booking_owner_notified_only_after_payment(
    client, make_business, monkeypatch, tmp_path, sent
):
    _open_slot(monkeypatch)
    biz = make_business("autonotify", plan="premium_monthly", deposit=25.0)
    ids = _make_services(client, biz["owner_token"])

    sms_calls = []
    monkeypatch.setattr(web, "send_business_sms", lambda *a, **k: sms_calls.append(a) or {})
    monkeypatch.setattr(
        payments_router, "send_business_sms", lambda *a, **k: sms_calls.append(a) or {}
    )

    res = _book(client, "autonotify", ids)
    assert res.status_code == 200, res.text
    assert "Booking Received" in res.text
    assert "instructions by email or text" not in res.text  # manual text is manual-only

    conn = database.get_connection()
    try:
        booking_id = conn.execute(
            "SELECT id FROM bookings WHERE business_id = ?", (biz["id"],)
        ).fetchone()["id"]
    finally:
        conn.close()

    # Owner is NOT notified at booking time in automatic mode
    assert _new_booking_notification_count(biz["id"]) == 0
    assert sms_calls == []
    assert not [m for m in sent if m["to"] == "owner@autonotify.wavebook.com"]

    # After the Flutterwave payment succeeds, the owner is notified
    _set_contact_phone(biz["id"])
    monkeypatch.setattr(
        flutterwave,
        "verify_transaction",
        lambda transaction_id: {
            "status": "successful",
            "tx_ref": f"WB-BK-{booking_id}-abcd",
            "amount": 25.0,
            "id": "tx-deposit",
            "currency": "GBP",
        },
    )
    res = client.get(f"/api/payments/verify?tx_ref=WB-BK-{booking_id}-abcd&transaction_id=tx-deposit")
    assert res.status_code == 200, res.text

    assert _new_booking_notification_count(biz["id"]) == 1
    assert len(sms_calls) == 1
    owner_emails = [
        m for m in sent if m["to"] == "owner@autonotify.wavebook.com" and "New booking" in m["subject"]
    ]
    assert len(owner_emails) == 1

    # The booking is paid but still pending — it is only confirmed by the owner
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT status, payment_status FROM bookings WHERE id = ?", (booking_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["status"] == "pending"
    assert row["payment_status"] == "paid"
    # The customer has not been told the booking is confirmed yet
    assert not [
        m for m in sent if m["to"] == "ada@example.com" and "Booking confirmed" in m["subject"]
    ]

    # When the owner confirms the booking, the customer gets the confirmation
    res = client.patch(
        f"/api/bookings/{booking_id}/status",
        json={"status": "confirmed"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    customer_emails = [
        m for m in sent if m["to"] == "ada@example.com" and "Booking confirmed" in m["subject"]
    ]
    assert len(customer_emails) == 1


def test_manual_booking_notifies_owner_immediately(client, make_business, monkeypatch, tmp_path, sent):
    _open_slot(monkeypatch)
    biz = make_business("manualnotify", plan="premium_monthly", deposit=25.0)
    _disable_online_payments(biz["id"])
    _set_contact_phone(biz["id"])
    ids = _make_services(client, biz["owner_token"])

    sms_calls = []
    monkeypatch.setattr(web, "send_business_sms", lambda *a, **k: sms_calls.append(a) or {})

    res = _book(client, "manualnotify", ids)
    assert res.status_code == 200, res.text
    assert "Booking Submitted" in res.text
    assert "bank details below" in res.text

    assert _new_booking_notification_count(biz["id"]) == 1
    assert len(sms_calls) == 1
    owner_emails = [
        m for m in sent if m["to"] == "owner@manualnotify.wavebook.com" and "New booking" in m["subject"]
    ]
    assert len(owner_emails) == 1


def test_automatic_booking_without_deposit_notifies_owner_immediately(
    client, make_business, monkeypatch, tmp_path
):
    _open_slot(monkeypatch)
    biz = make_business("nodepauto", plan="premium_monthly", deposit=0.0)
    ids = _make_services(client, biz["owner_token"])

    res = _book(client, "nodepauto", ids)
    assert res.status_code == 200, res.text
    assert "No deposit required" in res.text
    assert _new_booking_notification_count(biz["id"]) == 1
