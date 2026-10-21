from app import database
from app.routers import web as web_router
from conftest import auth


def _open_slots(monkeypatch, slots=None):
    monkeypatch.setattr(web_router, "get_available_time_slots", lambda *a, **k: slots or ["10:00", "14:00", "16:00"])
    monkeypatch.setattr(web_router, "is_date_blocked", lambda *a, **k: False)


def _rename_service(business_id, name):
    conn = database.get_connection()
    try:
        conn.execute("UPDATE services SET name = ? WHERE business_id = ?", (name, business_id))
        conn.commit()
    finally:
        conn.close()


def test_assistant_empty_message_asks_for_input(client, make_business):
    biz = make_business("assistempty")
    res = client.post("/t/assistempty/api/assistant", json={"message": "  "})
    assert res.status_code == 200
    assert "Tell me what you'd like to book" in res.json()["reply"]


def test_assistant_asks_which_service_when_no_match(client, make_business, make_service):
    biz = make_business("assistask")
    make_service(biz["id"])
    res = client.post("/t/assistask/api/assistant", json={"message": "i want to book something"})
    assert res.status_code == 200
    data = res.json()
    assert data["reply"] == "I can help you book. Which service would you like?"
    assert len(data["services"]) == 1
    assert data["services"][0]["name"] == "Cut"


def test_assistant_returns_slots_for_matched_service(client, make_business, make_service, monkeypatch):
    _open_slots(monkeypatch)
    biz = make_business("assistslots")
    make_service(biz["id"])
    _rename_service(biz["id"], "Haircut")
    res = client.post("/t/assistslots/api/assistant", json={"message": "a haircut tomorrow"})
    assert res.status_code == 200
    data = res.json()
    assert data["service_id"] is not None
    assert len(data["slots"]) == 3
    assert data["slots"][0]["time"] == "10:00"
    assert "at" in data["slots"][0]["display"]


def test_assistant_filters_slots_by_time_preference(client, make_business, make_service, monkeypatch):
    _open_slots(monkeypatch)
    biz = make_business("assistfilter")
    make_service(biz["id"])
    _rename_service(biz["id"], "Massage")
    res = client.post("/t/assistfilter/api/assistant", json={"message": "massage tomorrow afternoon"})
    data = res.json()
    times = [s["time"] for s in data["slots"]]
    assert times == ["14:00", "16:00"]


def test_assistant_offers_next_available_day_when_no_slots(client, make_business, make_service, monkeypatch):
    monkeypatch.setattr(web_router, "get_available_time_slots", lambda *a, **k: [])
    monkeypatch.setattr(web_router, "is_date_blocked", lambda *a, **k: False)
    biz = make_business("assistnext")
    make_service(biz["id"])
    _rename_service(biz["id"], "Haircut")
    res = client.post("/t/assistnext/api/assistant", json={"message": "haircut tomorrow"})
    data = res.json()
    assert "couldn't find any available Haircut slots" in data["reply"]
    assert data["slots"] == []


def test_assistant_matches_partial_service_name(client, make_business, make_service, monkeypatch):
    _open_slots(monkeypatch)
    biz = make_business("assistpartial")
    make_service(biz["id"])
    _rename_service(biz["id"], "Men's Haircut")
    res = client.post("/t/assistpartial/api/assistant", json={"message": "i need a haircut tomorrow"})
    assert res.status_code == 200
    data = res.json()
    assert data["service_id"] is not None
    assert len(data["slots"]) == 3


def test_assistant_generic_booking_request_shows_menu(client, make_business, make_service, monkeypatch):
    """'book an appointment' without a service name must ask which service, not match one."""
    _open_slots(monkeypatch)
    biz = make_business("assistgeneric")
    make_service(biz["id"])
    _rename_service(biz["id"], "Men's Haircut")
    res = client.post(
        "/t/assistgeneric/api/assistant",
        json={"message": "I'd like to book an appointment"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("service_id") is None
    assert data["reply"] == "I can help you book. Which service would you like?"
    assert len(data["services"]) == 1
    assert data["services"][0]["name"] == "Men's Haircut"


def test_assistant_handles_business_with_no_services(client, make_business):
    biz = make_business("assistnone")
    res = client.post("/t/assistnone/api/assistant", json={"message": "a haircut tomorrow"})
    assert res.status_code == 200
    assert "hasn't added any services" in res.json()["reply"]


def test_assistant_unknown_business_returns_404(client):
    res = client.post("/t/does-not-exist/api/assistant", json={"message": "haircut"})
    assert res.status_code == 404
