from datetime import date, timedelta

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


def test_admin_finances_requires_login(client):
    res = client.get("/admin/finances")
    assert res.status_code == 401


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
