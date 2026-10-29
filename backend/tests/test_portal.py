"""Tests for the browser owner portal (/portal)."""

from datetime import datetime, timezone

import jwt as pyjwt

from app import database
from app.config import settings
from app.services.slots import get_availability_row


def _login(client, biz, password="ownerpass1"):
    return client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": password},
        follow_redirects=False,
    )


def test_portal_requires_login(client):
    res = client.get("/portal", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/portal/login"


def test_portal_login_page_renders(client):
    res = client.get("/portal/login")
    assert res.status_code == 200
    assert "Business Owner Login" in res.text


def test_portal_login_rejects_wrong_password(client, make_business):
    biz = make_business("portalbad")
    res = _login(client, biz, password="wrongpass1")
    assert res.status_code == 303
    assert "error" in res.headers["location"]


def test_portal_login_sets_cookie_and_redirects(client, make_business):
    biz = make_business("portalgood")
    res = _login(client, biz)
    assert res.status_code == 303
    assert res.headers["location"] == "/portal?msg=Welcome%20back"
    assert "wavebook_portal" in res.headers.get("set-cookie", "")


def test_portal_session_expires_after_12_hours(client, make_business):
    biz = make_business("portalsess")
    res = _login(client, biz)
    cookie = res.cookies.get("wavebook_portal")
    assert cookie
    payload = pyjwt.decode(cookie, options={"verify_signature": False})
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    remaining_hours = (exp - datetime.now(timezone.utc)).total_seconds() / 3600
    expected = settings.PORTAL_SESSION_MINUTES / 60
    assert expected - 1 <= remaining_hours <= expected + 1


def test_app_token_expires_after_30_days(client, make_business):
    biz = make_business("apptoken")
    res = client.post(
        "/api/auth/login",
        json={"email": biz["owner_email"], "password": "ownerpass1"},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    payload = pyjwt.decode(token, options={"verify_signature": False})
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    remaining_days = (exp - datetime.now(timezone.utc)).total_seconds() / 86400
    expected = settings.ACCESS_TOKEN_EXPIRE_MINUTES / 1440
    assert expected - 1 <= remaining_days <= expected + 1


def test_portal_dashboard_shows_business(client, make_business):
    biz = make_business("portaldash")
    _login(client, biz)
    res = client.get("/portal")
    assert res.status_code == 200
    assert biz["name"] in res.text
    assert "Calendar" in res.text
    assert "Staff" in res.text
    assert "Payments" in res.text


def test_portal_calendar_saves_working_days_and_blocked_dates(client, make_business):
    biz = make_business("portalcal")
    _login(client, biz)
    res = client.post(
        "/portal/calendar",
        data={
            "slot_interval": "60",
            "blocked_dates": "2026-12-25\n2026-12-26",
            "mon_enabled": "on",
            "mon_start": "10:00",
            "mon_end": "16:00",
            "tue_enabled": "",
            "tue_start": "09:00",
            "tue_end": "17:00",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "msg" in res.headers["location"]

    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM availability WHERE business_id = ?", (biz["id"],)
        ).fetchone()
    finally:
        conn.close()
    avail = get_availability_row(row)
    assert avail["slot_interval"] == 60
    assert avail["working_days"]["mon"] == {"enabled": True, "start": "10:00", "end": "16:00"}
    assert avail["working_days"]["tue"]["enabled"] is False
    assert avail["blocked_dates"] == ["2026-12-25", "2026-12-26"]


def test_portal_staff_invite(client, make_business, sent):
    biz = make_business("portalstaff", plan="premium_monthly")
    _login(client, biz)
    res = client.post(
        "/portal/staff",
        data={"full_name": "Sam Staff", "email": "sam@portalwavebook.com", "phone": "07123456789"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "msg" in res.headers["location"]
    assert any("sam@portalwavebook.com" in m["to"] for m in sent)

    conn = database.get_connection()
    try:
        row = conn.execute(
            """SELECT u.email FROM staff s JOIN users u ON u.id = s.user_id
               WHERE s.business_id = ?""",
            (biz["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row["email"] == "sam@portalwavebook.com"


def test_portal_payments_saves_currency_and_deposit(client, make_business):
    biz = make_business("portalpay")
    _login(client, biz)
    res = client.post(
        "/portal/payments",
        data={
            "currency": "USD",
            "deposit_amount": "35.50",
            "payout_bank_name": "Test Bank",
            "payout_account_name": "Owner",
            "payout_account_number": "12345678",
            "payout_sort_code": "12-34-56",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "msg" in res.headers["location"]

    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM businesses WHERE id = ?", (biz["id"],)).fetchone()
    finally:
        conn.close()
    assert row["currency"] == "USD"
    assert row["deposit_amount"] == 35.5
    assert row["payout_bank_name"] == "Test Bank"


def test_portal_customize_saves_website_fields(client, make_business):
    biz = make_business("portalweb")
    _login(client, biz)
    res = client.post(
        "/portal/customize",
        data={
            "name": "Blush Studio",
            "tagline": "Beauty made easy",
            "about_text": "We do great hair.",
            "rules": "Arrive early",
            "contact_phone": "07123456789",
            "contact_email": "hello@blush.test",
            "address": "1 High Street",
            "instagram": "@blush",
            "facebook": "",
            "tiktok": "",
            "opening_hours": "Mon-Fri 9-7",
            "theme_color": "#123456",
            "storefront_enabled": "on",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "msg" in res.headers["location"]

    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM businesses WHERE id = ?", (biz["id"],)).fetchone()
    finally:
        conn.close()
    assert row["name"] == "Blush Studio"
    assert row["tagline"] == "Beauty made easy"
    assert row["theme_color"] == "#123456"
    assert row["storefront_enabled"] == 1


def test_portal_account_changes_password(client, make_business):
    biz = make_business("portalacct")
    _login(client, biz)
    res = client.post(
        "/portal/account",
        data={"current_password": "ownerpass1", "new_password": "newpass123"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "msg" in res.headers["location"]

    # Old password no longer works, new one does
    res = _login(client, biz, password="ownerpass1")
    assert "error" in res.headers["location"]
    res = _login(client, biz, password="newpass123")
    assert res.status_code == 303
    assert "wavebook_portal" in res.headers.get("set-cookie", "")


def test_portal_logout_clears_cookie(client, make_business):
    biz = make_business("portallogout")
    _login(client, biz)
    res = client.post("/portal/logout", follow_redirects=False)
    assert res.status_code == 303
    assert "wavebook_portal" in res.headers.get("set-cookie", "")
    assert "Max-Age=0" in res.headers.get("set-cookie", "")


def _capture_reset_email(monkeypatch):
    """Monkeypatch the reset email sender and return the temp password."""
    captured = {}

    def fake_send(to, full_name, temp_password):
        captured["to"] = to
        captured["temp"] = temp_password
        return {"provider": "test", "status": "sent"}

    monkeypatch.setattr("app.routers.auth.send_password_reset_email", fake_send)
    return captured


def test_forgot_password_page_renders(client):
    res = client.get("/forgot-password")
    assert res.status_code == 200
    assert "Reset your password" in res.text


def test_forgot_password_sends_temp_password_and_forces_change(client, make_business, monkeypatch):
    biz = make_business("portalreset")
    captured = _capture_reset_email(monkeypatch)

    res = client.post(
        "/forgot-password", data={"email": biz["owner_email"]}, follow_redirects=False
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/forgot-password/sent"
    assert captured["to"] == biz["owner_email"]

    # Old password no longer works
    res = _login(client, biz, password="ownerpass1")
    assert "error" in res.headers["location"]

    # Temp password works but sends the user to change it
    res = client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": captured["temp"]},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/portal/change-password")

    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT must_change_password FROM users WHERE email = ?", (biz["owner_email"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["must_change_password"] == 1


def test_portal_change_password_clears_flag(client, make_business, monkeypatch):
    biz = make_business("portalreset2")
    captured = _capture_reset_email(monkeypatch)
    client.post("/forgot-password", data={"email": biz["owner_email"]})

    # Log in with the temporary password, then set a new one
    client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": captured["temp"]},
        follow_redirects=False,
    )
    res = client.post(
        "/portal/change-password",
        data={"current_password": captured["temp"], "new_password": "newpass123"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/portal?msg=Password%20updated"

    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT must_change_password FROM users WHERE email = ?", (biz["owner_email"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["must_change_password"] == 0

    # New password logs in normally
    res = _login(client, biz, password="newpass123")
    assert res.status_code == 303
    assert res.headers["location"] == "/portal?msg=Welcome%20back"


def test_api_forgot_password_and_login_flow(client, make_business, monkeypatch):
    biz = make_business("apireset")
    captured = _capture_reset_email(monkeypatch)

    res = client.post("/api/auth/forgot-password", json={"email": biz["owner_email"]})
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    # Login with the temp password reports must_change_password
    res = client.post(
        "/api/auth/login",
        json={"email": biz["owner_email"], "password": captured["temp"]},
    )
    assert res.status_code == 200
    assert res.json()["user"]["must_change_password"] == 1

    # Changing the password clears the flag
    token = res.json()["access_token"]
    res = client.post(
        "/api/auth/change-password",
        json={"current_password": captured["temp"], "new_password": "brandnew123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    res = client.post(
        "/api/auth/login",
        json={"email": biz["owner_email"], "password": "brandnew123"},
    )
    assert res.status_code == 200
    assert res.json()["user"]["must_change_password"] == 0


def test_support_page_links_to_password_reset(client):
    res = client.get("/support")
    assert res.status_code == 200
    assert "/forgot-password" in res.text
    assert "Email us from the address on your account" not in res.text
