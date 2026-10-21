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
            "customer_address": "10 High Street",
            "customer_city": "London",
            "customer_postcode": "SW1A 1AA",
            "customer_country": "GB",
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
            "customer_address": "10 High Street",
            "customer_city": "London",
            "customer_postcode": "SW1A 1AA",
            "customer_country": "GB",
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
            "customer_address": "10 High Street",
            "customer_city": "London",
            "customer_postcode": "SW1A 1AA",
            "customer_country": "GB",
            "items": [{"product_id": pid, "quantity": 1}],
        },
    )
    assert res.status_code == 200, res.text
    assert "#" not in calls[1]["description"], calls[1]["description"]


def _make_store_product(conn, business_id, price=10.0):
    return conn.execute(
        "INSERT INTO products (business_id, name, price, active) VALUES (?, 'Test Product', ?, 1)",
        (business_id, price),
    ).lastrowid


def test_storefront_local_shipping_fee(client, make_business, monkeypatch):
    """Customers in the store's country pay the local shipping fee."""
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("shiplocal")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1, shipping_fee_local = 3.5, "
            "shipping_fee_international = 12.0, store_country = 'GB' WHERE id = ?",
            (biz["id"],),
        )
        pid = _make_store_product(conn, biz["id"])
        conn.commit()
    finally:
        conn.close()

    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "shiplocal",
            "customer_name": "Local Buyer",
            "customer_phone": "07123456789",
            "customer_address": "10 High Street",
            "customer_city": "London",
            "customer_postcode": "SW1A 1AA",
            "customer_country": "GB",
            "items": [{"product_id": pid, "quantity": 2}],
        },
    )
    assert res.status_code == 200, res.text
    assert calls[0]["amount"] == 23.5, calls[0]["amount"]  # 20.0 products + 3.5 local shipping

    conn = database.get_connection()
    try:
        order = conn.execute("SELECT * FROM orders WHERE business_id = ?", (biz["id"],)).fetchone()
        assert order["shipping_fee"] == 3.5
        assert order["total"] == 23.5
        assert order["customer_address"] == "10 High Street"
        assert order["customer_city"] == "London"
        assert order["customer_postcode"] == "SW1A 1AA"
        assert order["customer_country"] == "GB"
    finally:
        conn.close()


def test_storefront_international_shipping_fee(client, make_business, monkeypatch):
    """Customers outside the store's country pay the international fee."""
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("shipintl")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1, shipping_fee_local = 3.5, "
            "shipping_fee_international = 12.0, store_country = 'GB' WHERE id = ?",
            (biz["id"],),
        )
        pid = _make_store_product(conn, biz["id"])
        conn.commit()
    finally:
        conn.close()

    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "shipintl",
            "customer_name": "Overseas Buyer",
            "customer_phone": "07123456789",
            "customer_address": "5 Rue de Paris",
            "customer_city": "Paris",
            "customer_postcode": "75001",
            "customer_country": "FR",
            "items": [{"product_id": pid, "quantity": 1}],
        },
    )
    assert res.status_code == 200, res.text
    assert calls[0]["amount"] == 22.0, calls[0]["amount"]  # 10.0 product + 12.0 international shipping

    conn = database.get_connection()
    try:
        order = conn.execute("SELECT * FROM orders WHERE business_id = ?", (biz["id"],)).fetchone()
        assert order["shipping_fee"] == 12.0
        assert order["total"] == 22.0
        assert order["customer_country"] == "FR"
    finally:
        conn.close()


def test_storefront_no_shipping_fee_when_unset(client, make_business, monkeypatch):
    """No shipping fee is charged when the business has not configured one."""
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("shipnone")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        pid = _make_store_product(conn, biz["id"])
        conn.commit()
    finally:
        conn.close()

    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "shipnone",
            "customer_name": "No Fee Buyer",
            "customer_phone": "07123456789",
            "customer_address": "1 Test Road",
            "customer_city": "New York",
            "customer_postcode": "10001",
            "customer_country": "US",
            "items": [{"product_id": pid, "quantity": 1}],
        },
    )
    assert res.status_code == 200, res.text
    assert calls[0]["amount"] == 10.0, calls[0]["amount"]


def test_storefront_checkout_requires_shipping_details(client, make_business, monkeypatch):
    """Checkout is rejected when required delivery fields are missing."""
    _capture_payment_link(monkeypatch)
    biz = make_business("shipreq")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        pid = _make_store_product(conn, biz["id"])
        conn.commit()
    finally:
        conn.close()

    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "shipreq",
            "customer_name": "Incomplete Buyer",
            "customer_phone": "07123456789",
            "items": [{"product_id": pid, "quantity": 1}],
        },
    )
    assert res.status_code == 400, res.text
    assert "address" in res.json()["detail"]
    assert "country" in res.json()["detail"]
