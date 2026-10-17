import secrets

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..database import get_connection, row_to_dict
from ..routers.notifications import add_notification
from ..schemas import PaymentIntentCreate
from ..services import flutterwave
from ..services.notifier import send_booking_confirmation_sms

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("/init")
def init_payment(data: PaymentIntentCreate):
    """Create a Flutterwave payment link for a booking deposit.

    Public endpoint — called from the tenant booking page after a booking is
    created, so the customer can pay the deposit by card.
    """
    conn = get_connection()
    try:
        booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (data.booking_id,)).fetchone()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        if booking["payment_status"] == "paid":
            raise HTTPException(status_code=400, detail="This booking is already paid")

        business = conn.execute(
            "SELECT * FROM businesses WHERE id = ?", (booking["business_id"],)
        ).fetchone()
        service = conn.execute(
            "SELECT * FROM services WHERE id = ?", (booking["service_id"],)
        ).fetchone()

        deposit = float(business["deposit_amount"] or 0)
        price = float(service["price"] or 0)
        amount = min(deposit, price) if deposit > 0 else 0.0
        if amount <= 0:
            raise HTTPException(status_code=400, detail="No payment is required for this booking")

        tx_ref = f"WB-BK-{booking['id']}-{secrets.token_hex(4)}"
        payment_link = flutterwave.create_payment_link(
            tx_ref=tx_ref,
            amount=amount,
            currency=settings.FLW_CURRENCY,
            redirect_url=f"{settings.API_PUBLIC_URL}/pay/verify",
            customer_email=booking["customer_email"] or "",
            meta={
                "booking_id": str(booking["id"]),
                "business_id": str(business["id"]),
                "type": "booking_deposit",
            },
            title="WaveBook Deposit",
            description=f"{service['name']} deposit for {business['name']}",
        )
        conn.execute(
            "UPDATE bookings SET payment_intent_id = ?, payment_status = 'pending' WHERE id = ?",
            (tx_ref, booking["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "payment_link": payment_link,
        "amount": amount,
        "currency": settings.FLW_CURRENCY.upper(),
    }


@router.get("/verify")
def verify_payment(tx_ref: str, transaction_id: str):
    """Verify a Flutterwave deposit payment and confirm the booking.

    Flutterwave redirects the customer here after paying on the hosted page.
    """
    data = flutterwave.verify_transaction(transaction_id)

    if data.get("status") != "successful":
        raise HTTPException(status_code=400, detail="Payment was not successful")
    if data.get("tx_ref") != tx_ref:
        raise HTTPException(status_code=400, detail="Transaction reference mismatch")

    booking_id = 0
    if tx_ref.startswith("WB-BK-"):
        try:
            booking_id = int(tx_ref.split("-")[1])
        except (IndexError, ValueError):
            booking_id = 0
    if not booking_id:
        raise HTTPException(status_code=400, detail="Invalid payment reference")

    conn = get_connection()
    try:
        booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        expected = float(data.get("meta", {}).get("charged_amount") or 0)
        paid = float(data.get("amount") or 0)
        if expected and paid < expected:
            raise HTTPException(status_code=400, detail="Payment amount does not match")

        conn.execute(
            "UPDATE bookings SET payment_status = 'paid', status = 'confirmed' WHERE id = ?",
            (booking_id,),
        )
        conn.execute(
            "INSERT INTO payments (business_id, booking_id, stripe_payment_intent_id, amount, currency, status, method) "
            "VALUES (?, ?, ?, ?, ?, 'paid', 'card')",
            (
                booking["business_id"],
                booking_id,
                data.get("id", ""),
                paid,
                data.get("currency") or settings.FLW_CURRENCY.upper(),
            ),
        )
        business = conn.execute(
            "SELECT * FROM businesses WHERE id = ?", (booking["business_id"],)
        ).fetchone()
        add_notification(
            conn,
            booking["business_id"],
            "Payment received",
            f"{booking['customer_name']} paid for {booking['service_name']} on {booking['date']} at {booking['time']}",
            booking_id,
            type_="payment",
        )
        conn.commit()
        # Send the customer a confirmation text
        send_booking_confirmation_sms(row_to_dict(booking), row_to_dict(business))
    finally:
        conn.close()
    return {"status": "paid", "booking_id": booking_id}
