def test_support_page_is_public_and_lists_contact(client):
    res = client.get("/support")
    assert res.status_code == 200
    assert "support@getwavebook.com" in res.text
    assert "NeuroWaves Data Systems Ltd" in res.text


def test_privacy_page_is_public(client):
    res = client.get("/privacy")
    assert res.status_code == 200
    assert "Privacy Policy" in res.text
    assert "support@getwavebook.com" in res.text


def test_copyright_page_is_public(client):
    res = client.get("/copyright")
    assert res.status_code == 200
    assert "NeuroWaves Data Systems Ltd" in res.text


def test_landing_page_is_public(client):
    assert client.get("/").status_code == 200
