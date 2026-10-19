from app.services import flutterwave
from conftest import auth


def test_owner_can_start_sms_topup(client, make_business, monkeypatch):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return "https://checkout.flutterwave.test/pay/sms"

    monkeypatch.setattr(flutterwave, "create_payment_link", fake_create)
    biz = make_business("smstopup")
    res = client.post("/api/payments/sms/topup", headers=auth(biz["owner_token"]))
    assert res.status_code == 200, res.text
    assert res.json()["payment_link"] == "https://checkout.flutterwave.test/pay/sms"
    assert calls[0]["customer_email"] == biz["owner_email"]
    assert calls[0]["meta"]["type"] == "sms_topup"
