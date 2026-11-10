from app import database
from app.routers import web
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
    assert "Booking Submitted" in res.text
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
    assert "instructions by email or text" in res.text
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
    assert "disabled" in res.json()["detail"].lower()
