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


def test_cancel_recurring_subscription(client, make_business, monkeypatch):
    biz = make_business("renew6", status="active")
    _activate(biz, monkeypatch)
    cancelled = {}

    def fake_cancel(sub_id):
        cancelled["sub_id"] = sub_id
        return {"id": sub_id, "cancel_at_period_end": True}

    monkeypatch.setattr(stripepay, "cancel_subscription", fake_cancel)
    res = client.post("/api/subscription/cancel", headers=auth(biz["owner_token"]))
    assert res.status_code == 200, res.text
    assert cancelled["sub_id"] == "sub_renew_1"
    assert res.json()["status"] == "cancelling"


def test_cancel_legacy_subscription_rejected(client, make_business, monkeypatch):
    biz = make_business("renew7", status="active")
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-legacy"
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO subscriptions (business_id, stripe_subscription_id, tx_ref, status, plan, amount, currency) "
            "VALUES (?, ?, ?, 'active', 'premium_monthly', 19.99, 'GBP')",
            (biz["id"], tx_ref, tx_ref),
        )
        conn.commit()
    finally:
        conn.close()
    res = client.post("/api/subscription/cancel", headers=auth(biz["owner_token"]))
    assert res.status_code == 400
    assert "No recurring subscription" in res.text


def test_cancel_without_subscription_rejected(client, make_business, monkeypatch):
    biz = make_business("renew8", status="trial")
    res = client.post("/api/subscription/cancel", headers=auth(biz["owner_token"]))
    assert res.status_code == 400


def test_portal_opens_for_active_subscription(client, make_business, monkeypatch):
    biz = make_business("renew9", status="active")
    _activate(biz, monkeypatch)
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE subscriptions SET stripe_customer_id = 'cus_test_1' WHERE business_id = ?",
            (biz["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(
        stripepay, "create_portal_session", lambda customer_id, return_url: "https://billing.stripe.test/p/session"
    )
    res = client.post("/api/subscription/portal", json={"email": biz["owner_email"]})
    assert res.status_code == 200, res.text
    assert res.json()["portal_url"] == "https://billing.stripe.test/p/session"


def test_portal_rejects_subscription_without_customer(client, make_business, monkeypatch):
    biz = make_business("renew10", status="active")
    _activate(biz, monkeypatch)
    monkeypatch.setattr(stripepay, "get_subscription_customer", lambda sub_id: "")
    res = client.post("/api/subscription/portal", json={"email": biz["owner_email"]})
    assert res.status_code == 400
    assert "No active subscription" in res.text


def test_portal_resolves_customer_from_stripe(client, make_business, monkeypatch):
    """Subscriptions activated before customer ids were stored are resolved from Stripe."""
    biz = make_business("renew15", status="active")
    _activate(biz, monkeypatch)
    monkeypatch.setattr(stripepay, "get_subscription_customer", lambda sub_id: "cus_backfilled")
    monkeypatch.setattr(
        stripepay, "create_portal_session", lambda customer_id, return_url: "https://billing.stripe.test/p/session"
    )
    res = client.post("/api/subscription/portal", json={"email": biz["owner_email"]})
    assert res.status_code == 200, res.text
    assert res.json()["portal_url"] == "https://billing.stripe.test/p/session"
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT stripe_customer_id FROM subscriptions WHERE business_id = ?", (biz["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row["stripe_customer_id"] == "cus_backfilled"


def test_portal_rejects_unknown_email(client, make_business, monkeypatch):
    biz = make_business("renew11", status="active")
    _activate(biz, monkeypatch)
    res = client.post("/api/subscription/portal", json={"email": "nobody@wavebook.com"})
    assert res.status_code == 404


def _portal_login(client, biz):
    res = client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": "ownerpass1"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    for k, v in res.cookies.items():
        client.cookies.set(k, v)


def test_portal_subscription_manage_redirects_to_stripe(client, make_business, monkeypatch):
    biz = make_business("renew12", status="active")
    _activate(biz, monkeypatch)
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE subscriptions SET stripe_customer_id = 'cus_test_2' WHERE business_id = ?",
            (biz["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    _portal_login(client, biz)
    monkeypatch.setattr(
        stripepay, "create_portal_session", lambda customer_id, return_url: "https://billing.stripe.test/p/session"
    )
    res = client.post("/portal/subscription", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "https://billing.stripe.test/p/session"


def test_portal_subscription_manage_without_customer(client, make_business, monkeypatch):
    biz = make_business("renew13", status="active")
    _activate(biz, monkeypatch)
    monkeypatch.setattr(stripepay, "get_subscription_customer", lambda sub_id: "")
    _portal_login(client, biz)
    res = client.post("/portal/subscription", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"].startswith("/portal?tab=account")
    assert "No%20active%20subscription" in res.headers["location"]


def test_portal_account_tab_shows_subscription(client, make_business, monkeypatch):
    biz = make_business("renew14", status="active")
    _activate(biz, monkeypatch)
    _portal_login(client, biz)
    res = client.get("/portal?tab=account")
    assert res.status_code == 200
    assert "Manage or Cancel Subscription" in res.text
    assert "premium_monthly" in res.text
