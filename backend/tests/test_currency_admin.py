from datetime import date, timedelta

import jwt as pyjwt

from app import database
from app.config import settings
from app.routers.web import _format_price
from conftest import auth


def _admin_cookie(client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-admin-pass")
    res = client.post(
        "/admin/login", data={"password": "test-admin-pass"}, follow_redirects=False
    )
    assert res.status_code == 303
    for k, v in res.cookies.items():
        client.cookies.set(k, v)
    return client.cookies


def test_admin_session_expires_after_12_hours(client, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-admin-pass")
    res = client.post(
        "/admin/login", data={"password": "test-admin-pass"}, follow_redirects=False
    )
    assert res.status_code == 303
    cookie = res.cookies.get("wavebook_admin")
    assert cookie
    payload = pyjwt.decode(cookie, options={"verify_signature": False})
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    remaining_hours = (exp - datetime.now(timezone.utc)).total_seconds() / 3600
    expected = settings.ADMIN_SESSION_MINUTES / 60
    assert expected - 1 <= remaining_hours <= expected + 1


def _add_subscription(business_id, amount, created_at, plan="basic_monthly"):
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO subscriptions (business_id, stripe_subscription_id, status, plan, amount, created_at) "
            "VALUES (?, ?, 'active', ?, ?, ?)",
            (business_id, f"tx-{business_id}-{created_at}", plan, amount, created_at),
        )
        conn.commit()
    finally:
        conn.close()


# ---- Currency formatting ----

def test_init_db_adds_currency_column_to_existing_businesses(client):
    """Existing databases (e.g. the VPS) must get the currency column on startup."""
    conn = database.get_connection()
    try:
        conn.execute("ALTER TABLE businesses DROP COLUMN currency")
        conn.commit()
    finally:
        conn.close()
    database.init_db()
    conn = database.get_connection()
    try:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(businesses)").fetchall()]
        assert "currency" in cols
    finally:
        conn.close()


def test_format_price_uses_currency_symbols():
    assert _format_price(12.5, "GBP") == "£12.50"
    assert _format_price(12.5, "USD") == "$12.50"
    assert _format_price(12.5, "CAD") == "C$12.50"
    assert _format_price(12.5, "EUR") == "€12.50"
    assert _format_price(12.5, "AUD") == "A$12.50"
    assert _format_price(12.5, "NZD") == "NZ$12.50"
    assert _format_price(12.5, "NGN") == "₦12.50"
    assert _format_price(12.5, "KES") == "KSh12.50"
    assert _format_price(12.5, "ZAR") == "R12.50"


def test_format_price_defaults_and_falls_back_safely():
    assert _format_price(9.99) == "£9.99"
    assert _format_price(9.99, None) == "£9.99"
    assert _format_price(9.99, "jpy") == "JPY 9.99"


# ---- Business currency selection ----

def test_create_business_with_currency(client):
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "cur@wavebook.com",
            "password": "password1",
            "full_name": "Cur Owner",
            "phone": "+14155550123",
        },
    )
    assert signup.status_code == 200, signup.text
    token = signup.json()["access_token"]
    res = client.post(
        "/api/business",
        json={"name": "Currency Co", "slug": "curco2", "currency": "USD"},
        headers=auth(token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["currency"] == "USD"


def test_create_business_rejects_unsupported_currency(client):
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "badcur@wavebook.com",
            "password": "password1",
            "full_name": "Bad Cur Owner",
            "phone": "+14155550123",
        },
    )
    token = signup.json()["access_token"]
    res = client.post(
        "/api/business",
        json={"name": "Bad Cur", "slug": "badcur2", "currency": "XXX"},
        headers=auth(token),
    )
    assert res.status_code == 422
    assert "Unsupported currency" in res.json()["detail"]


