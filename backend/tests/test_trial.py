from datetime import date, timedelta

from app import database
from app.config import settings
from app.security import create_admin_token
from app.services import emailer
from conftest import auth


def _set_trial(business_id, status, trial_ends_at):
    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET subscription_status = ?, trial_ends_at = ? WHERE id = ?",
            (status, trial_ends_at, business_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_default_trial_is_seven_days(client, make_business):
    assert settings.TRIAL_DAYS == 7
    assert database.get_trial_days() == 7
    biz = make_business("trialco")
    _set_trial(biz["id"], "trial", (date.today() + timedelta(days=7)).isoformat())
    body = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert body["status"] == "trial"
    assert body["trial_days"] == 7
    assert body["trial_days_left"] == 7
    assert body["max_staff"] == settings.MAX_STAFF


def test_trial_is_still_running_the_day_before_it_ends(client, make_business):
    biz = make_business("lastday")
    _set_trial(biz["id"], "trial", (date.today() + timedelta(days=1)).isoformat())
    body = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert body["status"] == "trial"
    assert body["trial_days_left"] == 1


def test_trial_expires_on_its_end_date(client, make_business):
    biz = make_business("endco")
    _set_trial(biz["id"], "trial", date.today().isoformat())
    body = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert body["status"] == "expired"
    assert body["trial_days_left"] == 0
    assert body["max_staff"] == 0


def test_expired_trial_loses_staff_and_assignment(client, make_business, make_booking, invite_staff):
    biz = make_business("lapsedco", plan="premium_monthly")
    staff = invite_staff(biz)
    booking_id = make_booking(biz["id"])
    _set_trial(biz["id"], "trial", (date.today() - timedelta(days=1)).isoformat())
    assign = client.patch(
        f"/api/bookings/{booking_id}/assign",
        json={"staff_id": staff["staff_id"]},
        headers=auth(biz["owner_token"]),
    )
    assert assign.status_code == 403
    assert client.get("/api/bookings/mine", headers=auth(staff["token"])).status_code == 403


def test_admin_changes_trial_length(client, make_business):
    client.cookies.set("wavebook_admin", create_admin_token())
    res = client.post("/admin/trial-days", data={"trial_days": "10"}, follow_redirects=False)
    assert res.status_code == 303
    assert database.get_trial_days() == 10

    biz = make_business("tencoed")
    _set_trial(biz["id"], "trial", (date.today() + timedelta(days=10)).isoformat())
    body = client.get("/api/subscription", headers=auth(biz["owner_token"])).json()
    assert body["trial_days"] == 10
    assert body["trial_days_left"] == 10


def test_admin_rejects_out_of_range_trial_length(client):
    client.cookies.set("wavebook_admin", create_admin_token())
    client.post("/admin/trial-days", data={"trial_days": "10"}, follow_redirects=False)
    for bad in ("0", "91"):
        client.post("/admin/trial-days", data={"trial_days": bad}, follow_redirects=False)
        assert database.get_trial_days() == 10


def test_trial_days_control_is_on_admin_dashboard(client):
    client.cookies.set("wavebook_admin", create_admin_token())
    page = client.get("/admin")
    assert page.status_code == 200
    assert 'name="trial_days"' in page.text
    assert 'value="7"' in page.text


def test_landing_page_quotes_trial_length_and_premium_price(client):
    text = client.get("/").text
    assert "Start Your 7-Day Free Trial" in text
    assert "£19.99" in text
    assert "£14.99" not in text


def test_premium_monthly_is_nineteen_ninety_nine():
    assert settings.SUBSCRIPTION_PLANS["premium_monthly"]["price"] == 19.99
    assert settings.SUBSCRIPTION_PRICE_GBP == 19.99


def test_welcome_email_quotes_trial_length(sent):
    emailer.send_welcome_email("new@wavebook.com", "New Owner")
    assert sent[-1]["subject"] == "Welcome to WaveBook — your 7-day free trial is active"
    assert "7-day free trial" in sent[-1]["body"]
