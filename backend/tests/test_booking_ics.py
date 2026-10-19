from app import database
from conftest import auth


def test_booking_ics_export(client, make_business, make_booking):
    biz = make_business("icsco", plan="premium_monthly")
    booking_id = make_booking(biz["id"], status="confirmed")
    res = client.get(f"/api/bookings/{booking_id}/ics", headers=auth(biz["owner_token"]))
    assert res.status_code == 200, res.text
    assert "BEGIN:VCALENDAR" in res.text
    assert "BEGIN:VEVENT" in res.text


def test_booking_ics_handles_seconds_in_time(client, make_business):
    biz = make_business("icssec", plan="premium_monthly")
    conn = database.get_connection()
    try:
        booking_id = conn.execute(
            "INSERT INTO bookings (business_id, customer_name, customer_phone, service_name, "
            "service_price, service_duration_minutes, date, time, status, reference) "
            "VALUES (?, 'Test', '07123456789', 'Cut', 20, 30, '2030-01-01', '10:00:00', 'confirmed', 'ABC123')",
            (biz["id"],),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    res = client.get(f"/api/bookings/{booking_id}/ics", headers=auth(biz["owner_token"]))
    assert res.status_code == 200, res.text
