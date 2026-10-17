from fastapi import APIRouter, Depends, HTTPException

from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import get_current_business

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("")
def list_customers(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        rows = rows_to_dicts(
            conn.execute(
                """SELECT c.*,
                          (SELECT COUNT(*) FROM bookings b WHERE b.business_id = c.business_id
                           AND ((b.customer_email != '' AND b.customer_email = c.email)
                                OR (b.customer_phone != '' AND b.customer_phone = c.phone))) AS booking_count
                   FROM customers c WHERE c.business_id = ? ORDER BY c.created_at DESC""",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return rows


@router.get("/{customer_id}/bookings")
def customer_bookings(customer_id: int, business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        customer = conn.execute(
            "SELECT * FROM customers WHERE id = ? AND business_id = ?", (customer_id, business["id"])
        ).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        rows = rows_to_dicts(
            conn.execute(
                """SELECT * FROM bookings WHERE business_id = ?
                   AND ((customer_email != '' AND customer_email = ?)
                        OR (customer_phone != '' AND customer_phone = ?))
                   ORDER BY date DESC""",
                (business["id"], customer["email"], customer["phone"]),
            ).fetchall()
        )
    finally:
        conn.close()
    return rows
