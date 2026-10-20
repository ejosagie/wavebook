"""Tests for the browser owner portal (/portal)."""

from app import database
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
