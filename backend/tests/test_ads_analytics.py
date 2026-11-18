"""Ads & Analytics: tenant visit tracking, booking source tagging, portal dashboard."""

from datetime import datetime, timedelta

from app import database
from app.routers import web
from conftest import auth


def _open_slot(monkeypatch):
    monkeypatch.setattr(web, "get_available_time_slots", lambda *a, **k: ["10:00"])
    monkeypatch.setattr(web, "is_date_blocked", lambda *a, **k: False)


def _make_service(client, token):
    res = client.post(
        "/api/services",
        json={"name": "Cut", "description": "", "price": 30.0, "duration_minutes": 30, "questions": []},
        headers=auth(token),
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _portal_login(client, biz):
    res = client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": "ownerpass1"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    for k, v in res.cookies.items():
        client.cookies.set(k, v)


def test_tenant_visit_records_ad_visit(client, make_business):
    biz = make_business("adco1")
    res = client.get("/t/adco1/?utm_source=metafeeds")
    assert res.status_code == 200
    assert res.cookies.get("wb_src") == "metafeeds"
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT source, page FROM ad_visits WHERE business_id = ?", (biz["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["source"] == "metafeeds"
    assert row["page"] == "home"


def test_tenant_visit_keeps_source_from_cookie(client, make_business):
    biz = make_business("adco2")
    client.get("/t/adco2/?utm_source=tiktokfeeds")
    client.get("/t/adco2/services")
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT source, page FROM ad_visits WHERE business_id = ? ORDER BY id", (biz["id"],)
        ).fetchall()
    finally:
        conn.close()
    assert [(r["source"], r["page"]) for r in rows] == [
        ("tiktokfeeds", "home"),
        ("tiktokfeeds", "services"),
    ]


def test_booking_tagged_with_ad_source(client, make_business, monkeypatch):
    _open_slot(monkeypatch)
    biz = make_business("adco3")
    svc = _make_service(client, biz["owner_token"])
    client.get("/t/adco3/?utm_source=googleads")
    res = client.post(
        "/t/adco3/booking",
        data={
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "phone": "07123456789",
            "service_id": [svc],
            "date": "2099-01-15",
            "time": "10:00",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert res.status_code == 200, res.text
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT source FROM bookings WHERE business_id = ?", (biz["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["source"] == "googleads"


def test_portal_analytics_tab_shows_links_and_stats(client, make_business):
    biz = make_business("adco4")
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO ad_visits (business_id, source, page) VALUES (?, 'metafeeds', 'home')", (biz["id"],)
        )
        conn.execute(
            "INSERT INTO ad_visits (business_id, source, page) VALUES (?, 'tiktokfeeds', 'booking')", (biz["id"],)
        )
        conn.execute(
            "INSERT INTO ad_visits (business_id, source, page) VALUES (?, '', 'home')", (biz["id"],)
        )
        conn.commit()
    finally:
        conn.close()
    _portal_login(client, biz)
    res = client.get("/portal?tab=analytics")
    assert res.status_code == 200
    assert "Ads &amp; Analytics" in res.text
    assert "utm_source=metafeeds" in res.text
    assert "https://adco4.wab.ad/?utm_source=metafeeds" in res.text
    assert "https://adco4.wab.ad/?utm_source=tiktokfeeds" in res.text
    assert "Meta (Instagram &amp; Facebook)" in res.text
    assert '<div class="num">3</div><div class="label">Visits</div>' in res.text
    assert '<div class="num">2</div><div class="label">Ad visits</div>' in res.text
    assert "Visits by platform" in res.text
    assert "Visits by page" in res.text
    assert "Services attempted to book" in res.text
    assert "Bookings by service" in res.text


def test_portal_analytics_date_range_filters(client, make_business):
    biz = make_business("adco5")
    old = (datetime.utcnow() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO ad_visits (business_id, source, page, visited_at) VALUES (?, 'metafeeds', 'home', ?)",
            (biz["id"], old),
        )
        conn.execute(
            "INSERT INTO ad_visits (business_id, source, page) VALUES (?, 'metafeeds', 'home')", (biz["id"],)
        )
        conn.commit()
    finally:
        conn.close()
    _portal_login(client, biz)
    res = client.get("/portal?tab=analytics&range=7d")
    assert res.status_code == 200
    assert '<div class="num">1</div><div class="label">Visits</div>' in res.text
    from_dt = (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d")
    to_dt = datetime.utcnow().strftime("%Y-%m-%d")
    res = client.get(f"/portal?tab=analytics&range=custom&from={from_dt}&to={to_dt}")
    assert res.status_code == 200
    assert '<div class="num">2</div><div class="label">Visits</div>' in res.text


def test_booking_page_visit_records_service_attempt(client, make_business, make_service):
    biz = make_business("adco6")
    svc = make_service(biz["id"])
    client.get(f"/t/adco6/booking?service={svc}&utm_source=metafeeds")
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT service_id, page, source FROM ad_visits WHERE business_id = ?", (biz["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["service_id"] == svc
    assert row["page"] == "booking"
    assert row["source"] == "metafeeds"


def test_portal_analytics_platform_filter(client, make_business, make_service):
    biz = make_business("adco7")
    svc = make_service(biz["id"])
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO ad_visits (business_id, source, page, service_id) VALUES (?, 'metafeeds', 'booking', ?)",
            (biz["id"], svc),
        )
        conn.execute(
            "INSERT INTO ad_visits (business_id, source, page) VALUES (?, 'tiktokfeeds', 'home')", (biz["id"],)
        )
        conn.commit()
    finally:
        conn.close()
    _portal_login(client, biz)
    res = client.get("/portal?tab=analytics&platform=metafeeds")
    assert res.status_code == 200
    assert '<div class="num">1</div><div class="label">Visits</div>' in res.text
    assert "Services attempted to book" in res.text
    assert "Cut" in res.text  # service name from the join
    assert "Visits by platform" not in res.text  # breakdown only for ALL
    res = client.get("/portal?tab=analytics&platform=all")
    assert res.status_code == 200
    assert '<div class="num">2</div><div class="label">Visits</div>' in res.text
    assert "Visits by platform" in res.text
