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
