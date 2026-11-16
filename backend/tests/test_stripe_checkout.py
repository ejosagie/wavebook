"""Stripe Checkout flows: session creation, session-id verification, and webhooks."""

import json

import stripe

from app import database
from app.config import settings
from app.services import stripepay
from conftest import auth


def _session(*, tx_ref, amount_pence=2000, currency="gbp", session_id="cs_test_123", status="paid"):
    return {
        "id": session_id,
        "payment_status": status,
        "amount_total": amount_pence,
        "currency": currency,
        "metadata": {"tx_ref": tx_ref, "type": tx_ref.split("-")[1].lower()},
    }


def _order(biz, status="pending"):
    conn = database.get_connection()
    try:
        order_id = conn.execute(
            "INSERT INTO orders (business_id, customer_name, customer_email, customer_phone, items, total, status) "
            "VALUES (?, 'Jane Customer', 'jane@wavebook.com', '07123456789', ?, 25.0, ?)",
            (biz["id"], json.dumps([{"name": "Shampoo", "price": 12.5, "quantity": 2}]), status),
        ).lastrowid
        conn.commit()
        return order_id
    finally:
        conn.close()


def _payment_rows(order_id=None, booking_id=None):
    conn = database.get_connection()
    try:
        sql = "SELECT * FROM payments WHERE 1=1"
        args = []
        if order_id is not None:
            sql += " AND booking_id IS NULL"
        if booking_id is not None:
            sql += " AND booking_id = ?"
            args.append(booking_id)
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


# ---- Session creation ----

def test_create_checkout_session_builds_payload(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "rk_test_123")
    captured = {}

    class FakeSession(dict):
        pass

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeSession({"url": "https://checkout.stripe.test/c/pay"})

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(fake_create))
    url = stripepay.create_checkout_session(
        tx_ref="WB-BK-1-abcd",
        amount=20.0,
        currency="GBP",
        success_url="https://getwavebook.com/pay/verify?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://getwavebook.com/t/demo/booking/1/paid",
        customer_email="jane@wavebook.com",
        metadata={"booking_id": "1", "type": "booking_deposit"},
        title="WaveBook Deposit",
        description="Cut deposit for Demo Studio",
    )
    assert url == "https://checkout.stripe.test/c/pay"
    assert captured["mode"] == "payment"
    assert captured["line_items"][0]["price_data"]["unit_amount"] == 2000
    assert captured["line_items"][0]["price_data"]["currency"] == "gbp"
    assert captured["metadata"]["tx_ref"] == "WB-BK-1-abcd"
    assert captured["customer_email"] == "jane@wavebook.com"
    assert captured["success_url"].endswith("{CHECKOUT_SESSION_ID}")


def test_create_checkout_session_503_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    try:
        stripepay.create_checkout_session(
            tx_ref="WB-BK-1", amount=10, currency="GBP",
            success_url="https://x", cancel_url="https://x",
            customer_email="", metadata={}, title="t", description="d",
        )
        assert False, "expected HTTPException"
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "status_code", None) == 503


def test_session_to_data_normalizes():
    data = stripepay.session_to_data(_session(tx_ref="WB-ORD-7-abcd", amount_pence=2500))
    assert data["status"] == "successful"
    assert data["tx_ref"] == "WB-ORD-7-abcd"
    assert data["amount"] == 25.0
    assert data["currency"] == "GBP"
    assert data["id"] == "cs_test_123"


# ---- Session-id verification ----

def test_verify_with_session_id_marks_booking_paid(client, make_business, make_booking, monkeypatch, sent):
    biz = make_business("stripebk")
    booking_id = make_booking(biz["id"], customer_email="jane@wavebook.com", status="pending", service_price=50.0)
    tx_ref = f"WB-BK-{booking_id}-abcd"
    monkeypatch.setattr(
        stripepay, "retrieve_checkout_session", lambda sid: _session(tx_ref=tx_ref, amount_pence=2000)
    )
    res = client.get(f"/api/payments/verify?session_id=cs_test_123")
    assert res.status_code == 200, res.text
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT payment_status FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    finally:
        conn.close()
    assert row["payment_status"] == "paid"
    assert len(_payment_rows(booking_id=booking_id)) == 1


def test_verify_with_unpaid_session_rejected(client, make_business, make_booking, monkeypatch):
    biz = make_business("stripeunpaid")
    booking_id = make_booking(biz["id"], status="pending", service_price=50.0)
    tx_ref = f"WB-BK-{booking_id}-abcd"
    monkeypatch.setattr(
        stripepay, "retrieve_checkout_session", lambda sid: _session(tx_ref=tx_ref, status="unpaid")
    )
    res = client.get(f"/api/payments/verify?session_id=cs_test_123")
    assert res.status_code == 400


# ---- Webhook ----

def test_webhook_applies_order_payment(client, make_business, monkeypatch, sent):
    biz = make_business("stripehook")
    order_id = _order(biz)
    tx_ref = f"WB-ORD-{order_id}-abcd"
    event = {
        "type": "checkout.session.completed",
        "data": {"object": _session(tx_ref=tx_ref, amount_pence=2500)},
    }
    monkeypatch.setattr(stripepay, "construct_webhook_event", lambda payload, sig: event)
    res = client.post("/api/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
    assert res.status_code == 200, res.text
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    finally:
        conn.close()
    assert row["status"] == "paid"
    assert len(_payment_rows()) == 1
    # The customer gets the paid-order email once
    assert len([m for m in sent if m["to"] == "jane@wavebook.com"]) == 1


def test_webhook_is_idempotent(client, make_business, monkeypatch, sent):
    biz = make_business("stripehook2")
    order_id = _order(biz)
    tx_ref = f"WB-ORD-{order_id}-abcd"
    event = {
        "type": "checkout.session.completed",
        "data": {"object": _session(tx_ref=tx_ref, amount_pence=2500)},
    }
    monkeypatch.setattr(stripepay, "construct_webhook_event", lambda payload, sig: event)
    for _ in range(2):
        res = client.post("/api/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert res.status_code == 200
    assert len(_payment_rows()) == 1
    assert len([m for m in sent if m["to"] == "jane@wavebook.com"]) == 1


def test_webhook_activates_subscription(client, make_business, monkeypatch):
    biz = make_business("stripehsub", status="trial")
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-abcd"
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": _session(tx_ref=tx_ref, amount_pence=1999)
            | {"metadata": {"tx_ref": tx_ref, "plan": "premium_monthly", "currency": "GBP"}}
        },
    }
    monkeypatch.setattr(stripepay, "construct_webhook_event", lambda payload, sig: event)
    res = client.post("/api/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
    assert res.status_code == 200, res.text
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "active"
    assert sub["plan"] == "premium_monthly"


def test_webhook_requires_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    res = client.post("/api/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
    assert res.status_code == 503
