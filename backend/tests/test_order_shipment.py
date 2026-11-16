"""Storefront order shipment/delivery flow: required fields, persistence, and customer emails."""

import json

from app import database
from conftest import auth


def _order(biz, status="pending", customer_email="jane@wavebook.com"):
    conn = database.get_connection()
    try:
        order_id = conn.execute(
            "INSERT INTO orders (business_id, customer_name, customer_email, customer_phone, items, total, status) "
            "VALUES (?, 'Jane Customer', ?, '07123456789', ?, 25.0, ?)",
            (biz["id"], customer_email, json.dumps([{"name": "Shampoo", "price": 12.5, "quantity": 2}]), status),
        ).lastrowid
        conn.commit()
        return order_id
    finally:
        conn.close()


def _row(order_id):
    conn = database.get_connection()
    try:
        return dict(
            conn.execute(
                "SELECT status, tracking_number, courier_name, delivered_at FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        )
    finally:
        conn.close()


def test_shipped_requires_courier_and_tracking(client, make_business):
    biz = make_business("shipreq")
    order_id = _order(biz)
    res = client.patch(
        f"/api/orders/{order_id}",
        json={"status": "shipped"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 422
    assert "courier" in res.json()["detail"].lower()
    assert _row(order_id)["status"] == "pending"


def test_shipped_saves_fields_and_emails_customer(client, make_business, sent):
    biz = make_business("shipok")
    order_id = _order(biz)
    res = client.patch(
        f"/api/orders/{order_id}",
        json={"status": "shipped", "courier_name": "DPD", "tracking_number": "TRK-123"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    row = _row(order_id)
    assert row["status"] == "shipped"
    assert row["courier_name"] == "DPD"
    assert row["tracking_number"] == "TRK-123"
    shipped = [m for m in sent if m["to"] == "jane@wavebook.com"]
    assert len(shipped) == 1
    assert "shipped" in shipped[0]["subject"].lower()
    assert "DPD" in shipped[0]["body"]
    assert "TRK-123" in shipped[0]["body"]


def test_delivered_requires_delivery_date(client, make_business):
    biz = make_business("delreq")
    order_id = _order(biz, status="shipped")
    res = client.patch(
        f"/api/orders/{order_id}",
        json={"status": "delivered"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 422
    assert "delivery date" in res.json()["detail"].lower()
    assert _row(order_id)["status"] == "shipped"


def test_delivered_saves_date_and_emails_customer(client, make_business, sent):
    biz = make_business("delok")
    order_id = _order(biz, status="shipped")
    res = client.patch(
        f"/api/orders/{order_id}",
        json={"status": "delivered", "delivered_at": "2026-11-15"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    row = _row(order_id)
    assert row["status"] == "delivered"
    assert row["delivered_at"] == "2026-11-15"
    delivered = [m for m in sent if m["to"] == "jane@wavebook.com"]
    assert len(delivered) == 1
    assert "delivered" in delivered[0]["subject"].lower()
    assert "2026-11-15" in delivered[0]["body"]


def test_unrelated_status_update_preserves_shipment_fields(client, make_business):
    biz = make_business("shippreserve")
    order_id = _order(biz, status="shipped")
    client.patch(
        f"/api/orders/{order_id}",
        json={"status": "shipped", "courier_name": "Royal Mail", "tracking_number": "RM-9"},
        headers=auth(biz["owner_token"]),
    )
    # A later status change without shipment fields must not wipe them.
    res = client.patch(
        f"/api/orders/{order_id}",
        json={"status": "confirmed"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    row = _row(order_id)
    assert row["courier_name"] == "Royal Mail"
    assert row["tracking_number"] == "RM-9"


def test_no_duplicate_emails_on_resubmit(client, make_business, sent):
    biz = make_business("shiponce")
    order_id = _order(biz)
    payload = {"status": "shipped", "courier_name": "DPD", "tracking_number": "TRK-1"}
    first = client.patch(f"/api/orders/{order_id}", json=payload, headers=auth(biz["owner_token"]))
    assert first.status_code == 200
    again = client.patch(f"/api/orders/{order_id}", json=payload, headers=auth(biz["owner_token"]))
    assert again.status_code == 200
    shipped = [m for m in sent if m["to"] == "jane@wavebook.com"]
    assert len(shipped) == 1
