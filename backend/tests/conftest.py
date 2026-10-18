import re

import pytest
from fastapi.testclient import TestClient

from app import database
from app.config import settings
from app.main import app
from app.security import create_access_token, hash_password
from app.services import emailer


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test.db"))
    database.init_db()
    outbox: list[dict] = []

    def fake_send(to, subject, body_text):
        outbox.append({"to": to, "subject": subject, "body": body_text})
        return {"provider": "test", "status": "sent", "to": to}

    monkeypatch.setattr(emailer, "send_email", fake_send)
    return outbox


@pytest.fixture
def client(sent):
    return TestClient(app)


@pytest.fixture
def make_business():
    def _make(slug, plan=None, status="active", contact_email="", deposit=20.0):
        conn = database.get_connection()
        try:
            bid = conn.execute(
                "INSERT INTO businesses (slug, name, subscription_status, contact_email, deposit_amount) "
                "VALUES (?, ?, ?, ?, ?)",
                (slug, f"{slug.title()} Studio", status, contact_email, deposit),
            ).lastrowid
            conn.execute(
                "INSERT INTO availability (business_id, working_days, blocked_dates, blocked_slots, slot_interval) "
                "VALUES (?, '{}', '[]', '{}', 30)",
                (bid,),
            )
            if plan:
                conn.execute(
                    "INSERT INTO subscriptions (business_id, status, plan) VALUES (?, 'active', ?)", (bid, plan)
                )
            owner_email = f"owner@{slug}.wavebook.com"
            uid = conn.execute(
                "INSERT INTO users (email, password_hash, full_name, role, business_id) "
                "VALUES (?, ?, 'Owner Test', 'owner', ?)",
                (owner_email, hash_password("ownerpass1"), bid),
            ).lastrowid
            conn.commit()
        finally:
            conn.close()
        return {
            "id": bid,
            "name": f"{slug.title()} Studio",
            "owner_id": uid,
            "owner_email": owner_email,
            "owner_token": create_access_token(uid),
        }

    return _make


@pytest.fixture
def make_service():
    def _make(business_id, price=50.0):
        conn = database.get_connection()
        try:
            sid = conn.execute(
                "INSERT INTO services (business_id, name, price, duration_minutes) VALUES (?, 'Cut', ?, 60)",
                (business_id, price),
            ).lastrowid
            conn.commit()
            return sid
        finally:
            conn.close()

    return _make


@pytest.fixture
def make_booking():
    def _make(business_id, customer_email="jane@wavebook.com", status="confirmed", service_price=50.0, staff_id=None):
        conn = database.get_connection()
        try:
            sid = conn.execute(
                "INSERT INTO services (business_id, name, price, duration_minutes) VALUES (?, 'Cut', ?, 60)",
                (business_id, service_price),
            ).lastrowid
            bid = conn.execute(
                """INSERT INTO bookings (business_id, customer_name, customer_email, customer_phone, service_id,
                       service_name, service_price, service_duration_minutes, date, time, notes, reference,
                       status, assigned_staff_id)
                   VALUES (?, 'Jane Customer', ?, '07123456789', ?, 'Cut', ?, 60, '2030-06-01', '10:00', '',
                       'REF001', ?, ?)""",
                (business_id, customer_email, sid, service_price, status, staff_id),
            ).lastrowid
            conn.commit()
            return bid
        finally:
            conn.close()

    return _make


@pytest.fixture
def invite_staff(client, sent):
    def _invite(biz, email="sam@wavebook.com", name="Sam Staff"):
        res = client.post(
            "/api/staff",
            json={"full_name": name, "email": email, "phone": ""},
            headers=auth(biz["owner_token"]),
        )
        assert res.status_code == 201, res.text
        password = re.search(r"Temporary password: (\S+)", sent[-1]["body"]).group(1)
        login = client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        return {
            "staff_id": res.json()["id"],
            "token": login.json()["access_token"],
            "password": password,
            "email": email,
        }

    return _invite
