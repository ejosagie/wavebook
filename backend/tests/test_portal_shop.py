"""Portal Shop tab: web-only owners can manage storefront settings, products, and orders."""

import json

from app import database


def _login(client, biz):
    res = client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": "ownerpass1"},
        follow_redirects=False,
    )
    assert res.status_code == 303


def _product(client, business_id):
    conn = database.get_connection()
    try:
        return dict(
            conn.execute(
                "SELECT * FROM products WHERE business_id = ?", (business_id,)
            ).fetchone()
        )
    finally:
        conn.close()


def test_portal_shop_settings_save(client, make_business):
    biz = make_business("shopweb")
    _login(client, biz)
    res = client.post(
        "/portal/shop",
        data={
            "storefront_enabled": "on",
            "store_country": "US",
            "shipping_fee_local": "3.50",
            "shipping_fee_international": "9.99",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM businesses WHERE id = ?", (biz["id"],)).fetchone()
    finally:
        conn.close()
    assert row["storefront_enabled"] == 1
    assert row["store_country"] == "US"
    assert row["shipping_fee_local"] == 3.50
    assert row["shipping_fee_international"] == 9.99


def test_portal_product_create_update_delete(client, make_business):
    biz = make_business("proddweb", plan="premium_monthly")
    _login(client, biz)

    # Create
    res = client.post(
        "/portal/products",
        data={"name": "Candle", "description": "Scented", "price": "7.50", "stock": "4"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    p = _product(client, biz["id"])
    assert p["name"] == "Candle"
    assert p["stock"] == 4

    # Update (low stock + hide)
    res = client.post(
        f"/portal/products/{p['id']}",
        data={"name": "Candle XL", "price": "12.00", "stock": "3", "sort_order": "2"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    p = _product(client, biz["id"])
    assert p["name"] == "Candle XL"
    assert p["stock"] == 3
    assert p["active"] == 0  # checkbox unchecked → hidden

    # Delete
    res = client.post(f"/portal/products/{p['id']}/delete", follow_redirects=False)
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE business_id = ?", (biz["id"],)
        ).fetchone()["c"] == 0
    finally:
        conn.close()


def test_portal_order_status_update(client, make_business):
    biz = make_business("ordweb")
    _login(client, biz)
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO orders (business_id, customer_name, customer_email, customer_phone, "
            "items, total, status) VALUES (?, 'Jane', 'j@x.com', '071', '[]', 20.0, 'pending')",
            (biz["id"],),
        )
        conn.commit()
        order_id = conn.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
    finally:
        conn.close()

    res = client.post(
        f"/portal/orders/{order_id}/status",
        data={"status": "shipped"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    finally:
        conn.close()
    assert row["status"] == "shipped"


def test_portal_shop_tab_renders_products_and_orders(client, make_business):
    biz = make_business("shopview", plan="premium_monthly")
    _login(client, biz)
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO products (business_id, name, price, stock, active) VALUES (?, 'Soap', 4.0, 2, 1)",
            (biz["id"],),
        )
        conn.execute(
            "INSERT INTO orders (business_id, customer_name, customer_email, customer_phone, "
            "items, total, status) VALUES (?, 'Jane', 'j@x.com', '071', ?, 12.0, 'paid')",
            (biz["id"], json.dumps([{"name": "Soap", "price": 4.0, "quantity": 3}])),
        )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/portal?tab=shop")
    assert res.status_code == 200
    assert "Soap" in res.text
    assert "2 left" in res.text          # red low-stock badge
    assert "#" in res.text and "paid" in res.text  # order row rendered
