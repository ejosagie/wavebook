"""Portal Services, Bookings, and Feedback tabs for web-only owners."""

from app import database


def _login(client, biz):
    res = client.post(
        "/portal/login",
        data={"email": biz["owner_email"], "password": "ownerpass1"},
        follow_redirects=False,
    )
    assert res.status_code == 303


def _service(client, business_id):
    conn = database.get_connection()
    try:
        return dict(
            conn.execute(
                "SELECT * FROM services WHERE business_id = ?", (business_id,)
            ).fetchone()
        )
    finally:
        conn.close()


def test_portal_service_create_update_delete(client, make_business):
    biz = make_business("svcweb")
    _login(client, biz)

    res = client.post(
        "/portal/services",
        data={"name": "Haircut", "description": "Wash + cut", "price": "30", "duration_minutes": "45"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    svc = _service(client, biz["id"])
    assert svc["name"] == "Haircut"
    assert svc["duration_minutes"] == 45

    res = client.post(
        f"/portal/services/{svc['id']}",
        data={"name": "Haircut Deluxe", "price": "40", "duration_minutes": "60", "sort_order": "1"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    svc = _service(client, biz["id"])
    assert svc["name"] == "Haircut Deluxe"
    assert svc["price"] == 40
    assert svc["duration_minutes"] == 60

    res = client.post(f"/portal/services/{svc['id']}/delete", follow_redirects=False)
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM services WHERE business_id = ?", (biz["id"],)
        ).fetchone()["c"] == 0
    finally:
        conn.close()


def test_portal_service_rejects_bad_input(client, make_business):
    biz = make_business("svcbad")
    _login(client, biz)
    res = client.post(
        "/portal/services",
        data={"name": "   ", "price": "10", "duration_minutes": "30"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "error=" in res.headers["location"]
    conn = database.get_connection()
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM services WHERE business_id = ?", (biz["id"],)
        ).fetchone()["c"] == 0
    finally:
        conn.close()


def test_portal_booking_status_update(client, make_business):
    biz = make_business("bkweb")
    _login(client, biz)
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO bookings (business_id, customer_name, customer_email, service_name, "
            "service_price, service_duration_minutes, date, time, status) "
            "VALUES (?, 'Jane', 'j@x.com', 'Haircut', 30, 45, '2026-10-25', '10:00', 'pending')",
            (biz["id"],),
        )
        conn.commit()
        booking_id = conn.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
    finally:
        conn.close()

    res = client.post(
        f"/portal/bookings/{booking_id}/status",
        data={"status": "confirmed"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT status FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    finally:
        conn.close()
    assert row["status"] == "confirmed"


def test_portal_booking_status_rejects_invalid(client, make_business):
    biz = make_business("bkbad")
    _login(client, biz)
    res = client.post(
        "/portal/bookings/999/status",
        data={"status": "made-up"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "error=" in res.headers["location"]


def test_portal_feedback_toggle_and_delete(client, make_business):
    biz = make_business("fbweb")
    _login(client, biz)
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO feedback (business_id, customer_name, rating, comment, approved) "
            "VALUES (?, 'Jane', 5, 'Great!', 1)",
            (biz["id"],),
        )
        conn.commit()
        fid = conn.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
    finally:
        conn.close()

    res = client.post(f"/portal/feedback/{fid}/toggle", follow_redirects=False)
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        assert conn.execute("SELECT approved FROM feedback WHERE id = ?", (fid,)).fetchone()["approved"] == 0
    finally:
        conn.close()

    res = client.post(f"/portal/feedback/{fid}/delete", follow_redirects=False)
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        assert conn.execute("SELECT COUNT(*) AS c FROM feedback WHERE id = ?", (fid,)).fetchone()["c"] == 0
    finally:
        conn.close()


def test_portal_new_tabs_render(client, make_business):
    biz = make_business("tabsweb")
    _login(client, biz)
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO services (business_id, name, price, duration_minutes) VALUES (?, 'Facial', 50, 60)",
            (biz["id"],),
        )
        conn.execute(
            "INSERT INTO bookings (business_id, customer_name, service_name, service_price, "
            "date, time, status) VALUES (?, 'Jane', 'Facial', 50, '2026-10-26', '11:00', 'pending')",
            (biz["id"],),
        )
        conn.execute(
            "INSERT INTO feedback (business_id, customer_name, rating, comment) "
            "VALUES (?, 'Jane', 4, 'Lovely')",
            (biz["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    res = client.get("/portal?tab=services")
    assert "Facial" in res.text and "Add a service" in res.text
    res = client.get("/portal?tab=bookings")
    assert "Jane" in res.text and "pending" in res.text
    res = client.get("/portal?tab=feedback")
    assert "Lovely" in res.text

def _make_bookings(business_id, count, name="Jane"):
    conn = database.get_connection()
    try:
        for i in range(count):
            conn.execute(
                "INSERT INTO bookings (business_id, customer_name, customer_email, customer_phone, "
                "service_name, service_price, date, time, status, reference) "
                "VALUES (?, ?, ?, ?, 'Cut', 30, '2026-11-01', '10:00', 'confirmed', ?)",
                (business_id, f"{name}{i}", f"{name}{i}@x.com", f"+199{i:04d}", f"REF{i:03d}"),
            )
        conn.commit()
    finally:
        conn.close()


def test_api_bookings_search_and_pagination(client, make_business):
    biz = make_business("bksearch")
    _make_bookings(biz["id"], 25)
    from conftest import auth
    headers = auth(biz["owner_token"])

    res = client.get("/api/bookings?limit=10&offset=0", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 25 and len(data["items"]) == 10

    res = client.get("/api/bookings?limit=10&offset=20", headers=headers)
    data = res.json()
    assert len(data["items"]) == 5

    res = client.get("/api/bookings?q=Jane0@x.com&limit=10", headers=headers)
    data = res.json()
    assert data["total"] == 1 and data["items"][0]["customer_name"] == "Jane0"

    res = client.get("/api/bookings?q=+1990005&limit=10", headers=headers)
    data = res.json()
    assert data["total"] == 1

    bid = data["items"][0]["id"]
    res = client.get(f"/api/bookings?q={bid}&limit=200", headers=headers)
    items = res.json()["items"]
    assert any(b["id"] == bid for b in items)

    res = client.get("/api/bookings?q=REF000&limit=10", headers=headers)
    assert res.json()["total"] == 1

    # No params keeps the legacy list response for existing callers
    res = client.get("/api/bookings", headers=headers)
    assert isinstance(res.json(), list) and len(res.json()) == 25


def test_portal_bookings_search_and_pagination(client, make_business):
    biz = make_business("bkpage")
    _login(client, biz)
    _make_bookings(biz["id"], 25)

    res = client.get("/portal?tab=bookings&q=Jane0@x.com")
    assert "Jane0" in res.text and "1 result" in res.text
    assert "Jane1<" not in res.text

    res = client.get("/portal?tab=bookings&q=zzzz")
    assert "No bookings match" in res.text

    res = client.get("/portal?tab=bookings&page=2")
    assert "Page 2 of 2" in res.text

    res = client.get("/portal?tab=bookings&page=99")
    assert "Page 2 of 2" in res.text  # clamped

def test_dark_theme_toggle(client, make_business):
    biz = make_business("darkco")
    _login(client, biz)

    res = client.get("/", headers={"host": "darkco.wab.ad"})
    assert res.status_code == 200 and "tenant-dark" not in res.text

    res = client.post(
        "/portal/customize",
        data={"name": "Darkco Studio", "dark_theme": "on"},
        follow_redirects=False,
    )
    assert res.status_code in (302, 303)

    res = client.get("/", headers={"host": "darkco.wab.ad"})
    assert "tenant-dark" in res.text
    res = client.get("/services", headers={"host": "darkco.wab.ad"})
    assert "tenant-dark" in res.text

    # Unchecking the box removes the class
    client.post("/portal/customize", data={"name": "Darkco Studio"}, follow_redirects=False)
    res = client.get("/", headers={"host": "darkco.wab.ad"})
    assert "tenant-dark" not in res.text


def test_portal_photo_management(client, make_business):
    biz = make_business("photoco")
    _login(client, biz)
    png = ("photo.png", b"\x89PNG\r\n\x1a\nfakeimg", "image/png")

    # Logo and owner photo uploads update the business row
    res = client.post("/portal/images/logo", files={"file": png}, follow_redirects=False)
    assert res.status_code == 303
    res = client.post("/portal/images/about", files={"file": png}, follow_redirects=False)
    assert res.status_code == 303

    conn = database.get_connection()
    try:
        bizrow = dict(conn.execute("SELECT * FROM businesses WHERE id = ?", (biz["id"],)).fetchone())
    finally:
        conn.close()
    assert bizrow["logo_path"].startswith("/uploads/logo_")
    assert bizrow["about_image"].startswith("/uploads/about_")

    # Gallery upload, caption, then delete
    res = client.post("/portal/gallery/2", files={"file": png}, follow_redirects=False)
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        g = dict(conn.execute(
            "SELECT * FROM gallery WHERE business_id = ? AND slot = 2", (biz["id"],)
        ).fetchone())
    finally:
        conn.close()
    assert g["path"].startswith("/uploads/gallery_2_")

    res = client.post("/portal/gallery/2/caption", data={"caption": "Fresh install"}, follow_redirects=False)
    assert res.status_code == 303
    res = client.post("/portal/gallery/2/delete", follow_redirects=False)
    assert res.status_code == 303
    conn = database.get_connection()
    try:
        g = dict(conn.execute(
            "SELECT * FROM gallery WHERE business_id = ? AND slot = 2", (biz["id"],)
        ).fetchone())
    finally:
        conn.close()
    assert g["path"] == "" and g["caption"] == ""

    # Dashboard renders the gallery slots without errors
    res = client.get("/portal?tab=customize")
    assert res.status_code == 200 and "Gallery photos" in res.text
