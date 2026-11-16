from app.services import stripepay
from conftest import auth


def test_owner_can_start_sms_topup(client, make_business, monkeypatch):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return "https://checkout.stripe.test/pay/sms"

    monkeypatch.setattr(stripepay, "create_checkout_session", fake_create)
    biz = make_business("smstopup")
    res = client.post("/api/payments/sms/topup", headers=auth(biz["owner_token"]))
    assert res.status_code == 200, res.text
    assert res.json()["payment_link"] == "https://checkout.stripe.test/pay/sms"
    assert calls[0]["customer_email"] == biz["owner_email"]
    assert calls[0]["metadata"]["type"] == "sms_topup"
