import json
import secrets

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..database import get_connection, row_to_dict
from ..deps import get_current_business, require_owner
from ..routers.notifications import add_notification
from ..schemas import PaymentIntentCreate
from ..services import flutterwave
from ..services.emailer import send_booking_confirmation_email, send_order_paid_emails
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
    """Verify a Flutterwave payment and apply it (booking deposit, storefront order or SMS top-up).

    Flutterwave redirects the customer here after paying on the hosted page.
    """
    data = flutterwave.verify_transaction(transaction_id)

    if data.get("status") != "successful":
        raise HTTPException(status_code=400, detail="Payment was not successful")
    if data.get("tx_ref") != tx_ref:
        raise HTTPException(status_code=400, detail="Transaction reference mismatch")

    if tx_ref.startswith("WB-BK-"):
        return _verify_booking(tx_ref, data)
    if tx_ref.startswith("WB-ORD-"):
        return _verify_order(tx_ref, data)
    if tx_ref.startswith("WB-SMS-"):
        return _verify_sms_topup(tx_ref, data)
    raise HTTPException(status_code=400, detail="Invalid payment reference")


def _verify_booking(tx_ref: str, data: dict) -> dict:
    try:
        booking_id = int(tx_ref.split("-")[2])
    except (IndexError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payment reference")

    conn = get_connection()
    try:
        booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        if booking["payment_status"] == "paid":
            return {"status": "paid", "booking_id": booking_id}

        business = conn.execute(
            "SELECT * FROM businesses WHERE id = ?", (booking["business_id"],)
        ).fetchone()
        service = conn.execute(
            "SELECT * FROM services WHERE id = ?", (booking["service_id"],)
        ).fetchone()
        deposit = float(business["deposit_amount"] or 0)
        price = float(service["price"] or 0)
        expected = min(deposit, price) if deposit > 0 else 0.0
        paid = float(data.get("amount") or 0)
        if expected and paid < expected:
            raise HTTPException(status_code=400, detail="Payment amount does not match")

        conn.execute(
            "UPDATE bookings SET payment_status = 'paid', status = 'confirmed' WHERE id = ?",
            (booking_id,),
        )
        conn.execute(
            "INSERT INTO payments (business_id, booking_id, stripe_payment_intent_id, amount, currency, kind, status, method) "
            "VALUES (?, ?, ?, ?, ?, 'deposit', 'paid', 'card')",
            (
                booking["business_id"],
                booking_id,
                data.get("id", ""),
                paid,
                data.get("currency") or settings.FLW_CURRENCY.upper(),
            ),
        )
        add_notification(
            conn,
            booking["business_id"],
            "Payment received",
            f"{booking['customer_name']} paid for {booking['service_name']} on {booking['date']} at {booking['time']}",
            booking_id,
            type_="payment",
        )
        conn.commit()
        booking_data = row_to_dict(booking)
        business_data = row_to_dict(business)
        # Send the customer a confirmation text
        send_booking_confirmation_sms(booking_data, business_data)
    finally:
        conn.close()
    send_booking_confirmation_email(booking_data, business_data)
    return {"status": "paid", "booking_id": booking_id}


def _verify_order(tx_ref: str, data: dict) -> dict:
    try:
        order_id = int(tx_ref.split("-")[2])
    except (IndexError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payment reference")

    conn = get_connection()
    try:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order["status"] == "paid":
            return {"status": "paid", "order_id": order_id}

        paid = float(data.get("amount") or 0)
        if paid < float(order["total"] or 0):
            raise HTTPException(status_code=400, detail="Payment amount does not match")

        conn.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order_id,))
        conn.execute(
            "INSERT INTO payments (business_id, booking_id, stripe_payment_intent_id, amount, currency, kind, status, method) "
            "VALUES (?, NULL, ?, ?, ?, 'order', 'paid', 'card')",
            (
                order["business_id"],
                data.get("id", ""),
                paid,
                data.get("currency") or settings.FLW_CURRENCY.upper(),
            ),
        )
        items = json.loads(order["items"] or "[]")
        summary = ", ".join(f"{i.get('name', 'item')} x{i.get('quantity', 1)}" for i in items)
        add_notification(
            conn,
            order["business_id"],
            "Store order paid",
            f"{order['customer_name']} ordered {summary} — total £{order['total']:.2f}",
            type_="payment",
        )
        conn.commit()
        order_data = row_to_dict(order)
        business = row_to_dict(
            conn.execute("SELECT * FROM businesses WHERE id = ?", (order["business_id"],)).fetchone()
        )
    finally:
        conn.close()
    send_order_paid_emails(order_data, business)
    return {"status": "paid", "order_id": order_id}


def _verify_sms_topup(tx_ref: str, data: dict) -> dict:
    try:
        business_id = int(tx_ref.split("-")[2])
    except (IndexError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payment reference")

    conn = get_connection()
    try:
        business = conn.execute("SELECT * FROM businesses WHERE id = ?", (business_id,)).fetchone()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        # Idempotency: never credit the same Flutterwave transaction twice
        existing = conn.execute(
            "SELECT id FROM payments WHERE stripe_payment_intent_id = ?", (data.get("id", ""),)
        ).fetchone()
        if existing:
            return {"status": "paid", "business_id": business_id}

        paid = float(data.get("amount") or 0)
        if paid < settings.SMS_TOPUP_PRICE_GBP:
            raise HTTPException(status_code=400, detail="Payment amount does not match")

        conn.execute(
            "UPDATE businesses SET sms_credits = sms_credits + ? WHERE id = ?",
            (settings.SMS_TOPUP_CREDITS, business_id),
        )
        conn.execute(
            "INSERT INTO payments (business_id, booking_id, stripe_payment_intent_id, amount, currency, kind, status, method) "
            "VALUES (?, NULL, ?, ?, ?, 'sms_topup', 'paid', 'card')",
            (
                business_id,
                data.get("id", ""),
                paid,
                data.get("currency") or settings.FLW_CURRENCY.upper(),
            ),
        )
        add_notification(
            conn,
            business_id,
            "SMS credits added",
            f"Added {settings.SMS_TOPUP_CREDITS} SMS credits for £{settings.SMS_TOPUP_PRICE_GBP:.2f}.",
            type_="payment",
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "paid", "business_id": business_id}


@router.post("/sms/topup")
def sms_topup(
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    """Create a Flutterwave payment link to buy another 50 SMS credits for £5."""
    tx_ref = f"WB-SMS-{business['id']}-{secrets.token_hex(4)}"
    payment_link = flutterwave.create_payment_link(
        tx_ref=tx_ref,
        amount=settings.SMS_TOPUP_PRICE_GBP,
        currency=settings.FLW_CURRENCY,
        redirect_url=f"{settings.API_PUBLIC_URL}/pay/verify",
        customer_email=user["email"],
        meta={
            "business_id": str(business["id"]),
            "type": "sms_topup",
        },
        title="WaveBook SMS Credits",
        description=f"50 SMS credits for {business['name']}",
    )
    return {"payment_link": payment_link}
