"""Stripe subscription renewal webhooks: invoice.paid, invoice.payment_failed, subscription.deleted."""

from datetime import date, datetime, timedelta

from app import database
from app.services import stripepay
from conftest import auth


def _activate(biz, monkeypatch, sub_id="sub_renew_1", tx_ref=None):
    """Insert an active subscription row as if checkout had completed."""
    tx_ref = tx_ref or f"WB-SUB-{biz['id']}-premium_monthly-abcd"
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET subscription_status = 'active', storefront_enabled = 1 WHERE id = ?",
            (biz["id"],),
        )
        conn.execute(
            "INSERT INTO subscriptions (business_id, stripe_subscription_id, tx_ref, status, plan, amount, currency) "
            "VALUES (?, ?, ?, 'active', 'premium_monthly', 19.99, 'GBP')",
            (biz["id"], sub_id, tx_ref),
        )
        conn.commit()
    finally:
        conn.close()


def _invoice(sub_id="sub_renew_1", period_end=None, metadata=None):
    period_end = period_end or int((datetime.now() + timedelta(days=30)).timestamp())
    return {
        "id": "in_1",
        "subscription": sub_id,
        "period_end": period_end,
        "subscription_details": {"metadata": metadata or {}},
    }


def _post(client, monkeypatch, event_type, obj):
    event = {"type": event_type, "data": {"object": obj}}
    monkeypatch.setattr(stripepay, "construct_webhook_event", lambda payload, sig: event)
    return client.post("/api/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})


def test_invoice_paid_renews_subscription(client, make_business, monkeypatch):
    biz = make_business("renew1", status="trial")
    _activate(biz, monkeypatch)
    res = _post(client, monkeypatch, "invoice.paid", _invoice(period_end=int((datetime.now() + timedelta(days=30)).timestamp())))
    assert res.status_code == 200, res.text
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "active"
    assert sub["auto_renew"] is True
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT current_period_end FROM subscriptions WHERE business_id = ?",
            (biz["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row["current_period_end"] == (date.today() + timedelta(days=30)).isoformat()


def test_invoice_paid_reactivates_past_due_business(client, make_business, monkeypatch):
    biz = make_business("renew2", status="past_due")
    _activate(biz, monkeypatch)
    conn = database.get_connection()
    try:
        conn.execute("UPDATE businesses SET subscription_status = 'past_due' WHERE id = ?", (biz["id"],))
        conn.commit()
    finally:
        conn.close()
    res = _post(client, monkeypatch, "invoice.paid", _invoice())
    assert res.status_code == 200, res.text
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "active"


def test_invoice_payment_failed_marks_past_due_and_notifies(client, make_business, monkeypatch, sent):
    biz = make_business("renew3", status="active")
    _activate(biz, monkeypatch)
    res = _post(client, monkeypatch, "invoice.payment_failed", _invoice())
    assert res.status_code == 200, res.text
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "past_due"
    conn = database.get_connection()
    try:
        note = conn.execute(
            "SELECT type, title FROM notifications WHERE business_id = ?", (biz["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert note is not None
    assert note["type"] == "subscription"
    assert "Payment failed" in note["title"]
    assert len([m for m in sent if m["to"] == biz["owner_email"]]) == 1


def test_subscription_deleted_cancels_business(client, make_business, monkeypatch):
    biz = make_business("renew4", status="active")
    _activate(biz, monkeypatch)
    res = _post(
        client,
        monkeypatch,
        "customer.subscription.deleted",
        {"id": "sub_renew_1", "metadata": {}},
    )
    assert res.status_code == 200, res.text
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "cancelled"


def test_unknown_subscription_webhook_is_ignored(client, make_business, monkeypatch):
    biz = make_business("renew5", status="trial")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET trial_ends_at = ? WHERE id = ?",
            ((date.today() + timedelta(days=7)).isoformat(), biz["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    res = _post(client, monkeypatch, "invoice.paid", _invoice(sub_id="sub_unknown"))
    assert res.status_code == 200, res.text
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "trial"
