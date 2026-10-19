from io import BytesIO

from PIL import Image

from app.services import gcs


def _png_bytes():
    buf = BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def _capture_gcloud(monkeypatch):
    calls = []

    def fake_run(args):
        calls.append(args)
        return True, ""

    monkeypatch.setattr(gcs, "_run_gcloud", fake_run)
    return calls


def test_shop_image_is_stored_under_prefix(monkeypatch):
    monkeypatch.setattr(gcs, "GCS_BUCKET_NAME", "shopbucket")
    monkeypatch.setattr(gcs, "BLOB_ROOT", "wavebook/")
    calls = _capture_gcloud(monkeypatch)
    url = gcs.upload_shop_image(3, 7, _png_bytes())
    assert url == "https://storage.googleapis.com/shopbucket/wavebook/shop-images/3/7.jpg"
    assert calls[0][-1] == "gs://shopbucket/wavebook/shop-images/3/7.jpg"


def test_shop_image_without_prefix_uses_bucket_root(monkeypatch):
    monkeypatch.setattr(gcs, "GCS_BUCKET_NAME", "shopbucket")
    monkeypatch.setattr(gcs, "BLOB_ROOT", "")
    calls = _capture_gcloud(monkeypatch)
    url = gcs.upload_shop_image(3, 7, _png_bytes())
    assert url == "https://storage.googleapis.com/shopbucket/shop-images/3/7.jpg"
    assert calls[0][-1] == "gs://shopbucket/shop-images/3/7.jpg"


def test_delete_uses_prefix(monkeypatch):
    monkeypatch.setattr(gcs, "GCS_BUCKET_NAME", "shopbucket")
    monkeypatch.setattr(gcs, "BLOB_ROOT", "wavebook/")
    calls = _capture_gcloud(monkeypatch)
    gcs.delete_shop_image(3, 7)
    assert calls[0] == ["rm", "gs://shopbucket/wavebook/shop-images/3/7.jpg"]
