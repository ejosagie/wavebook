import json

from app import database
from app.routers import web
from conftest import auth


PNG = b"\x89PNG\r\n\x1a\nfake"


def _open_slot(monkeypatch):
    monkeypatch.setattr(web, "get_available_time_slots", lambda *a, **k: ["10:00"])
    monkeypatch.setattr(web, "is_date_blocked", lambda *a, **k: False)


def _make_service_with_questions(client, token):
    res = client.post(
        "/api/services",
        json={
            "name": "Consultation",
            "description": "",
            "price": 30.0,
            "duration_minutes": 30,
            "questions": [
                {"id": "q1", "label": "Any allergies?", "type": "text", "required": True, "options": []},
                {"id": "q2", "label": "Preferred contact", "type": "choice", "required": False, "options": ["Email", "Phone"]},
            ],
        },
        headers=auth(token),
    )
    assert res.status_code == 201, res.text
    return res.json()


def _book(client, slug, service_id, answers=None):
    data = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "07123456789",
        "service_id": service_id,
        "date": "2099-01-15",
        "time": "10:00",
        "notes": "",
    }
    if answers:
        data.update(answers)
    return client.post(f"/t/{slug}/booking", data=data, follow_redirects=False)


def test_booking_collects_intake_answers(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("intakeco", plan="premium_monthly")
    svc = _make_service_with_questions(client, biz["owner_token"])
    res = _book(
        client,
        "intakeco",
        svc["id"],
        {"answer_q1": "Peanuts", "answer_q2": "Email"},
    )
    assert res.status_code == 200, res.text
    assert "Booking Submitted" in res.text
    conn = database.get_connection()
    try:
        booking = conn.execute(
            "SELECT intake_answers FROM bookings WHERE business_id = ?", (biz["id"],)
        ).fetchone()
    finally:
        conn.close()
    answers = json.loads(booking["intake_answers"])
    assert answers == {"q1": "Peanuts", "q2": "Email"}


def test_booking_rejects_missing_required_answer(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("intakereq", plan="premium_monthly")
    svc = _make_service_with_questions(client, biz["owner_token"])
    res = _book(client, "intakereq", svc["id"], {"answer_q2": "Email"})
    assert res.status_code == 400
    assert "allergies" in res.json()["detail"].lower()


def test_calendar_feed_requires_token_and_lists_confirmed(client, make_business, monkeypatch, tmp_path):
    _open_slot(monkeypatch)
    biz = make_business("calco", plan="premium_monthly")
    token = biz["owner_token"]
    svc = _make_service_with_questions(client, token)
    _book(client, "calco", svc["id"], {"answer_q1": "None"})
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE bookings SET status = 'confirmed' WHERE business_id = ?", (biz["id"],)
        )
        conn.commit()
    finally:
        conn.close()

    # No token set yet: feed is public
    res = client.get("/t/calco/calendar.ics")
    assert res.status_code == 200, res.text
    assert "BEGIN:VCALENDAR" in res.text
    assert "wavebook-" in res.text

    # Once a token exists, the feed requires it
    tok = client.post("/api/business/calendar-token", headers=auth(token)).json()["calendar_token"]
    assert client.get("/t/calco/calendar.ics").status_code == 403
    res = client.get(f"/t/calco/calendar.ics?token={tok}")
    assert res.status_code == 200
    assert "BEGIN:VEVENT" in res.text
