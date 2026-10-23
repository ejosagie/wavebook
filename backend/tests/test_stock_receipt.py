"""Tests for international payout details, product stock, and the post-visit receipt automation."""

from datetime import datetime, timedelta

from app import database
from app.main import _send_due_receipts
from app.routers import payments as payments_router
from app.services import flutterwave
from conftest import auth


# ---- International payout details ----


def test_portal_payments_saves_international_bank_details(client, make_business):
    biz = make_business("payoutus")
    res = client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": "ownerpass1"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    res = client.post(
        "/portal/payments",
        data={
            "currency": "USD",
            "deposit_amount": "25.00",
            "payout_country": "US",
            "payout_bank_name": "Chase Bank",
            "payout_account_name": "Jane Owner",
            "payout_account_number": "123456789",
            "payout_routing_number": "021000021",
            "payout_iban": "",
            "payout_swift": "",
            "payout_bank_address": "270 Park Ave, New York, NY 10017",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM businesses WHERE id = ?", (biz["id"],)).fetchone()
    finally:
        conn.close()
    assert row["payout_country"] == "US"
    assert row["payout_routing_number"] == "021000021"
    assert row["payout_bank_address"] == "270 Park Ave, New York, NY 10017"
    assert row["currency"] == "USD"


def test_business_api_accepts_payout_fields(client, make_business):
    biz = make_business("payoutca")
    res = client.patch(
        "/api/business",
        json={
            "payout_country": "CA",
            "payout_routing_number": "12345-010",
            "payout_iban": "CA1234567890",
            "payout_swift": "ROYALCAT2",
            "payout_bank_address": "1 King St W, Toronto, ON",
        },
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["payout_country"] == "CA"
    assert res.json()["payout_routing_number"] == "12345-010"
    assert res.json()["payout_swift"] == "ROYALCAT2"


# ---- Product stock ----


def _create_product(client, token, stock=None):
    body = {"name": "Candle", "description": "", "price": 5.0, "sort_order": 0}
    if stock is not None:
        body["stock"] = stock
    res = client.post("/api/products", json=body, headers=auth(token))
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_product_stock_is_saved_and_listed(client, make_business):
    biz = make_business("stockco", plan="premium_monthly")
    pid = _create_product(client, biz["owner_token"], stock=3)
    listed = client.get("/api/products", headers=auth(biz["owner_token"])).json()
    assert listed[0]["stock"] == 3


def test_storefront_checkout_decrements_stock(client, make_business, monkeypatch):
    calls = {}

    def fake_link(**kwargs):
        calls.update(kwargs)
        return "https://checkout.flutterwave.test/pay"

    monkeypatch.setattr(flutterwave, "create_payment_link", fake_link)
    biz = make_business("stockdec", plan="premium_monthly")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        conn.commit()
    finally:
        conn.close()
    pid = _create_product(client, biz["owner_token"], stock=5)
    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "stockdec",
            "customer_name": "Jane Customer",
            "customer_email": "jane@wavebook.com",
            "customer_phone": "07123456789",
            "customer_address": "1 High St",
            "customer_city": "London",
            "customer_postcode": "SW1A 1AA",
            "customer_country": "GB",
            "items": [{"product_id": pid, "quantity": 2}],
        },
    )
    assert res.status_code == 200, res.text
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT stock FROM products WHERE id = ?", (pid,)).fetchone()
    finally:
        conn.close()
    assert row["stock"] == 3


def test_storefront_checkout_rejects_overstock(client, make_business, monkeypatch):
    monkeypatch.setattr(
        flutterwave,
        "create_payment_link",
        lambda **kwargs: "https://checkout.flutterwave.test/pay",
    )
    biz = make_business("stockover", plan="premium_monthly")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        conn.commit()
    finally:
        conn.close()
    pid = _create_product(client, biz["owner_token"], stock=2)
    res = client.post(
        "/api/storefront/checkout",
        json={
            "slug": "stockover",
            "customer_name": "Jane Customer",
            "customer_email": "jane@wavebook.com",
            "customer_phone": "07123456789",
            "customer_address": "1 High St",
            "customer_city": "London",
            "customer_postcode": "SW1A 1AA",
            "customer_country": "GB",
            "items": [{"product_id": pid, "quantity": 3}],
        },
    )
    assert res.status_code == 400
    assert "left in stock" in res.json()["detail"]


def test_store_page_shows_stock_badges(client, make_business):
    biz = make_business("stockbadge", plan="premium_monthly")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        conn.execute(
            "INSERT INTO products (business_id, name, description, price, active, sort_order, stock) VALUES "
            "(?, 'Low Stock', '', 5.0, 1, 0, 3), (?, 'Gone', '', 5.0, 1, 1, 0), (?, 'Plenty', '', 5.0, 1, 2, 20)",
            (biz["id"], biz["id"], biz["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/t/stockbadge/store")
    assert res.status_code == 200
    assert "Only 3 left" in res.text
    assert "Out of stock" in res.text
    assert "In stock" in res.text


# ---- Post-visit receipt automation ----


def test_receipt_page_renders(client, make_business, make_booking):
    biz = make_business("receiptco")
    booking_id = make_booking(biz["id"], customer_email="jane@wavebook.com", status="confirmed")
    res = client.get(f"/t/receiptco/booking/{booking_id}/receipt")
    assert res.status_code == 200
    assert "Thank you" in res.text
    assert "Cut" in res.text
    assert "2030-06-01" in res.text


def test_receipt_sweep_emails_two_hours_after_visit(client, make_business, make_booking, sent):
    biz = make_business("sweepco")
    booking_id = make_booking(biz["id"], customer_email="jane@wavebook.com", status="confirmed")

    # Too early: appointment is in the future
    now = datetime(2030, 6, 1, 9, 0)  # booking at 10:00, 60 min
    assert _send_due_receipts(now) == 0
    assert not any(m["to"] == "jane@wavebook.com" for m in sent)

    # 2 hours after the 10:00-11:00 appointment ends (13:00)
    now = datetime(2030, 6, 1, 13, 0)
    assert _send_due_receipts(now) == 1
    receipts = [m for m in sent if m["to"] == "jane@wavebook.com"]
    assert len(receipts) == 1
    assert "receipt" in receipts[0]["subject"].lower()
    assert f"/booking/{booking_id}/receipt" in receipts[0]["body"]

    # Idempotent: running again does not resend
    assert _send_due_receipts(now) == 0


def test_receipt_sweep_skips_unconfirmed(client, make_business, make_booking, sent):
    biz = make_business("sweepskip")
    make_booking(biz["id"], customer_email="jane@wavebook.com", status="pending")
    now = datetime(2030, 6, 1, 13, 0)
    assert _send_due_receipts(now) == 0
    assert not any(m["to"] == "jane@wavebook.com" for m in sent)
