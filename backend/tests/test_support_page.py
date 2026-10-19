def test_support_page_is_public_and_lists_contact(client):
    res = client.get("/support")
    assert res.status_code == 200
    assert "support@getwavebook.com" in res.text
    assert "NeuroWaves Data Systems" in res.text


def test_privacy_page_is_public(client):
    res = client.get("/privacy")
    assert res.status_code == 200
    assert "Privacy Policy" in res.text
    assert "support@getwavebook.com" in res.text


def test_copyright_page_is_public(client):
    res = client.get("/copyright")
    assert res.status_code == 200
    assert "NeuroWaves Data Systems" in res.text


def test_landing_page_is_public(client):
    assert client.get("/").status_code == 200


def test_download_page_is_public_with_store_links(client):
    res = client.get("/download")
    assert res.status_code == 200
    assert "Download the WaveBook app" in res.text
    assert "apps.apple.com" in res.text
    assert "play.google.com" in res.text