def test_update_business_currency(client, make_business):
    biz = make_business("updcur")
    res = client.patch(
        "/api/business",
        json={"currency": "CAD"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["currency"] == "CAD"


def test_signup_with_currency(client):
    res = client.post(
        "/api/auth/signup",
        json={
            "email": "us@wavebook.com",
            "password": "password1",
            "full_name": "US Owner",
            "phone": "+14155550123",
            "business_name": "US Studio",
            "slug": "usstudio",
            "currency": "USD",
        },
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    biz = client.get("/api/business", headers=auth(token)).json()
    assert biz["currency"] == "USD"


# ---- Reports ----

def test_financials_report_returns_currency(client, make_business, make_booking):
    biz = make_business("repcur")
    make_booking(biz["id"])
    res = client.get(
        "/api/reports/financials?period=year", headers=auth(biz["owner_token"])
    )
    assert res.status_code == 200, res.text
    assert res.json()["currency"] == "GBP"


# ---- Admin subscription revenue ----

def test_admin_finances_shows_subscription_revenue_with_date_range(
    client, make_business, monkeypatch
):
    cookie = _admin_cookie(client, monkeypatch)
    biz = make_business("subrev")
    _add_subscription(biz["id"], 9.99, "2026-01-05 10:00:00")
    _add_subscription(biz["id"], 19.99, "2026-02-10 10:00:00")
    _add_subscription(biz["id"], 12.99, "2026-03-15 10:00:00")

    res = client.get("/admin/finances")
    assert res.status_code == 200
    assert "WaveBook Platform Revenue" in res.text
    assert "&pound;42.97" in res.text  # 9.99 + 19.99 + 12.99

    res = client.get("/admin/finances?from_date=2026-02-01&to_date=2026-02-28")
    assert res.status_code == 200
    assert "&pound;19.99" in res.text
    assert "&pound;42.97" not in res.text


def test_admin_users_shows_registration_and_subscription_dates(
    client, make_business, monkeypatch
):
    _admin_cookie(client, monkeypatch)
    biz = make_business("userdates")
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO subscriptions (business_id, stripe_subscription_id, status, plan, amount, created_at) "
            "VALUES (?, 'tx-userdates', 'active', 'premium_yearly', 199.99, '2026-03-15 10:00:00')",
            (biz["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/users")
    assert res.status_code == 200
    assert "Registered" in res.text
    assert "Start" in res.text
    assert "End" in res.text
    assert "2026-03-15" in res.text  # subscription start
    assert "2027-03-15" in res.text  # yearly end = +12 months
    assert "WaveBook Premium" in res.text  # plan label


def test_admin_users_groups_staff_under_owner(client, make_business, monkeypatch):
    """Staff must appear nested under their business owner row, not as a
    separate row that looks like another paying user."""
    _admin_cookie(client, monkeypatch)
    biz = make_business("staffsub", plan="premium_monthly")
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, full_name, role, business_id) "
            "VALUES ('staff@staffsub.wavebook.com', 'x', 'Staff Test', 'staff', ?)",
            (biz["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/users")
    assert res.status_code == 200
    html = res.text
    # Owner row still shows the business subscription and a staff toggle.
    assert "WaveBook Premium" in html
    assert "1 staff" in html
    # The staff member is nested in an expandable sub-row, not a main row.
    assert 'class="staff-subrows"' in html
    assert "Staff Test" in html
    assert "staff — no subscription" in html
    subrow = html.split('class="staff-subrows"')[1].split("</table>")[0]
    assert "Staff Test" in subrow
    # The staff name must not appear in a main row (outside the sub-row).
    assert "Staff Test" not in html.split('class="staff-subrows"')[0]


def test_admin_users_demo_shows_real_subscription(client, make_business, monkeypatch):
    """The demo account is a paying customer and must show its plan normally."""
    _admin_cookie(client, monkeypatch)
    make_business("demo", plan="premium_monthly")
    res = client.get("/admin/users")
    assert res.status_code == 200
    assert "WaveBook Premium" in res.text
    assert "demo account" not in res.text


def test_admin_finances_requires_login(client):
    res = client.get("/admin/finances")
    assert res.status_code == 401


def test_admin_dashboard_paginates_businesses(client, monkeypatch):
    _admin_cookie(client, monkeypatch)
    conn = database.get_connection()
    try:
        for i in range(30):
            conn.execute(
                "INSERT INTO businesses (slug, name, trial_ends_at, currency, created_at) "
                "VALUES (?, ?, '2026-11-01', 'GBP', ?)",
                (f"pagbiz{i}", f"Paginated Biz {i}", f"2026-10-01 {i:02d}:00:00"),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin")
    assert res.status_code == 200
    assert "Page 1 of 2" in res.text
    assert "Paginated Biz 29" in res.text  # page 1 shows the 25 newest
    assert "Paginated Biz 0" not in res.text
    res = client.get("/admin?page=2")
    assert res.status_code == 200
    assert "Page 2 of 2" in res.text
    assert "Paginated Biz 0" in res.text


def test_admin_visits_paginates_recent_rows(client, monkeypatch):
    """Recent visits must render with client-side pagination so the page
    stays short even with many recorded visits."""
    _admin_cookie(client, monkeypatch)
    conn = database.get_connection()
    try:
        for i in range(45):
            conn.execute(
                "INSERT INTO page_visits (page, visited_at) VALUES (?, ?)",
                ("home", f"2026-10-22 06:00:{i:02d}"),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/visits")
    assert res.status_code == 200
    html = res.text
    assert html.count('class="visit-row"') == 45
    assert 'id="visits-pagination"' in html
    assert 'id="visits-count"' in html
    assert "ROWS_PER_PAGE" in html
    assert "renderVisits" in html


def test_admin_users_paginates(client, monkeypatch):
    _admin_cookie(client, monkeypatch)
    conn = database.get_connection()
    try:
        for i in range(30):
            conn.execute(
                "INSERT INTO users (email, password_hash, full_name, phone, role, created_at) "
                "VALUES (?, 'x', ?, '+441234567890', 'owner', ?)",
                (f"paguser{i}@wavebook.com", f"Paginated User {i}", f"2026-10-01 {i:02d}:00:00"),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/users")
    assert res.status_code == 200
    assert "Page 1 of 2" in res.text
    assert "Paginated User 29" in res.text  # page 1 shows the 25 newest
    assert "Paginated User 0" not in res.text
    res = client.get("/admin/users?page=2")
    assert res.status_code == 200
    assert "Page 2 of 2" in res.text
    assert "Paginated User 0" in res.text


def test_admin_settlements_paginates(client, make_business, monkeypatch):
    _admin_cookie(client, monkeypatch)
    biz = make_business("setpage")
    conn = database.get_connection()
    try:
        for i in range(30):
            conn.execute(
                "INSERT INTO settlements (business_id, amount, method, reference, created_at) "
                "VALUES (?, ?, 'bank_transfer', ?, ?)",
                (biz["id"], 10.0 + i, f"REF-{i:02d}", f"2026-10-01 {i:02d}:00:00"),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/settlements")
    assert res.status_code == 200
    assert "Page 1 of 2" in res.text
    assert "REF-29" in res.text  # page 1 shows the 25 newest
    assert "REF-00" not in res.text
    res = client.get("/admin/settlements?page=2")
    assert res.status_code == 200
    assert "Page 2 of 2" in res.text
    assert "REF-00" in res.text


def test_admin_finances_subscription_payments_paginate(
    client, make_business, monkeypatch
):
    _admin_cookie(client, monkeypatch)
    biz = make_business("subpage")
    for i in range(30):
        _add_subscription(biz["id"], 9.99 + i, f"2026-10-01 {i:02d}:00:00")
    res = client.get("/admin/finances")
    assert res.status_code == 200
    assert "Page 1 of 2" in res.text
    assert "&pound;38.99" in res.text  # page 1 shows the 25 newest (i=29)
    assert "&pound;9.99" not in res.text
    res = client.get("/admin/finances?spage=2")
    assert res.status_code == 200
    assert "Page 2 of 2" in res.text
    assert "&pound;9.99" in res.text  # page 2 shows the oldest (i=0)


def test_admin_feedback_paginates(client, make_business, monkeypatch):
    _admin_cookie(client, monkeypatch)
    biz = make_business("feedpage")
    conn = database.get_connection()
    try:
        for i in range(30):
            conn.execute(
                "INSERT INTO feedback (business_id, rating, comment, created_at) "
                "VALUES (?, 5, ?, ?)",
                (biz["id"], f"Feedback comment {i:02d}", f"2026-10-01 {i:02d}:00:00"),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/feedback")
    assert res.status_code == 200
    assert "Page 1 of 2" in res.text
    assert "Feedback comment 29" in res.text  # page 1 shows the 25 newest
    assert "Feedback comment 00" not in res.text
    res = client.get("/admin/feedback?page=2")
    assert res.status_code == 200
    assert "Page 2 of 2" in res.text
    assert "Feedback comment 00" in res.text


def test_admin_settlements_businesses_paginate(client, make_business, monkeypatch):
    _admin_cookie(client, monkeypatch)
    biz_ids = [make_business(f"oweb{i}")["id"] for i in range(30)]
    conn = database.get_connection()
    try:
        for i, bid in enumerate(biz_ids):
            conn.execute(
                "INSERT INTO payments (business_id, amount, kind, status) "
                "VALUES (?, ?, 'deposit', 'paid')",
                (bid, 100.0 + i),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/settlements")
    assert res.status_code == 200
    assert "Page 1 of 2" in res.text
    assert "Oweb29 Studio" in res.text  # highest collected first
    assert "Oweb0 Studio" not in res.text
    res = client.get("/admin/settlements?bpage=2")
    assert res.status_code == 200
    assert "Page 2 of 2" in res.text
    assert "Oweb0 Studio" in res.text


def test_admin_finances_businesses_paginate(client, make_business, monkeypatch):
    _admin_cookie(client, monkeypatch)
    biz_ids = [make_business(f"balb{i}")["id"] for i in range(30)]
    conn = database.get_connection()
    try:
        for i, bid in enumerate(biz_ids):
            conn.execute(
                "INSERT INTO payments (business_id, amount, kind, status, created_at) "
                "VALUES (?, ?, 'deposit', 'paid', ?)",
                (bid, 100.0 + i, f"2026-10-01 {i:02d}:00:00"),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/finances")
    assert res.status_code == 200
    assert "Page 1 of 2" in res.text
    assert "Balb29 Studio" in res.text  # highest collected first
    assert "Balb0 Studio" not in res.text
    res = client.get("/admin/finances?bpage=2")
    assert res.status_code == 200
    assert "Page 2 of 2" in res.text
    assert "Balb0 Studio" in res.text


def test_access_token_routes_to_login_but_does_not_auto_log_in(client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "test-admin-pass")
    monkeypatch.setattr(settings, "ADMIN_ACCESS_TOKEN", "waveanalz88102638")
    # Valid token: redirected to /admin, which shows the login page (no cookie set).
    res = client.get("/?access=waveanalz88102638", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/admin"
    assert client.get("/admin").status_code == 401  # still requires the password
    # Wrong token: landing page only.
    res = client.get("/?access=wrong", follow_redirects=False)
    assert res.status_code == 200
    assert "WaveBook" in res.text


def test_admin_finances_breaks_down_payment_kinds(client, make_business, monkeypatch):
    _admin_cookie(client, monkeypatch)
    biz = make_business("breakdown")
    conn = database.get_connection()
    try:
        for kind, amount in [("deposit", 30.0), ("order", 45.5), ("sms_topup", 5.0)]:
            conn.execute(
                "INSERT INTO payments (business_id, booking_id, stripe_payment_intent_id, amount, currency, kind, status, method) "
                "VALUES (?, NULL, ?, ?, 'GBP', ?, 'paid', 'card')",
                (biz["id"], f"tx-{kind}", amount, kind),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/finances")
    assert res.status_code == 200
    assert "&pound;30.00" in res.text  # deposits
    assert "&pound;45.50" in res.text  # shop sales
    assert "&pound;5.00" in res.text  # SMS top-up (platform revenue)
    assert "&pound;75.50" in res.text  # total collected for businesses (30 + 45.5)


def test_admin_settlements_page_shows_owed_and_history(client, make_business, monkeypatch):
    _admin_cookie(client, monkeypatch)
    biz = make_business("owedco")
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO payments (business_id, booking_id, stripe_payment_intent_id, amount, currency, kind, status, method) "
            "VALUES (?, NULL, 'tx-owed', 100.0, 'GBP', 'deposit', 'paid', 'card')",
            (biz["id"],),
        )
        conn.execute(
            "INSERT INTO settlements (business_id, amount, method, reference, notes) "
            "VALUES (?, 40.0, 'bank_transfer', 'WB-PAY-001', 'first payout')",
            (biz["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/admin/settlements")
    assert res.status_code == 200
    assert "&pound;60.00" in res.text  # owed = 100 - 40
    assert "WB-PAY-001" in res.text  # evidence reference in history


def test_admin_settlement_notifies_owner(client, make_business, monkeypatch, sent):
    _admin_cookie(client, monkeypatch)
    biz = make_business("notifyco")
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO payments (business_id, booking_id, stripe_payment_intent_id, amount, currency, kind, status, method) "
            "VALUES (?, NULL, 'tx-notify', 80.0, 'GBP', 'order', 'paid', 'card')",
            (biz["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    baseline = len(sent)
    res = client.post(
        "/admin/settlements",
        data={
            "business_id": str(biz["id"]),
            "amount": "80.00",
            "method": "paypal",
            "reference": "PP-REF-9",
            "notes": "weekly payout",
            "notify": "true",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM notifications WHERE business_id = ? AND type = 'settlement'",
            (biz["id"],),
        ).fetchone()
        assert row is not None
        assert "80.00" in row["message"]
        assert "PP-REF-9" in row["message"]
    finally:
        conn.close()
    assert len(sent) == baseline + 1
    assert sent[-1]["to"] == biz["owner_email"]
    assert "payment settled" in sent[-1]["subject"].lower()


def test_admin_settlement_without_notify_skips_owner(client, make_business, monkeypatch, sent):
    _admin_cookie(client, monkeypatch)
    biz = make_business("quietco")
    baseline = len(sent)
    res = client.post(
        "/admin/settlements",
        data={"business_id": str(biz["id"]), "amount": "10.00", "method": "cash"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert len(sent) == baseline  # no email when notify is unchecked
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM notifications WHERE business_id = ? AND type = 'settlement'",
            (biz["id"],),
        ).fetchone()
        assert row is None
    finally:
        conn.close()
