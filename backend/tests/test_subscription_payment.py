from datetime import date, timedelta

from app import database
from app.services import stripepay
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
        return "https://checkout.stripe.test/pay/abc"

    monkeypatch.setattr(stripepay, "create_subscription_checkout_session", fake_create)
    return calls


def _verify_as(
    monkeypatch,
    *,
    status="paid",
    amount=19.99,
    plan="premium_monthly",
    tx_ref=None,
    currency="GBP",
    meta_currency=None,
):
    meta = {"plan": plan}
    if meta_currency is not None:
        meta["currency"] = meta_currency

    def fake_retrieve(session_id):
        return {
            "id": session_id,
            "payment_status": status,
            "amount_total": int(round(amount * 100)),
            "currency": currency.lower(),
            "subscription": "sub_test_123",
            "metadata": {"tx_ref": tx_ref, **meta},
        }

    monkeypatch.setattr(stripepay, "retrieve_checkout_session", fake_retrieve)


def _subscription_rows(business_id):
    conn = database.get_connection()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT stripe_subscription_id, tx_ref, plan, amount, status, currency, current_period_end FROM subscriptions WHERE business_id = ?",
                (business_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


def test_subscribe_page_renders_currency_selector(client):
    res = client.get("/subscribe")
    assert res.status_code == 200
    assert 'name="currency"' in res.text
    assert "currency-GBP" in res.text
    assert "currency-USD" in res.text
    assert "currency-EUR" in res.text


def test_checkout_creates_payment_link_for_chosen_plan(client, make_business, monkeypatch):
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("payco1", status="trial")
    res = client.post(
        "/api/subscription/checkout",
        json={"plan": "premium_quarterly"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["payment_link"] == "https://checkout.stripe.test/pay/abc"
    call = calls[-1]
    assert call["amount"] == 56.99
    assert call["currency"] == "GBP"
    assert call["customer_email"] == biz["owner_email"]
    assert call["tx_ref"].startswith(f"WB-SUB-{biz['id']}-premium_quarterly-")
    assert call["interval"] == "month"
    assert call["interval_count"] == 3
    assert call["metadata"] == {
        "business_id": str(biz["id"]),
        "type": "subscription",
        "plan": "premium_quarterly",
        "currency": "GBP",
    }
    assert call["success_url"].endswith("/subscribe/verify?session_id={CHECKOUT_SESSION_ID}")


def test_checkout_converts_price_for_usd(client, make_business, monkeypatch):
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("payco7", status="trial")
    res = client.post(
        "/api/subscription/checkout",
        json={"plan": "premium_quarterly", "currency": "USD"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    call = calls[-1]
    assert call["amount"] == round(56.99 * 1.35, 2)  # 76.94
    assert call["currency"] == "USD"
    assert call["metadata"]["currency"] == "USD"


def test_checkout_converts_price_for_eur(client, make_business, monkeypatch):
    calls = _capture_payment_link(monkeypatch)
    biz = make_business("payco8", status="trial")
    res = client.post(
        "/api/subscription/checkout",
        json={"plan": "premium_quarterly", "currency": "eur"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    call = calls[-1]
    assert call["amount"] == round(56.99 * 1.19, 2)  # 67.82
    assert call["currency"] == "EUR"
    assert call["metadata"]["currency"] == "EUR"


def test_checkout_rejects_unsupported_currency(client, make_business, monkeypatch):
    _capture_payment_link(monkeypatch)
    biz = make_business("payco9", status="trial")
    res = client.post(
        "/api/subscription/checkout",
        json={"plan": "premium_monthly", "currency": "JPY"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 400
    assert "Unsupported currency" in res.text


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
    res = client.get("/subscribe/verify?session_id=cs_ok_1")
    assert res.status_code == 200
    rows = _subscription_rows(biz["id"])
    assert len(rows) == 1
    assert rows[0]["stripe_subscription_id"] == "sub_test_123"
    assert rows[0]["tx_ref"] == tx_ref
    assert rows[0]["plan"] == "premium_monthly"
    assert rows[0]["amount"] == 19.99
    assert rows[0]["currency"] == "GBP"
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "active"
    assert sub["plan"] == "premium_monthly"
    assert sub["max_staff"] == 5
    assert sub["auto_renew"] is True


def test_successful_usd_payment_activates_and_records_currency(client, make_business, monkeypatch):
    biz = make_business("payc10", status="trial")
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-usd0001"
    _verify_as(monkeypatch, tx_ref=tx_ref, amount=round(19.99 * 1.35, 2), currency="USD", meta_currency="USD")
    res = client.get("/subscribe/verify?session_id=cs_usd_1")
    assert res.status_code == 200
    rows = _subscription_rows(biz["id"])
    assert len(rows) == 1
    assert rows[0]["amount"] == round(19.99 * 1.35, 2)
    assert rows[0]["currency"] == "USD"


def test_verify_rejects_currency_mismatch(client, make_business, monkeypatch):
    biz = make_business("payc11", status="trial")
    _running_trial(biz)
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-mismatch"
    _verify_as(monkeypatch, tx_ref=tx_ref, currency="GBP", meta_currency="USD")
    client.get("/subscribe/verify?session_id=cs_mismatch")
    assert _subscription_rows(biz["id"]) == []


def test_verify_rejects_unsupported_currency(client, make_business, monkeypatch):
    biz = make_business("payc12", status="trial")
    _running_trial(biz)
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-jpy0001"
    _verify_as(monkeypatch, tx_ref=tx_ref, amount=50000, currency="JPY")
    client.get("/subscribe/verify?session_id=cs_jpy")
    assert _subscription_rows(biz["id"]) == []


def test_usd_underpayment_does_not_activate(client, make_business, monkeypatch):
    biz = make_business("payc13", status="trial")
    _running_trial(biz)
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-shortusd"
    _verify_as(monkeypatch, tx_ref=tx_ref, amount=10.00, currency="USD", meta_currency="USD")
    client.get("/subscribe/verify?session_id=cs_short_usd")
    assert _subscription_rows(biz["id"]) == []


def test_repeat_redirect_does_not_activate_twice(client, make_business, monkeypatch):
    biz = make_business("payco4", status="trial")
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-feed0001"
    _verify_as(monkeypatch, tx_ref=tx_ref)
    client.get("/subscribe/verify?session_id=cs_dup")
    res = client.get("/subscribe/verify?session_id=cs_dup")
    assert res.status_code == 200
    assert len(_subscription_rows(biz["id"])) == 1


def test_underpayment_does_not_activate(client, make_business, monkeypatch):
    biz = make_business("payco5", status="trial")
    _running_trial(biz)
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-beef0002"
    _verify_as(monkeypatch, tx_ref=tx_ref, amount=5.00)
    client.get("/subscribe/verify?session_id=cs_short")
    assert _subscription_rows(biz["id"]) == []
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "trial"


def test_failed_payment_does_not_activate(client, make_business, monkeypatch):
    biz = make_business("payco6", status="trial")
    _running_trial(biz)
    tx_ref = f"WB-SUB-{biz['id']}-premium_monthly-dead0003"
    _verify_as(monkeypatch, status="unpaid", tx_ref=tx_ref)
    client.get("/subscribe/verify?session_id=cs_failed")
    assert _subscription_rows(biz["id"]) == []
    sub = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert sub["status"] == "trial"
