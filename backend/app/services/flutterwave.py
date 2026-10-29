"""Flutterwave payment helpers (card payments via the Flutterwave API).

Mirrors the flow used by the legacy PHP prototype (fluttermethod/):
1. create_payment_link()  -> POST https://api.flutterwave.com/v3/payments
                             returns a hosted payment page URL to redirect to.
2. verify_transaction()   -> GET https://api.flutterwave.com/v3/transactions/{id}/verify
                             confirms the payment after the customer returns.
"""

import logging
import time

from fastapi import HTTPException

from ..config import settings

FLW_API = "https://api.flutterwave.com/v3"
FLW_USER_AGENT = "WaveBook/1.0 (+https://getwavebook.com)"
MAX_RETRIES = 3

logger = logging.getLogger("wavebook")


def _headers() -> dict:
    if not settings.FLW_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Flutterwave is not configured yet")
    return {
        "Authorization": f"Bearer {settings.FLW_SECRET_KEY}",
        "Content-Type": "application/json",
        "User-Agent": FLW_USER_AGENT,
    }


def _request(method: str, url: str, **kwargs) -> "requests.Response":
    """Request with retries and backoff for transient failures."""
    import requests

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(method, url, headers=_headers(), timeout=30, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning("FLW transient status=%s attempt=%s", resp.status_code, attempt + 1)
                time.sleep(2**attempt)
                continue
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("FLW request error attempt=%s: %s", attempt + 1, exc)
            time.sleep(2**attempt)
    raise HTTPException(status_code=502, detail="Could not reach Flutterwave") from last_exc


def _json(resp) -> dict:
    """Parse a JSON response, logging the raw body when Flutterwave returns HTML (e.g. a WAF block)."""
    try:
        return resp.json()
    except ValueError:
        logger.error("FLW non-JSON response status=%s body=%r", resp.status_code, resp.text[:500])
        raise HTTPException(status_code=502, detail="Could not reach Flutterwave")


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
    country: str | None = None,
) -> str:
    """Create a hosted Flutterwave payment link and return its URL."""
    payload = {
        "tx_ref": tx_ref,
        "amount": str(amount),
        "currency": currency,
        "country": country or settings.FLW_COUNTRY,
        "redirect_url": redirect_url,
        "customer": {"email": customer_email},
        "meta": meta,
        "customizations": {
            "title": title,
            "description": description,
            "logo": f"{settings.API_PUBLIC_URL}/static/img/icon.png",
        },
    }
    result = _json(_request("POST", f"{FLW_API}/payments", json=payload))

    if result.get("status") != "success" or not result.get("data", {}).get("link"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message") or "Payment initialization failed",
        )
    return result["data"]["link"]


def verify_transaction(transaction_id: str) -> dict:
    """Verify a Flutterwave transaction and return its data dict."""
    result = _json(_request("GET", f"{FLW_API}/transactions/{transaction_id}/verify"))

    data = result.get("data") or {}
    if result.get("status") != "success" or not data:
        raise HTTPException(status_code=400, detail="Payment verification failed")
    return data
