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
    assert "Subscription Revenue" in res.text
    assert "&pound;42.97" in res.text  # 9.99 + 19.99 + 12.99

    res = client.get("/admin/finances?from_date=2026-02-01&to_date=2026-02-28")
    assert res.status_code == 200
    assert "&pound;19.99" in res.text
    assert "&pound;42.97" not in res.text


def test_admin_finances_requires_login(client):
    res = client.get("/admin/finances")
    assert res.status_code == 401
