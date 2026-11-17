import json
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import settings
from ..database import get_connection, row_to_dict
from ..deps import get_current_business, require_owner
from ..routers.notifications import add_notification
from ..schemas import PaymentIntentCreate
from ..services import stripepay
from ..services.emailer import send_order_paid_emails, send_owner_new_booking_email
from ..services.invoice import create_invoice, send_invoice_email
from ..services.notifier import send_business_sms

router = APIRouter(prefix="/api/payments", tags=["payments"])
webhook_router = APIRouter(tags=["webhooks"])

logger = logging.getLogger("wavebook")


@router.post("/init")
def init_payment(data: PaymentIntentCreate):
    """Create a Stripe Checkout Session for a booking deposit.

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
        if "online_payments_enabled" in business.keys() and not business["online_payments_enabled"]:
            raise HTTPException(status_code=400, detail="Online payments are disabled for this business")

        deposit = float(business["deposit_amount"] or 0)
        price = float(booking["service_price"] or 0)
        amount = min(deposit, price) if deposit > 0 else 0.0
        if amount <= 0:
            raise HTTPException(status_code=400, detail="No payment is required for this booking")

        tx_ref = f"WB-BK-{booking['id']}-{secrets.token_hex(4)}"
        payment_link = stripepay.create_checkout_session(
            tx_ref=tx_ref,
            amount=amount,
            currency=business["currency"],
            success_url=f"{settings.API_PUBLIC_URL}/pay/verify?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.API_PUBLIC_URL}/t/{business['slug']}/booking/{booking['id']}/paid",
            customer_email=booking["customer_email"] or "",
            metadata={
                "booking_id": str(booking["id"]),
                "business_id": str(business["id"]),
                "type": "booking_deposit",
            },
            title="WaveBook Deposit",
            description=f"{booking['service_name']} deposit for {business['name']}",
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
        "currency": business["currency"].upper(),
    }


@router.get("/verify")
def verify_payment(tx_ref: str = "", session_id: str = ""):
    """Verify a Stripe Checkout Session and apply it (booking deposit, storefront order or SMS top-up).

    Stripe redirects the customer to the success URL with ?session_id=...;
    the payment is applied here and again via the webhook (idempotently).
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")
    session = stripepay.retrieve_checkout_session(session_id)
    data = stripepay.session_to_data(session)
    if data["status"] != "successful":
        raise HTTPException(status_code=400, detail="Payment was not successful")
    tx_ref = data["tx_ref"]

    if tx_ref.startswith("WB-BK-"):
        return _verify_booking(tx_ref, data)
    if tx_ref.startswith("WB-ORD-"):
        return _verify_order(tx_ref, data)
    if tx_ref.startswith("WB-SMS-"):
        return _verify_sms_topup(tx_ref, data)
    raise HTTPException(status_code=400, detail="Invalid payment reference")


def apply_checkout_session(session: dict) -> dict:
    """Apply a paid Stripe Checkout Session to the matching booking/order/SMS top-up.

    Shared by the webhook handler and the success-URL redirect so a payment is
    never applied twice (each helper is idempotent).
    """
    data = stripepay.session_to_data(session)
    if data["status"] != "successful":
        raise HTTPException(status_code=400, detail="Payment was not successful")
    tx_ref = data["tx_ref"]
    if tx_ref.startswith("WB-BK-"):
        return _verify_booking(tx_ref, data)
    if tx_ref.startswith("WB-ORD-"):
        return _verify_order(tx_ref, data)
    if tx_ref.startswith("WB-SMS-"):
        return _verify_sms_topup(tx_ref, data)
    if tx_ref.startswith("WB-SUB-"):
        from .subscription import activate_subscription

        return activate_subscription(tx_ref, data)
    raise HTTPException(status_code=400, detail="Invalid payment reference")


@webhook_router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook: confirm checkout sessions and subscription renewals asynchronously."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    event = stripepay.construct_webhook_event(payload, sig_header)
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object") or {}
    if event_type == "checkout.session.completed":
        try:
            apply_checkout_session(obj)
        except HTTPException as exc:
            logger.warning("Stripe webhook apply failed: %s", exc.detail)
    elif event_type == "invoice.paid":
        from .subscription import renew_subscription

        renew_subscription(obj)
    elif event_type == "invoice.payment_failed":
        from .subscription import mark_subscription_past_due

        mark_subscription_past_due(obj)
    elif event_type == "customer.subscription.deleted":
        from .subscription import cancel_subscription

        cancel_subscription(obj)
    return {"received": True}


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
        deposit = float(business["deposit_amount"] or 0)
        price = float(booking["service_price"] or 0)
        expected = min(deposit, price) if deposit > 0 else 0.0
        paid = float(data.get("amount") or 0)
        if expected and paid < expected:
            raise HTTPException(status_code=400, detail="Payment amount does not match")

        conn.execute(
            "UPDATE bookings SET payment_status = 'paid' WHERE id = ?",
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
                data.get("currency") or settings.STRIPE_CURRENCY.upper(),
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
        # In automatic mode the owner is only notified once the deposit is paid
        add_notification(
            conn,
            booking["business_id"],
            "New booking received",
            f"{booking['customer_name']} booked {booking['service_name']} on {booking['date']} at {booking['time']}",
            booking_id,
        )
        conn.commit()
        booking_data = row_to_dict(booking)
        business_data = row_to_dict(business)
        # Generate and email a formal PDF invoice (total, deposit paid, balance due)
        invoice = create_invoice(conn, booking_data, business_data, paid)
        send_invoice_email(invoice, booking_data, business_data)
    finally:
        conn.close()
    # Alert the owner by text and email that the booking is now paid and pending
    if business_data.get("contact_phone"):
        send_business_sms(
            business_data,
            business_data["contact_phone"],
            f"New booking: {booking_data['customer_name']} booked {booking_data['service_name']} "
            f"on {booking_data['date']} at {booking_data['time']} ({business_data['name']}). "
            f"Ref: {booking_data.get('reference', booking_id)}",
        )
    send_owner_new_booking_email(booking_data, business_data)
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
                data.get("currency") or settings.STRIPE_CURRENCY.upper(),
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
                data.get("currency") or settings.STRIPE_CURRENCY.upper(),
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
    """Create a Stripe Checkout Session to buy another 50 SMS credits for £5."""
    tx_ref = f"WB-SMS-{business['id']}-{secrets.token_hex(4)}"
    payment_link = stripepay.create_checkout_session(
        tx_ref=tx_ref,
        amount=settings.SMS_TOPUP_PRICE_GBP,
        currency=settings.STRIPE_CURRENCY,
        success_url=f"{settings.API_PUBLIC_URL}/pay/verify?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.API_PUBLIC_URL}/subscribe/cancel",
        customer_email=user["email"],
        metadata={
            "business_id": str(business["id"]),
            "type": "sms_topup",
        },
        title="WaveBook SMS Credits",
        description=f"50 SMS credits for {business['name']}",
    )
    return {"payment_link": payment_link}
