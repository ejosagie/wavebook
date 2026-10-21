import requests
from app.config import settings

payload = {
    "tx_ref": "WB-ORD-999-TEST",
    "amount": "14.00",
    "currency": "GBP",
    "country": settings.FLW_COUNTRY,
    "redirect_url": "https://getwavebook.com/pay/verify",
    "customer": {"email": "buyer@test.com"},
    "meta": {"order_id": "999", "business_id": "1", "type": "storefront_order"},
    "customizations": {
        "title": "WaveBook Store",
        "description": "Store order",
        "logo": "https://getwavebook.com/static/img/icon.png",
    },
}
r = requests.post(
    "https://api.flutterwave.com/v3/payments",
    json=payload,
    headers={"Authorization": "Bearer " + settings.FLW_SECRET_KEY, "Content-Type": "application/json"},
    timeout=30,
)
print("status:", r.status_code)
print(r.text[:300])
