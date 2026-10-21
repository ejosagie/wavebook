"""Regression tests: booking deposits and storefront orders must use the
business's configured currency, not the global Flutterwave default (GBP)."""

from app import database
from app.services import flutterwave


def _capture_payment_link(monkeypatch):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return "https://checkout.flutterwave.test/pay/abc"

    monkeypatch.setattr(flutterwave, "create_payment_link", fake_create)
    return calls


def test_booking_deposit_uses_business_currency(client, make_business, make_booking, monkeypatch):
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("curbk", currency="USD")
    booking_id = make_booking(biz["id"], service_price=50.0)

    res = client.post("/api/payments/init", json={"booking_id": booking_id})

    assert res.status_code == 200, res.text
    assert res.json()["currency"] == "USD"
    assert calls[0]["currency"] == "USD"
    assert calls[0]["amount"] == 20.0  # capped at configured deposit


def test_booking_deposit_without_currency_setting_defaults_to_gbp(client, make_business, make_booking, monkeypatch):
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("curbk2")  # default currency GBP
    booking_id = make_booking(biz["id"], service_price=50.0)

    res = client.post("/api/payments/init", json={"booking_id": booking_id})

    assert res.status_code == 200, res.text
    assert res.json()["currency"] == "GBP"
    assert calls[0]["currency"] == "GBP"


def test_store_checkout_uses_business_currency(client, make_business, monkeypatch):
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("curstore", currency="EUR")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        pid = conn.execute(
            "INSERT INTO products (business_id, name, price, active) VALUES (?, 'Lipstick', 25.5, 1)",
            (biz["id"],),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()

    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "curstore",
            "customer_name": "Jane Customer",
            "customer_email": "jane@wavebook.com",
            "customer_phone": "07123456789",
            "items": [{"product_id": pid, "quantity": 2}],
        },
    )

    assert res.status_code == 200, res.text
    assert res.json()["currency"] == "EUR"
    assert calls[0]["currency"] == "EUR"
    assert calls[0]["amount"] == 51.0


def test_store_checkout_defaults_to_gbp_when_business_has_no_currency(client, make_business, monkeypatch):
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("curstore2")  # default currency GBP
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        pid = conn.execute(
            "INSERT INTO products (business_id, name, price, active) VALUES (?, 'Lipstick', 10.0, 1)",
            (biz["id"],),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()

    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "curstore2",
            "customer_name": "Jane Customer",
            "customer_email": "jane@wavebook.com",
            "customer_phone": "07123456789",
            "items": [{"product_id": pid, "quantity": 1}],
        },
    )

    assert res.status_code == 200, res.text
    assert res.json()["currency"] == "GBP"
    assert calls[0]["currency"] == "GBP"


def test_flutterwave_descriptions_never_contain_hash(client, make_business, make_booking, monkeypatch):
    """Regression: a '#' in the payment description triggers Cloudflare's WAF
    on api.flutterwave.com, returning 403 and breaking checkout. Descriptions
    must stay free of '#'."""
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("hashbk")
    booking_id = make_booking(biz["id"], service_price=50.0)

    res = client.post("/api/payments/init", json={"booking_id": booking_id})
    assert res.status_code == 200, res.text
    assert "#" not in calls[0]["description"], calls[0]["description"]

    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        pid = conn.execute(
            "INSERT INTO products (business_id, name, price, active) VALUES (?, 'Lipstick', 10.0, 1)",
            (biz["id"],),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()

    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "hashbk",
            "customer_name": "Jane Customer",
            "customer_email": "jane@wavebook.com",
            "customer_phone": "07123456789",
            "items": [{"product_id": pid, "quantity": 1}],
        },
    )
    assert res.status_code == 200, res.text
    assert "#" not in calls[1]["description"], calls[1]["description"]
