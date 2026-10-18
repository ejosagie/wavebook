from app.routers import bookings as bookings_router
from app.routers import payments as payments_router
from app.services import emailer, flutterwave
from conftest import auth


def _open_slot(monkeypatch):
    monkeypatch.setattr(bookings_router, "get_available_time_slots", lambda *a, **k: ["10:00"])
    monkeypatch.setattr(bookings_router, "is_date_blocked", lambda *a, **k: False)


def test_new_booking_emails_customer_and_owner(client, make_business, make_service, monkeypatch, sent):
    _open_slot(monkeypatch)
    biz = make_business("bookco", contact_email="studio@wavebook.com")
    service_id = make_service(biz["id"])
    res = client.post(
        "/api/bookings",
        json={
            "customer_name": "Jane Customer",
            "customer_email": "jane@wavebook.com",
            "customer_phone": "07123456789",
            "service_id": service_id,
            "date": "2030-06-01",
            "time": "10:00",
            "notes": "Fringe trim",
        },
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 201, res.text
    recipients = {m["to"]: m["subject"] for m in sent}
    assert "jane@wavebook.com" in recipients
    assert recipients["jane@wavebook.com"].startswith("Booking received")
    assert "studio@wavebook.com" in recipients
    assert recipients["studio@wavebook.com"].startswith("New booking")


def test_owner_address_falls_back_to_account_email(make_business, sent):
    biz = make_business("fallbackco", contact_email="")
    assert emailer._owner_address({"id": biz["id"], "contact_email": ""}) == biz["owner_email"]


def test_deposit_payment_emails_customer_confirmation(make_business, make_booking, client, monkeypatch, sent):
    biz = make_business("payco", contact_email="pay@wavebook.com", deposit=20.0)
    booking_id = make_booking(biz["id"], customer_email="jane@wavebook.com", status="pending", service_price=50.0)
    monkeypatch.setattr(
        flutterwave,
        "verify_transaction",
        lambda transaction_id: {
            "status": "successful",
            "tx_ref": f"WB-BK-{booking_id}-abcd",
            "amount": 20.0,
            "id": "tx-deposit",
            "currency": "GBP",
        },
    )
    monkeypatch.setattr(payments_router, "send_booking_confirmation_sms", lambda *a, **k: {"status": "skipped"})
    res = client.get(f"/api/payments/verify?tx_ref=WB-BK-{booking_id}-abcd&transaction_id=tx-deposit")
    assert res.status_code == 200, res.text
    customer = [m for m in sent if m["to"] == "jane@wavebook.com"]
    assert len(customer) == 1
    assert customer[0]["subject"].startswith("Booking confirmed")


def test_paid_order_emails_customer_and_owner_once(client, make_business, monkeypatch, sent):
    import json

    from app import database

    biz = make_business("shopco", contact_email="shop@wavebook.com")
    items = json.dumps([{"product_id": 1, "name": "Shampoo", "price": 12.5, "quantity": 2}])
    conn = database.get_connection()
    try:
        order_id = conn.execute(
            "INSERT INTO orders (business_id, customer_name, customer_email, customer_phone, items, total, status) "
            "VALUES (?, 'Jane Customer', 'jane@wavebook.com', '07123456789', ?, 25.0, 'pending')",
            (biz["id"], items),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(
        flutterwave,
        "verify_transaction",
        lambda transaction_id: {
            "status": "successful",
            "tx_ref": f"WB-ORD-{order_id}-abcd",
            "amount": 25.0,
            "id": "tx-order",
            "currency": "GBP",
        },
    )
    url = f"/api/payments/verify?tx_ref=WB-ORD-{order_id}-abcd&transaction_id=tx-order"
    res = client.get(url)
    assert res.status_code == 200, res.text
    recipients = [m["to"] for m in sent]
    assert recipients.count("jane@wavebook.com") == 1
    assert recipients.count("shop@wavebook.com") == 1

    again = client.get(url)
    assert again.status_code == 200
    assert len(sent) == 2
