from conftest import auth


def test_website_address_cannot_be_changed_after_setup(client, make_business):
    biz = make_business("fixedslug")
    res = client.patch(
        "/api/business",
        json={"slug": "newslug"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["slug"] == "fixedslug"


def test_owner_cannot_text_customers(client, make_business):
    biz = make_business("nosms")
    res = client.post(
        "/api/notifications/send-text",
        json={"phone": "07123456789", "message": "Hello"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 404
