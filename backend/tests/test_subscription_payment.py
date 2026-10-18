from datetime import date, timedelta

from app import database
from app.services import flutterwave
from conftest import auth


def _running_trial(biz):
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET trial_ends_at = ? WHERE id = ?",
            ((date.today() + timedelta(days=7)).isoformat(), biz["id"]),
        )
        conn.commit()
    finally:
        conn.close()


def _capture_payment_link(monkeypatch):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return "https://checkout.flutterwave.test/pay/abc"

    monkeypatch.setattr(flutterwave, "create_payment_link", fake_create)
    return calls


def _verify_as(monkeypatch, *, status="successful", amount=19.99, plan="premium_monthly", tx_ref=None):
    def fake_verify(transaction_id):
        return {
            "id": transaction_id,
            "status": status,
            "tx_ref": tx_ref,
            "amount": amount,
            "currency": "GBP",
            "meta": {"plan": plan},
        }

    monkeypatch.setattr(flutterwave, "verify_transaction", fake_verify)


def _subscription_rows(business_id):
    conn = database.get_connection()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT stripe_subscription_id, plan, amount, status FROM subscriptions WHERE business_id = ?",
                (business_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


def test_checkout_creates_payment_link_for_chosen_plan(client, make_business, monkeypatch):
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("payco1", status="trial")
    res = client.post(
        "/api/subscription/checkout",
        json={"plan": "premium_quarterly"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["payment_link"] == "https://checkout.flutterwave.test/pay/abc"
    call = calls[-1]
    assert call["amount"] == 56.99
    assert call["currency"] == "GBP"
    assert call["customer_email"] == biz["owner_email"]
    assert call["tx_ref"].startswith(f"WB-SUB-{biz['id']}-premium_quarterly-")
    assert call["meta"] == {"business_id": str(biz["id"]), "type": "subscription", "plan": "premium_quarterly"}
    assert call["redirect_url"].endswith("/subscribe/verify")


def test_checkout_rejects_unknown_plan(client, make_business, monkeypatch):
    _capture_payment_link(monkeypatch)
    biz = make_business("payco2", status="trial")
    res = client.post(
        "/api/subscription/checkout",
        json={"plan": "platinum_monthly"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 400


def test_successful_payment_activates_subscription(client, make_business, monkeypatch):
    biz = make_business("payco3", status="trial")
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-abcd1234"
    _verify_as(monkeypatch, tx_ref=tx_ref)
    res = client.get(f"/subscribe/verify?tx_ref={tx_ref}&transaction_id=tx-ok-1")
    assert res.status_code == 200
    rows = _subscription_rows(biz["id"])
    assert len(rows) == 1
    assert rows[0]["stripe_subscription_id"] == tx_ref
    assert rows[0]["plan"] == "premium_monthly"
    assert rows[0]["amount"] == 19.99
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "active"
    assert sub["plan"] == "premium_monthly"
    assert sub["max_staff"] == 5


def test_repeat_redirect_does_not_activate_twice(client, make_business, monkeypatch):
    biz = make_business("payco4", status="trial")
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-feed0001"
    _verify_as(monkeypatch, tx_ref=tx_ref)
    client.get(f"/subscribe/verify?tx_ref={tx_ref}&transaction_id=tx-dup")
    res = client.get(f"/subscribe/verify?tx_ref={tx_ref}&transaction_id=tx-dup")
    assert res.status_code == 200
    assert len(_subscription_rows(biz["id"])) == 1


def test_underpayment_does_not_activate(client, make_business, monkeypatch):
    biz = make_business("payco5", status="trial")
    _running_trial(biz)
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-beef0002"
    _verify_as(monkeypatch, tx_ref=tx_ref, amount=5.00)
    client.get(f"/subscribe/verify?tx_ref={tx_ref}&transaction_id=tx-short")
    assert _subscription_rows(biz["id"]) == []
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "trial"


def test_failed_payment_does_not_activate(client, make_business, monkeypatch):
    biz = make_business("payco6", status="trial")
    _running_trial(biz)
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-dead0003"
    _verify_as(monkeypatch, status="failed", tx_ref=tx_ref)
    client.get(f"/subscribe/verify?tx_ref={tx_ref}&transaction_id=tx-failed")
    assert _subscription_rows(biz["id"]) == []
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "trial"
