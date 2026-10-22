from app import database
from app.routers import products
from conftest import auth


PNG = b"\x89PNG\r\n\x1a\nfake"


def _create_product(client, token):
    res = client.post(
        "/api/products",
        json={"name": "Candle", "description": "", "price": 5.0, "sort_order": 0},
        headers=auth(token),
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _upload(client, token, product_id, name="photo.png"):
    return client.post(
        f"/api/products/{product_id}/images",
        files={"file": (name, PNG, "image/png")},
        headers=auth(token),
    )


def test_product_accepts_up_to_four_images(client, make_business, monkeypatch, tmp_path):
    monkeypatch.setattr(products, "UPLOAD_DIR", tmp_path)
    biz = make_business("multiimg", plan="premium_monthly")
    pid = _create_product(client, biz["owner_token"])
    for _ in range(4):
        res = _upload(client, biz["owner_token"], pid)
        assert res.status_code == 201, res.text
    listed = client.get("/api/products", headers=auth(biz["owner_token"])).json()
    assert len(listed[0]["images"]) == 4


def test_fifth_image_is_rejected(client, make_business, monkeypatch, tmp_path):
    monkeypatch.setattr(products, "UPLOAD_DIR", tmp_path)
    biz = make_business("multiimg5", plan="premium_monthly")
    pid = _create_product(client, biz["owner_token"])
    for _ in range(4):
        assert _upload(client, biz["owner_token"], pid).status_code == 201
    res = _upload(client, biz["owner_token"], pid)
    assert res.status_code == 400
    assert "4" in res.json()["detail"]


def test_images_keep_upload_order_and_primary_path(client, make_business, monkeypatch, tmp_path):
    monkeypatch.setattr(products, "UPLOAD_DIR", tmp_path)
    biz = make_business("multiimgorder", plan="premium_monthly")
    pid = _create_product(client, biz["owner_token"])
    first = _upload(client, biz["owner_token"], pid).json()["path"]
    _upload(client, biz["owner_token"], pid)
    listed = client.get("/api/products", headers=auth(biz["owner_token"])).json()[0]
    assert listed["images"][0]["path"] == first
    assert listed["image_path"] == first


def test_delete_one_image_keeps_others_and_removes_file(client, make_business, monkeypatch, tmp_path):
    monkeypatch.setattr(products, "UPLOAD_DIR", tmp_path)
    biz = make_business("multiimgdel", plan="premium_monthly")
    token = biz["owner_token"]
    pid = _create_product(client, token)
    _upload(client, token, pid)
    _upload(client, token, pid)
    images = client.get("/api/products", headers=auth(token)).json()[0]["images"]
    res = client.delete(f"/api/products/{pid}/images/{images[0]['id']}", headers=auth(token))
    assert res.status_code == 200, res.text
    assert len(res.json()["images"]) == 1
    assert not (tmp_path / images[0]["path"].split("/")[-1]).exists()
    listed = client.get("/api/products", headers=auth(token)).json()[0]
    assert listed["image_path"] == listed["images"][0]["path"]


def test_delete_product_removes_all_images(client, make_business, monkeypatch, tmp_path):
    monkeypatch.setattr(products, "UPLOAD_DIR", tmp_path)
    biz = make_business("multiimgprod", plan="premium_monthly")
    token = biz["owner_token"]
    pid = _create_product(client, token)
    _upload(client, token, pid)
    _upload(client, token, pid)
    assert len(list(tmp_path.glob("product_*"))) == 2
    assert client.delete(f"/api/products/{pid}", headers=auth(token)).status_code == 200
    assert list(tmp_path.glob("product_*")) == []


def test_storefront_lists_product_images(client, make_business, monkeypatch, tmp_path):
    monkeypatch.setattr(products, "UPLOAD_DIR", tmp_path)
    biz = make_business("multiimgstore", plan="premium_monthly")
    token = biz["owner_token"]
    pid = _create_product(client, token)
    _upload(client, token, pid)
    _upload(client, token, pid)
    conn = database.get_connection()
    try:
        conn.execute("UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],))
        conn.commit()
    finally:
        conn.close()
    res = client.get("/api/storefront/multiimgstore")
    assert res.status_code == 200, res.text
    assert len(res.json()["products"][0]["images"]) == 2


def test_store_page_renders_pagination_with_many_products(client, make_business):
    """The storefront page must render all product cards plus pagination
    controls and a results counter so large catalogues stay usable."""
    biz = make_business("bigstore")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET storefront_enabled = 1 WHERE id = ?", (biz["id"],)
        )
        for i in range(30):
            conn.execute(
                "INSERT INTO products (business_id, name, price, active) VALUES (?, ?, ?, 1)",
                (biz["id"], f"Product {i}", 5.0),
            )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/t/bigstore/store")
    assert res.status_code == 200, res.text
    html = res.text
    assert html.count('class="service-card product-card"') == 30
    assert 'id="pagination"' in html
    assert 'id="store-results"' in html
    assert "PAGE_SIZE" in html
    assert "renderProducts" in html
