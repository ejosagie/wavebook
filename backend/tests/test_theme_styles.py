from app import database
from app.config import settings
from app.services import emailer
from conftest import auth


def _login(client, biz):
    res = client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": "ownerpass1"},
        follow_redirects=False,
    )
    assert res.status_code == 303


def _business_row(business_id):
    conn = database.get_connection()
    try:
        return dict(
            conn.execute(
                "SELECT theme_color, dark_theme, theme_style, theme_font FROM businesses WHERE id = ?",
                (business_id,),
            ).fetchone()
        )
    finally:
        conn.close()


def test_selecting_preset_applies_accent_dark_and_font(client, make_business):
    biz = make_business("styleco1")
    res = client.patch(
        "/api/business",
        json={"theme_style": "midnight"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    row = _business_row(biz["id"])
    assert row["theme_style"] == "midnight"
    assert row["theme_color"] == "#d4a017"
    assert row["dark_theme"] == 1
    assert row["theme_font"] == "georgia"


def test_invalid_preset_rejected(client, make_business):
    biz = make_business("styleco2")
    res = client.patch(
        "/api/business",
        json={"theme_style": "neon"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 422


def test_custom_style_keeps_custom_colors(client, make_business):
    biz = make_business("styleco3")
    res = client.patch(
        "/api/business",
        json={"theme_style": "custom", "theme_color": "#123456", "dark_theme": True},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    row = _business_row(biz["id"])
    assert row["theme_style"] == "custom"
    assert row["theme_color"] == "#123456"
    assert row["dark_theme"] == 1
    assert row["theme_font"] == ""


def test_tenant_page_renders_preset_theme(client, make_business):
    biz = make_business("styleco4")
    client.patch(
        "/api/business",
        json={"theme_style": "ocean"},
        headers=auth(biz["owner_token"]),
    )
    res = client.get("/t/styleco4")
    assert res.status_code == 200
    assert "#0ea5e9" in res.text


def test_legacy_custom_theme_preserved_on_tenant_page(client, make_business):
    biz = make_business("styleco5")
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET theme_style = 'custom', theme_color = '#123456', dark_theme = 1 WHERE id = ?",
            (biz["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    res = client.get("/t/styleco5")
    assert res.status_code == 200
    assert "#123456" in res.text
    assert "#ec4899" not in res.text


def test_new_business_defaults_to_rose(client, make_business):
    res = client.post(
        "/api/auth/signup",
        json={"email": "newrose@wavebook.com", "password": "ownerpass1", "full_name": "New Rose", "phone": "+14155550123"},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    res = client.post(
        "/api/business",
        json={"name": "Rose Co", "slug": "roseco1"},
        headers=auth(token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["theme_style"] == "rose"


def test_portal_customize_saves_preset(client, make_business):
    biz = make_business("styleco6")
    _login(client, biz)
    res = client.post(
        "/portal/customize",
        data={
            "name": "Styleco6 Studio",
            "theme_style": "ocean",
            "theme_font": "default",
            "theme_color": "#000000",
            "dark_theme": "",
            "storefront_enabled": "",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    row = _business_row(biz["id"])
    assert row["theme_style"] == "ocean"
    assert row["theme_color"] == "#0ea5e9"
    assert row["dark_theme"] == 0
    assert row["theme_font"] == "default"


def test_portal_customize_saves_font_with_custom_style(client, make_business):
    biz = make_business("styleco7")
    _login(client, biz)
    res = client.post(
        "/portal/customize",
        data={
            "name": "Styleco7 Studio",
            "theme_style": "custom",
            "theme_font": "georgia",
            "theme_color": "#123456",
            "dark_theme": "on",
            "storefront_enabled": "",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    row = _business_row(biz["id"])
    assert row["theme_style"] == "custom"
    assert row["theme_color"] == "#123456"
    assert row["dark_theme"] == 1
    assert row["theme_font"] == "georgia"


def test_portal_customize_rejects_unknown_style(client, make_business):
    biz = make_business("styleco8")
    _login(client, biz)
    res = client.post(
        "/portal/customize",
        data={
            "name": "Styleco8 Studio",
            "theme_style": "neon",
            "theme_font": "default",
            "theme_color": "#000000",
            "dark_theme": "",
            "storefront_enabled": "",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "error=" in res.headers["location"]
    assert _business_row(biz["id"])["theme_style"] != "neon"


def test_smtp_send_email(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, user, password):
            sent.append(("login", user, password))

        def send_message(self, msg):
            sent.append(("send", msg["To"], msg["Subject"]))

    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(settings, "SMTP_HOST", "mail.test")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "support@test.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
    result = emailer.send_email("jane@test.com", "Hello", "Body text")
    assert result["provider"] == "smtp"
    assert result["status"] == "sent"
    assert sent[0] == ("login", "support@test.com", "secret")
    assert sent[1] == ("send", "jane@test.com", "Hello")
