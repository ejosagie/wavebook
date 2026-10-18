import pytest

from app import database
from conftest import auth

OWNER_ONLY_PATHS = [
    "/api/bookings",
    "/api/reports/financials",
    "/api/orders",
    "/api/products",
    "/api/services",
    "/api/staff",
    "/api/notifications",
    "/api/subscription",
]


def test_basic_owner_cannot_invite_staff(client, make_business):
    biz = make_business("basicco", plan="basic_monthly")
    res = client.post(
        "/api/staff",
        json={"full_name": "Sam", "email": "sam@wavebook.com", "phone": ""},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 403
    assert "Premium" in res.json()["detail"]


def test_premium_invite_emails_credentials_that_log_in(client, make_business, invite_staff, sent):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    assert sent[-1]["to"] == "sam@wavebook.com"
    assert staff["password"] in sent[-1]["body"]
    me = client.get("/api/auth/me", headers=auth(staff["token"]))
    assert me.status_code == 200
    assert me.json()["role"] == "staff"


@pytest.mark.parametrize("path", OWNER_ONLY_PATHS)
def test_staff_blocked_from_owner_routes(client, make_business, invite_staff, path):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    res = client.get(path, headers=auth(staff["token"]))
    assert res.status_code == 403, path


def test_staff_cannot_read_business_settings(client, make_business, invite_staff):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    res = client.post(
        "/api/services",
        json={"name": "Beard trim", "price": 10, "duration_minutes": 30},
        headers=auth(staff["token"]),
    )
    assert res.status_code == 403


def test_staff_sees_only_bookings_assigned_to_them(client, make_business, make_booking, invite_staff):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    mine = make_booking(biz["id"], customer_email="a@wavebook.com")
    make_booking(biz["id"], customer_email="b@wavebook.com")
    res = client.patch(
        f"/api/bookings/{mine}/assign",
        json={"staff_id": staff["staff_id"]},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200, res.text
    assert res.json()["assigned_staff_name"] == "Sam Staff"

    rows = client.get("/api/bookings/mine", headers=auth(staff["token"])).json()
    assert [r["id"] for r in rows] == [mine]
    assert "service_price" not in rows[0]
    assert "payment_status" not in rows[0]
    assert "customer_email" not in rows[0]

    owner_rows = client.get("/api/bookings", headers=auth(biz["owner_token"])).json()
    assigned = next(r for r in owner_rows if r["id"] == mine)
    assert assigned["assigned_staff_name"] == "Sam Staff"


def test_assignment_emails_staff_once(client, make_business, make_booking, invite_staff, sent):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    booking_id = make_booking(biz["id"])
    baseline = len(sent)
    url = f"/api/bookings/{booking_id}/assign"
    client.patch(url, json={"staff_id": staff["staff_id"]}, headers=auth(biz["owner_token"]))
    assert len(sent) == baseline + 1
    assert sent[-1]["to"] == "sam@wavebook.com"
    assert "assigned to you" in sent[-1]["subject"]
    client.patch(url, json={"staff_id": staff["staff_id"]}, headers=auth(biz["owner_token"]))
    assert len(sent) == baseline + 1


def test_unassign_returns_booking_to_owner(client, make_business, make_booking, invite_staff):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    booking_id = make_booking(biz["id"])
    url = f"/api/bookings/{booking_id}/assign"
    client.patch(url, json={"staff_id": staff["staff_id"]}, headers=auth(biz["owner_token"]))
    res = client.patch(url, json={"staff_id": None}, headers=auth(biz["owner_token"]))
    assert res.status_code == 200
    assert res.json()["assigned_staff_name"] is None
    assert client.get("/api/bookings/mine", headers=auth(staff["token"])).json() == []


def test_basic_owner_cannot_assign_bookings(client, make_business, make_booking):
    biz = make_business("basicco", plan="basic_monthly")
    booking_id = make_booking(biz["id"])
    res = client.patch(
        f"/api/bookings/{booking_id}/assign",
        json={"staff_id": 1},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 403
    assert "Premium" in res.json()["detail"]


def test_staff_cannot_assign_bookings(client, make_business, make_booking, invite_staff):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    booking_id = make_booking(biz["id"])
    res = client.patch(
        f"/api/bookings/{booking_id}/assign",
        json={"staff_id": staff["staff_id"]},
        headers=auth(staff["token"]),
    )
    assert res.status_code == 403


def test_cannot_assign_staff_from_another_business(client, make_business, make_booking, invite_staff):
    biz_a = make_business("premiumco", plan="premium_monthly")
    biz_b = make_business("otherco", plan="premium_monthly")
    staff = invite_staff(biz_a)
    booking_id = make_booking(biz_b["id"])
    res = client.patch(
        f"/api/bookings/{booking_id}/assign",
        json={"staff_id": staff["staff_id"]},
        headers=auth(biz_b["owner_token"]),
    )
    assert res.status_code == 404


def test_lapsed_business_blocks_staff(client, make_business, make_booking, invite_staff):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    booking_id = make_booking(biz["id"])
    client.patch(
        f"/api/bookings/{booking_id}/assign",
        json={"staff_id": staff["staff_id"]},
        headers=auth(biz["owner_token"]),
    )
    conn = database.get_connection()
    try:
        conn.execute("UPDATE businesses SET subscription_status = 'cancelled' WHERE id = ?", (biz["id"],))
        conn.commit()
    finally:
        conn.close()
    res = client.get("/api/bookings/mine", headers=auth(staff["token"]))
    assert res.status_code == 403
    assert "plan" in res.json()["detail"]
    assert client.get("/api/auth/me", headers=auth(staff["token"])).status_code == 200


def test_staff_can_change_password(client, make_business, invite_staff):
    biz = make_business("premiumco", plan="premium_monthly")
    staff = invite_staff(biz)
    wrong = client.post(
        "/api/auth/change-password",
        json={"current_password": "not-the-password", "new_password": "NewPass123"},
        headers=auth(staff["token"]),
    )
    assert wrong.status_code == 400
    ok = client.post(
        "/api/auth/change-password",
        json={"current_password": staff["password"], "new_password": "NewPass123"},
        headers=auth(staff["token"]),
    )
    assert ok.status_code == 200
    old_login = client.post("/api/auth/login", json={"email": staff["email"], "password": staff["password"]})
    assert old_login.status_code == 401
    new_login = client.post("/api/auth/login", json={"email": staff["email"], "password": "NewPass123"})
    assert new_login.status_code == 200


def test_owner_can_change_password(client, make_business):
    biz = make_business("premiumco", plan="premium_monthly")
    res = client.post(
        "/api/auth/change-password",
        json={"current_password": "ownerpass1", "new_password": "OwnerNew123"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 200
    login = client.post("/api/auth/login", json={"email": biz["owner_email"], "password": "OwnerNew123"})
    assert login.status_code == 200


def test_change_password_rejects_short_new_password(client, make_business):
    biz = make_business("premiumco", plan="premium_monthly")
    res = client.post(
        "/api/auth/change-password",
        json={"current_password": "ownerpass1", "new_password": "short"},
        headers=auth(biz["owner_token"]),
    )
    assert res.status_code == 422
