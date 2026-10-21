import requests

r = requests.post(
    "https://demo.wab.ad/api/storefront/checkout",
    json={
        "slug": "demo",
        "customer_name": "Test Buyer",
        "customer_email": "buyer@test.com",
        "customer_phone": "07123456789",
        "items": [{"product_id": 1, "quantity": 1}],
    },
    timeout=30,
)
print("status:", r.status_code)
print(r.text[:500])
