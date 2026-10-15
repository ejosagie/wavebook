from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import settings
from ..database import get_connection, row_to_dict
from ..routers.notifications import add_notification
from ..schemas import PaymentIntentCreate
from ..services.notifier import send_booking_confirmation_sms

router = APIRouter(prefix="/api/payments", tags=["payments"])


def _stripe():
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured yet")
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


@router.post("/intent")
def create_payment_intent(data: PaymentIntentCreate):
    """Create a Stripe PaymentIntent for a booking deposit.

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

        stripe = _stripe()
        intent = stripe.PaymentIntent.create(
            amount=int(round(amount * 100)),
            currency=settings.STRIPE_CURRENCY,
            metadata={
                "booking_id": str(booking["id"]),
                "business_id": str(business["id"]),
            },
            automatic_payment_methods={"enabled": True},
        )
        conn.execute(
            "UPDATE bookings SET payment_intent_id = ?, payment_status = 'pending' WHERE id = ?",
            (intent.id, booking["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "client_secret": intent.client_secret,
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "amount": amount,
        "currency": settings.STRIPE_CURRENCY.upper(),
    }


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe events: mark bookings paid/confirmed when payment succeeds."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid signature") from exc

    conn = get_connection()
    try:
        if event["type"] == "payment_intent.succeeded":
            intent = event["data"]["object"]
            booking_id = int(intent.get("metadata", {}).get("booking_id") or 0)
            if booking_id:
                booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
                if booking:
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
                            intent.get("id", ""),
                            float(intent.get("amount", 0)) / 100,
                            settings.STRIPE_CURRENCY.upper(),
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
        elif event["type"] == "payment_intent.payment_failed":
            intent = event["data"]["object"]
            booking_id = int(intent.get("metadata", {}).get("booking_id") or 0)
            if booking_id:
                conn.execute(
                    "UPDATE bookings SET payment_status = 'failed' WHERE id = ?", (booking_id,)
                )
                conn.commit()
    finally:
        conn.close()
    return {"received": True}
