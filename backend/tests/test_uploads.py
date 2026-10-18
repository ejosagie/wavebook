from app.routers import products
from conftest import auth


def _create_product(client, token):
    res = client.post(
        "/api/products",
        json={"name": "Candle", "description": "", "price": 5.0, "sort_order": 0},
        headers=auth(token),
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_product_image_accepts_png_sent_as_generic_binary(client, make_business, monkeypatch, tmp_path):
    monkeypatch.setattr(products, "UPLOAD_DIR", tmp_path)
    biz = make_business("imgco", plan="premium_monthly")
    product_id = _create_product(client, biz["owner_token"])
    res = client.post(
        f"/api/products/{product_id}/image",
        files={"file": ("photo.png", b"\x89PNG fake", "application/octet-stream")},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["path"].startswith("/uploads/product_")
    assert len(list(tmp_path.iterdir())) == 1


def test_product_image_rejects_non_image_file(client, make_business, monkeypatch, tmp_path):
    monkeypatch.setattr(products, "UPLOAD_DIR", tmp_path)
    biz = make_business("imgbad", plan="premium_monthly")
    product_id = _create_product(client, biz["owner_token"])
    res = client.post(
        f"/api/products/{product_id}/image",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 400
    assert list(tmp_path.iterdir()) == []
