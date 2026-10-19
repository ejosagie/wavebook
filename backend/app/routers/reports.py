from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_connection, row_to_dict
from ..deps import get_current_business

router = APIRouter(prefix="/api/reports", tags=["reports"])

PERIODS = {
    "today": "date('now')",
    "week": "date('now', '-6 days')",
    "month": "date('now', 'start of month')",
    "year": "date('now', 'start of year')",
}


@router.get("/financials")
def financials(
    period: str = Query(default="today"),
    business: dict = Depends(get_current_business),
):
    if period not in PERIODS:
        raise HTTPException(status_code=422, detail="Period must be today, week, month or year")
    since = PERIODS[period]
    conn = get_connection()
    try:
        booking_row = conn.execute(
            f"""SELECT COUNT(*) AS count, COALESCE(SUM(service_price), 0) AS amount
                FROM bookings
                WHERE business_id = ? AND status != 'cancelled' AND created_at >= {since}""",
            (business["id"],),
        ).fetchone()
        deposit_row = conn.execute(
            f"""SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount
                FROM payments
                WHERE business_id = ? AND status = 'paid' AND booking_id IS NOT NULL AND created_at >= {since}""",
            (business["id"],),
        ).fetchone()
        order_row = conn.execute(
            f"""SELECT COUNT(*) AS count, COALESCE(SUM(total), 0) AS amount
                FROM orders
                WHERE business_id = ? AND status != 'cancelled' AND created_at >= {since}""",
            (business["id"],),
        ).fetchone()
    finally:
        conn.close()
    bookings = row_to_dict(booking_row)
    deposits = row_to_dict(deposit_row)
    orders = row_to_dict(order_row)
    return {
        "period": period,
        "currency": business.get("currency") or "GBP",
        "bookings_count": bookings["count"],
        "bookings_amount": round(bookings["amount"], 2),
        "deposits_count": deposits["count"],
        "deposits_amount": round(deposits["amount"], 2),
        "orders_count": orders["count"],
        "orders_amount": round(orders["amount"], 2),
    }
