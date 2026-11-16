"""Stripe payment helpers (hosted Checkout Sessions).

Replaces the Flutterwave hosted-payment flow:
1. create_checkout_session() -> POST /v1/checkout/sessions
                                returns a hosted checkout URL to redirect to.
2. retrieve_checkout_session() -> GET /v1/checkout/sessions/{id}
                                confirms the payment after the customer returns.
3. Webhook events (checkout.session.completed) confirm payments asynchronously
   when the customer does not return to the success URL.
"""

import logging

import stripe
from fastapi import HTTPException

from ..config import settings

logger = logging.getLogger("wavebook")


def _configure() -> None:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured yet")
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(
    *,
    tx_ref: str,
    amount: float,
    currency: str,
    success_url: str,
    cancel_url: str,
    customer_email: str,
    metadata: dict,
    title: str,
    description: str,
) -> str:
    """Create a hosted Stripe Checkout Session and return its URL."""
    _configure()
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": (currency or settings.STRIPE_CURRENCY).lower(),
                        "unit_amount": int(round(amount * 100)),
                        "product_data": {
                            "name": title,
                            "description": description,
                        },
                    },
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=customer_email or None,
            metadata={"tx_ref": tx_ref, **metadata},
            payment_intent_data={"metadata": {"tx_ref": tx_ref, **metadata}},
        )
    except stripe.error.PermissionError as exc:
        logger.error("Stripe checkout permission error: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Stripe key lacks permission to create checkouts — grant Checkout Sessions write access",
        )
    except stripe.error.StripeError as exc:
        logger.error("Stripe checkout error: %s", exc)
        raise HTTPException(status_code=400, detail="Payment initialization failed")
    if not session.get("url"):
        raise HTTPException(status_code=400, detail="Payment initialization failed")
    return session["url"]


def retrieve_checkout_session(session_id: str) -> dict:
    """Retrieve a Checkout Session and return its data dict."""
    _configure()
    try:
        return stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as exc:
        logger.error("Stripe session retrieve error: %s", exc)
        raise HTTPException(status_code=400, detail="Payment verification failed")


def construct_webhook_event(payload: bytes, sig_header: str) -> dict:
    """Verify the Stripe webhook signature and parse the event."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")
    _configure()
    try:
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError as exc:
        logger.warning("Stripe webhook signature invalid: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature")


def session_to_data(session: dict) -> dict:
    """Normalize a Checkout Session into the shape used by the verify helpers.

    Mirrors the Flutterwave transaction dict so the existing apply-payment
    helpers can be reused unchanged.
    """
    meta = dict(session.get("metadata") or {})
    return {
        "status": "successful" if session.get("payment_status") == "paid" else "unpaid",
        "tx_ref": meta.get("tx_ref", ""),
        "amount": float(session.get("amount_total") or 0) / 100,
        "currency": (session.get("currency") or settings.STRIPE_CURRENCY).upper(),
        "id": session.get("id", ""),
        "meta": meta,
    }
