from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import get_current_business, require_owner
from ..phone import validate_uk_phone
from ..routers.notifications import add_notification
from ..schemas import BookingCreate, BookingStatusUpdate
from ..services.notifier import send_booking_confirmation_sms
from ..services.slots import get_availability_row, get_available_time_slots, is_date_blocked

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.get("")
def list_bookings(
    business: dict = Depends(get_current_business),
    date: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
):
    query = "SELECT * FROM bookings WHERE business_id = ?"
    params: list = [business["id"]]
    if date:
        query += " AND date = ?"
        params.append(date)
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    query += " ORDER BY date DESC, time DESC"
    conn = get_connection()
    try:
        rows = rows_to_dicts(conn.execute(query, params).fetchall())
    finally:
        conn.close()
    return rows


@router.get("/slots")
def available_slots(
    date: str,
    service_id: int | None = Query(default=None),
    business: dict = Depends(get_current_business),
):
    conn = get_connection()
    try:
        availability_row = conn.execute(
            "SELECT * FROM availability WHERE business_id = ?", (business["id"],)
        ).fetchone()
        service = None
        if service_id:
            service = conn.execute(
                "SELECT * FROM services WHERE id = ? AND business_id = ?", (service_id, business["id"])
            ).fetchone()
        confirmed = conn.execute(
            "SELECT * FROM bookings WHERE business_id = ? AND date = ? AND status = 'confirmed'",
            (business["id"], date),
        ).fetchall()
    finally:
        conn.close()

    availability = get_availability_row(availability_row)
    if is_date_blocked(date, availability):
        return {"date": date, "blocked": True, "slots": []}

    duration = int(service["duration_minutes"]) if service else 60
    slots = get_available_time_slots(
        date,
        availability,
        rows_to_dicts(confirmed),
        duration,
        int(business["buffer_minutes"] or 30),
    )
    return {"date": date, "blocked": False, "slots": slots}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_booking(data: BookingCreate, business: dict = Depends(get_current_business)):
    try:
        customer_phone = validate_uk_phone(data.customer_phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    conn = get_connection()
    try:
        service = conn.execute(
            "SELECT * FROM services WHERE id = ? AND business_id = ?", (data.service_id, business["id"])
        ).fetchone()
        if not service:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

        availability_row = conn.execute(
            "SELECT * FROM availability WHERE business_id = ?", (business["id"],)
        ).fetchone()
        availability = get_availability_row(availability_row)
        if is_date_blocked(data.date, availability):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That date is not available")

        confirmed = conn.execute(
            "SELECT * FROM bookings WHERE business_id = ? AND date = ? AND status = 'confirmed'",
            (business["id"], data.date),
        ).fetchall()
        slots = get_available_time_slots(
            data.date,
            availability,
            rows_to_dicts(confirmed),
            int(service["duration_minutes"] or 60),
            int(business["buffer_minutes"] or 30),
        )
        if data.time not in slots:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That time slot is no longer available")

        cur = conn.execute(
            """INSERT INTO bookings
               (business_id, customer_name, customer_email, customer_phone, service_id,
                service_name, service_price, service_duration_minutes, date, time, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                business["id"],
                data.customer_name.strip(),
                data.customer_email.strip(),
                customer_phone,
                service["id"],
                service["name"],
                service["price"],
                service["duration_minutes"],
                data.date,
                data.time,
                data.notes.strip(),
            ),
        )
        booking_id = cur.lastrowid

        # Upsert into customer profiles (match by phone or email)
        if data.customer_email or customer_phone:
            existing = conn.execute(
                """SELECT id FROM customers WHERE business_id = ?
                   AND ((email != '' AND email = ?) OR (phone != '' AND phone = ?))
                   LIMIT 1""",
                (business["id"], data.customer_email.strip(), customer_phone),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE customers SET name = ?, email = ?, phone = ? WHERE id = ?",
                    (data.customer_name.strip(), data.customer_email.strip(), customer_phone, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO customers (business_id, name, email, phone) VALUES (?, ?, ?, ?)",
                    (business["id"], data.customer_name.strip(), data.customer_email.strip(), customer_phone),
                )
        conn.commit()
        booking = row_to_dict(conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone())
        add_notification(
            conn,
            business["id"],
            "New booking received",
            f"{data.customer_name.strip()} booked {service['name']} on {data.date} at {data.time}",
            booking_id,
        )
        conn.commit()
    finally:
        conn.close()
    return booking


@router.patch("/{booking_id}/status")
def update_booking_status(
    booking_id: int,
    data: BookingStatusUpdate,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM bookings WHERE id = ? AND business_id = ?", (booking_id, business["id"])
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        conn.execute(
            "UPDATE bookings SET status = ? WHERE id = ?", (data.status, booking_id)
        )
        conn.commit()
        booking = row_to_dict(conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone())
    finally:
        conn.close()

    # Text the customer when their booking is confirmed
    sms = None
    if data.status == "confirmed" and booking.get("customer_phone"):
        sms = send_booking_confirmation_sms(booking, business)

    return {**booking, "sms": sms}


@router.delete("/{booking_id}")
def delete_booking(
    booking_id: int,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM bookings WHERE id = ? AND business_id = ?", (booking_id, business["id"])
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return {"ok": True}
