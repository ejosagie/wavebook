import sqlite3
import requests

conn = sqlite3.connect("/opt/wavebook/backend/data/wavebook.db")
row = conn.execute(
    "SELECT id, payment_status FROM bookings ORDER BY id DESC LIMIT 1"
).fetchone()
print("latest booking:", row)
bid = row[0]

r = requests.post(
    "https://demo.wab.ad/api/payments/init",
    json={"booking_id": bid, "slug": "demo"},
    timeout=40,
)
print("deposit:", r.status_code, r.text[:300])
