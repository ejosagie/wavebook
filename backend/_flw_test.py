import requests

key = ""
for line in open("/opt/wavebook/backend/.env"):
    if line.startswith("FLW_SECRET_KEY="):
        key = line.split("=", 1)[1].strip()
        break

base = {
    "tx_ref": "WB-ORD-5-abc123",
    "amount": "14.0",
    "currency": "GBP",
    "country": "GB",
    "redirect_url": "https://getwavebook.com/pay/verify",
    "customer": {"email": "buyer@test.com"},
    "meta": {"order_id": "5", "business_id": "1", "type": "storefront"},
    "customizations": {"title": "T", "description": "T", "logo": "https://getwavebook.com/static/img/icon.png"},
}

variants = {
    "title_Demo_Store": {"customizations": {"title": "Demo Store", "description": "T", "logo": "https://getwavebook.com/static/img/icon.png"}},
    "desc_Order": {"customizations": {"title": "T", "description": "Order #5 from Demo", "logo": "https://getwavebook.com/static/img/icon.png"}},
    "title_Store": {"customizations": {"title": "Store", "description": "T", "logo": "https://getwavebook.com/static/img/icon.png"}},
    "title_Demo": {"customizations": {"title": "Demo", "description": "T", "logo": "https://getwavebook.com/static/img/icon.png"}},
    "desc_Order_plain": {"customizations": {"title": "T", "description": "Order 5 from Demo", "logo": "https://getwavebook.com/static/img/icon.png"}},
    "desc_from_Demo": {"customizations": {"title": "T", "description": "from Demo", "logo": "https://getwavebook.com/static/img/icon.png"}},
}
for name, extra in variants.items():
    payload = dict(base)
    payload.update(extra)
    r = requests.post(
        "https://api.flutterwave.com/v3/payments",
        json=payload,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        timeout=15,
    )
    print(name, "->", r.status_code, r.text[:40].replace("\n", " "))
