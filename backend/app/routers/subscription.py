from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import settings
from ..database import get_connection, row_to_dict
from ..deps import get_current_business, require_owner

router = APIRouter(prefix="/api/subscription", tags=["subscription"])


def _stripe():
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured yet")
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


@router.get("")
def get_subscription(business: dict = Depends(get_current_business)):
    return {
        "status": business["subscription_status"],
        "price_gbp": settings.SUBSCRIPTION_PRICE_GBP,
        "max_staff": settings.MAX_STAFF,
    }


@router.post("/checkout")
def create_checkout_session(
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    """Create a Stripe Checkout session for the £9.99/month subscription.

    Subscription activation happens on the website only (App Store compliant).
    """
    stripe = _stripe()
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=user["email"],
            line_items=[{"price": settings.STRIPE_PRICE_ID_MONTHLY, "quantity": 1}],
            client_reference_id=str(business["id"]),
            metadata={"business_id": str(business["id"])},
            success_url=f"{settings.API_PUBLIC_URL}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.API_PUBLIC_URL}/subscribe/cancel",
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=f"Could not create checkout session: {exc}") from exc
    return {"checkout_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe subscription lifecycle events."""
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
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            business_id = int(session.get("metadata", {}).get("business_id") or session.get("client_reference_id") or 0)
            if business_id:
                conn.execute(
                    "UPDATE businesses SET subscription_status = 'active', stripe_customer_id = ?, stripe_subscription_id = ? WHERE id = ?",
                    (session.get("customer", ""), session.get("subscription", ""), business_id),
                )
                conn.execute(
                    "INSERT INTO subscriptions (business_id, stripe_subscription_id, status, plan, amount) VALUES (?, ?, 'active', 'monthly', ?)",
                    (business_id, session.get("subscription", ""), settings.SUBSCRIPTION_PRICE_GBP),
                )
        elif event["type"] == "customer.subscription.updated":
            sub = event["data"]["object"]
            status_map = {
                "active": "active",
                "past_due": "past_due",
                "unpaid": "past_due",
                "canceled": "cancelled",
                "trialing": "trial",
            }
            new_status = status_map.get(sub.get("status"), "past_due")
            conn.execute(
                "UPDATE businesses SET subscription_status = ? WHERE stripe_subscription_id = ?",
                (new_status, sub.get("id")),
            )
        elif event["type"] == "customer.subscription.deleted":
            sub = event["data"]["object"]
            conn.execute(
                "UPDATE businesses SET subscription_status = 'cancelled' WHERE stripe_subscription_id = ?",
                (sub.get("id"),),
            )
        conn.commit()
    finally:
        conn.close()
    return {"received": True}
