"""Flutterwave payment helpers (card payments via the Flutterwave API).

Mirrors the flow used by the legacy PHP prototype (fluttermethod/):
1. create_payment_link()  -> POST https://api.flutterwave.com/v3/payments
                             returns a hosted payment page URL to redirect to.
2. verify_transaction()   -> GET https://api.flutterwave.com/v3/transactions/{id}/verify
                             confirms the payment after the customer returns.
"""

from fastapi import HTTPException

from ..config import settings

FLW_API = "https://api.flutterwave.com/v3"


def _headers() -> dict:
    if not settings.FLW_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Flutterwave is not configured yet")
    return {
        "Authorization": f"Bearer {settings.FLW_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def create_payment_link(
    *,
    tx_ref: str,
    amount: float,
    currency: str,
    redirect_url: str,
    customer_email: str,
    meta: dict,
    title: str,
    description: str,
) -> str:
    """Create a hosted Flutterwave payment link and return its URL."""
    import requests

    payload = {
        "tx_ref": tx_ref,
        "amount": str(amount),
        "currency": currency,
        "country": settings.FLW_COUNTRY,
        "redirect_url": redirect_url,
        "customer": {"email": customer_email},
        "meta": meta,
        "customizations": {
            "title": title,
            "description": description,
            "logo": f"{settings.API_PUBLIC_URL}/static/img/icon.png",
        },
    }
    try:
        resp = requests.post(
            f"{FLW_API}/payments",
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        import logging

        logging.getLogger("wavebook").error(
            "FLW status=%s headers=%r body=%r",
            resp.status_code,
            dict(resp.headers),
            resp.text[:800],
        )
        result = resp.json()
    except requests.RequestException as exc:
        import logging

        logging.getLogger("wavebook").exception("Flutterwave request failed")
        raise HTTPException(status_code=502, detail="Could not reach Flutterwave") from exc

    if result.get("status") != "success" or not result.get("data", {}).get("link"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message") or "Payment initialization failed",
        )
    return result["data"]["link"]


def verify_transaction(transaction_id: str) -> dict:
    """Verify a Flutterwave transaction and return its data dict."""
    import requests

    try:
        resp = requests.get(
            f"{FLW_API}/transactions/{transaction_id}/verify",
            headers=_headers(),
            timeout=30,
        )
        result = resp.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Could not reach Flutterwave") from exc

    data = result.get("data") or {}
    if result.get("status") != "success" or not data:
        raise HTTPException(status_code=400, detail="Payment verification failed")
    return data
