import secrets
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from ..config import settings
from ..database import get_connection, get_trial_days, row_to_dict
from ..deps import bearer_scheme, business_tier_features, get_business_plan, get_current_business
from ..schemas import SubscriptionCheckoutRequest
from ..security import decode_access_token
from ..services import stripepay

router = APIRouter(prefix="/api/subscription", tags=["subscription"])


@router.get("")
def get_subscription(business: dict = Depends(get_current_business)):
    trial_ends = business.get("trial_ends_at") or ""
    trial_days_left = 0
    if business["subscription_status"] == "trial" and trial_ends:
        try:
            end = datetime.strptime(trial_ends, "%Y-%m-%d").date()
            trial_days_left = max(0, (end - date.today()).days)
        except ValueError:
            trial_days_left = 0
    plan_key, plan = get_business_plan(business["id"])
    plan_key = plan_key or ""
    plan = plan or {}
    conn = get_connection()
    try:
        sub_row = conn.execute(
            "SELECT stripe_subscription_id, current_period_end FROM subscriptions "
            "WHERE business_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (business["id"],),
        ).fetchone()
    finally:
        conn.close()
    auto_renew = bool(sub_row and sub_row["stripe_subscription_id"].startswith("sub_"))
    return {
        "status": business["subscription_status"],
        "plan": plan_key,
        "plan_tier": plan.get("tier", ""),
        "plan_interval": plan.get("interval", ""),
        "price_gbp": settings.SUBSCRIPTION_PRICE_GBP,
        "max_staff": business_tier_features(business)["max_staff"],
        "trial_days": get_trial_days(),
        "trial_ends_at": trial_ends,
        "trial_days_left": trial_days_left,
        "auto_renew": auto_renew,
        "current_period_end": sub_row["current_period_end"] if sub_row else "",
    }


def _resolve_business(email: str, credentials: HTTPAuthorizationCredentials | None) -> tuple[dict, str]:
    """Resolve the owner user and their business (Bearer token or account email).

    Returns (business, owner_email).
    """
    conn = get_connection()
    try:
        if credentials is not None:
            user_id = decode_access_token(credentials.credentials)
            user = (
                row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
                if user_id
                else None
            )
            if user is None:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            if user.get("role") not in ("owner", "admin"):
                raise HTTPException(status_code=403, detail="Owner access required")
        else:
            email = (email or "").strip().lower()
            if not email:
                raise HTTPException(status_code=400, detail="Email is required")
            user = row_to_dict(
                conn.execute(
                    "SELECT * FROM users WHERE email = ? AND role IN ('owner','admin')",
                    (email,),
                ).fetchone()
            )
            if user is None:
                raise HTTPException(status_code=404, detail="No account found for that email")
        if not user.get("business_id"):
            raise HTTPException(status_code=400, detail="No business linked to this account")
        business = row_to_dict(
            conn.execute("SELECT * FROM businesses WHERE id = ?", (user["business_id"],)).fetchone()
        )
    finally:
        conn.close()
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")
    return business, user["email"]


@router.post("/checkout")
def create_checkout(
    payload: SubscriptionCheckoutRequest | None = Body(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    """Create a Stripe Checkout Session for a subscription plan.

    App callers authenticate with their Bearer token; website visitors
    (no web session exists) identify their account by email instead.
    Subscription activation happens on the website only (App Store compliant).
    """
    plan_key = (payload.plan if payload else None) or "basic_monthly"
    plan = settings.SUBSCRIPTION_PLANS.get(plan_key)
    if plan is None:
        raise HTTPException(status_code=400, detail="Unknown plan")
    currency = ((payload.currency if payload else None) or "GBP").upper()
    currency_info = settings.SUBSCRIPTION_CURRENCIES.get(currency)
    if currency_info is None:
        raise HTTPException(status_code=400, detail="Unsupported currency")
    amount = round(plan["price"] * currency_info["rate"], 2)

    business, owner_email = _resolve_business(payload.email if payload else None, credentials)

    tier = settings.TIER_LABELS.get(plan["tier"], "WaveBook")
    interval_label = settings.INTERVAL_LABELS.get(plan["interval"], plan["interval"].title())
    interval, interval_count = _stripe_interval(plan["interval"])
    tx_ref = f"WB-SUB-{business['id']}-{plan_key}-{secrets.token_hex(4)}"
    payment_link = stripepay.create_subscription_checkout_session(
        tx_ref=tx_ref,
        amount=amount,
        currency=currency,
        success_url=f"{settings.API_PUBLIC_URL}/subscribe/verify?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.API_PUBLIC_URL}/subscribe/cancel",
        customer_email=owner_email,
        metadata={
            "business_id": str(business["id"]),
            "type": "subscription",
            "plan": plan_key,
            "currency": currency,
        },
        title=f"{tier} — {interval_label}",
        description=f"{interval_label} subscription for {business['name']}",
        interval=interval,
        interval_count=interval_count,
    )
    return {"payment_link": payment_link}


@router.post("/portal")
def open_portal(
    payload: SubscriptionCheckoutRequest | None = Body(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    """Open Stripe's Customer Portal so the owner can cancel or manage their subscription.

    Website visitors identify their account by email; Stripe emails them a
    magic link before the portal opens, so email alone cannot be abused.
    """
    business, _ = _resolve_business(payload.email if payload else None, credentials)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, stripe_subscription_id, stripe_customer_id FROM subscriptions "
            "WHERE business_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (business["id"],),
        ).fetchone()
    finally:
        conn.close()
    customer_id = _portal_customer_id(row)
    if not customer_id:
        raise HTTPException(status_code=400, detail="No active subscription to manage")
    url = stripepay.create_portal_session(
        customer_id,
        return_url=f"{settings.API_PUBLIC_URL}/subscribe",
    )
    return {"portal_url": url}


def _portal_customer_id(row: dict | None) -> str:
    """Return the Stripe customer id for an active subscription row.

    Older subscriptions activated before customer ids were stored have a
    stripe_subscription_id but no stripe_customer_id; resolve it from Stripe
    and persist it so the portal keeps working for them.
    """
    if not row:
        return ""
    if row["stripe_customer_id"]:
        return row["stripe_customer_id"]
    if not row["stripe_subscription_id"].startswith("sub_"):
        return ""
    customer_id = stripepay.get_subscription_customer(row["stripe_subscription_id"])
    if not customer_id:
        return ""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE subscriptions SET stripe_customer_id = ? WHERE id = ?",
            (customer_id, row["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return customer_id


@router.post("/cancel")
def cancel_my_subscription(business: dict = Depends(get_current_business)):
    """Cancel the business's recurring subscription at the end of the current period.

    The business keeps access until the paid period ends; Stripe then sends
    customer.subscription.deleted, which the webhook turns into 'cancelled'.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT stripe_subscription_id, current_period_end FROM subscriptions "
            "WHERE business_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (business["id"],),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["stripe_subscription_id"].startswith("sub_"):
        raise HTTPException(status_code=400, detail="No recurring subscription to cancel")
    stripepay.cancel_subscription(row["stripe_subscription_id"])
    return {"status": "cancelling", "current_period_end": row["current_period_end"]}


def _stripe_interval(plan_interval: str) -> tuple[str, int]:
    """Map WaveBook plan intervals to Stripe recurring price intervals."""
    return {
        "monthly": ("month", 1),
        "quarterly": ("month", 3),
        "biannual": ("month", 6),
        "yearly": ("year", 1),
    }.get(plan_interval, ("month", 1))


def activate_subscription(tx_ref: str, data: dict) -> dict:
    """Activate a subscription after a successful payment (Stripe or Flutterwave).

    Idempotent: a second call for the same transaction returns early. Shared by
    the webhook handler and the /subscribe/verify redirect page.
    """
    business_id = 0
    plan_key = (data.get("meta") or {}).get("plan") or "basic_monthly"
    if tx_ref.startswith("WB-SUB-"):
        parts = tx_ref.split("-")
        try:
            business_id = int(parts[2])
        except (IndexError, ValueError):
            business_id = 0
        # Older refs lack the plan segment; meta is authoritative when present
        if plan_key not in settings.SUBSCRIPTION_PLANS and len(parts) > 3:
            plan_key = parts[3]
    plan_key = settings.LEGACY_PLAN_KEYS.get(plan_key, plan_key)
    if plan_key not in settings.SUBSCRIPTION_PLANS:
        plan_key = "basic_monthly"
    plan = settings.SUBSCRIPTION_PLANS[plan_key]
    if not business_id:
        raise HTTPException(status_code=400, detail="Invalid payment reference")

    # The transaction currency is authoritative; it must be one we support and
    # must match the currency requested at checkout when present in meta.
    currency = (data.get("currency") or settings.STRIPE_CURRENCY).upper()
    currency_info = settings.SUBSCRIPTION_CURRENCIES.get(currency)
    meta_currency = ((data.get("meta") or {}).get("currency") or "").upper()
    if currency_info is None or (meta_currency and meta_currency != currency):
        raise HTTPException(status_code=400, detail="Payment currency mismatch")

    paid = float(data.get("amount") or 0)
    expected = round(plan["price"] * currency_info["rate"], 2)
    if paid < expected:
        raise HTTPException(status_code=400, detail="Payment amount does not match")

    conn = get_connection()
    try:
        # Idempotency: never activate twice for the same transaction.
        # New rows keep tx_ref; legacy rows stored the tx_ref in stripe_subscription_id.
        existing = conn.execute(
            "SELECT id FROM subscriptions WHERE tx_ref = ? OR stripe_subscription_id = ?",
            (tx_ref, tx_ref),
        ).fetchone()
        if existing:
            return {"status": "active", "business_id": business_id}
        # Every paid plan includes the storefront; product caps differ by tier.
        conn.execute(
            "UPDATE businesses SET subscription_status = 'active', storefront_enabled = 1 WHERE id = ?",
            (business_id,),
        )
        stripe_sub_id = data.get("subscription") or tx_ref
        conn.execute(
            "INSERT INTO subscriptions (business_id, stripe_subscription_id, tx_ref, status, plan, amount, currency, current_period_end, stripe_customer_id) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)",
            (business_id, stripe_sub_id, tx_ref, plan_key, paid, currency, data.get("current_period_end") or "", data.get("customer") or ""),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "active", "business_id": business_id}


def _business_for_subscription(sub_id: str, meta: dict) -> int | None:
    """Resolve the business id for a Stripe subscription (by sub_ id or metadata)."""
    if not sub_id:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT business_id FROM subscriptions WHERE stripe_subscription_id = ?", (sub_id,)
        ).fetchone()
    finally:
        conn.close()
    if row:
        return row["business_id"]
    try:
        return int(meta.get("business_id") or 0) or None
    except (TypeError, ValueError):
        return None


def renew_subscription(invoice: dict) -> dict:
    """invoice.paid: a renewal succeeded — keep the business active.

    Called by the Stripe webhook for every paid invoice (initial and renewals).
    """
    sub_id = invoice.get("subscription") or ""
    meta = dict(invoice.get("subscription_details") or {}).get("metadata") or {}
    business_id = _business_for_subscription(sub_id, meta)
    if business_id is None:
        return {"status": "ignored"}
    period_end = _format_period_end(invoice.get("period_end"))
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET subscription_status = 'active', storefront_enabled = 1 WHERE id = ?",
            (business_id,),
        )
        if sub_id:
            conn.execute(
                "UPDATE subscriptions SET status = 'active', current_period_end = ? "
                "WHERE business_id = ? AND stripe_subscription_id = ?",
                (period_end, business_id, sub_id),
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": "active", "business_id": business_id}


def mark_subscription_past_due(invoice: dict) -> dict:
    """invoice.payment_failed: flag the business past_due and notify the owner."""
    sub_id = invoice.get("subscription") or ""
    meta = dict(invoice.get("subscription_details") or {}).get("metadata") or {}
    business_id = _business_for_subscription(sub_id, meta)
    if business_id is None:
        return {"status": "ignored"}
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET subscription_status = 'past_due' WHERE id = ?", (business_id,)
        )
        conn.execute(
            "INSERT INTO notifications (business_id, type, title, message) "
            "VALUES (?, 'subscription', 'Payment failed', 'Your monthly subscription payment failed. Stripe will retry automatically — update your card details to avoid losing access.')",
            (business_id,),
        )
        owner = conn.execute(
            "SELECT email FROM users WHERE business_id = ? AND role = 'owner' ORDER BY id LIMIT 1",
            (business_id,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if owner:
        from ..services import emailer

        emailer.send_email(
            owner["email"],
            "WaveBook payment failed — action needed",
            "Your WaveBook subscription payment could not be collected. Stripe will retry automatically; update your payment method in the WaveBook app to keep your subscription active.",
        )
    return {"status": "past_due", "business_id": business_id}


def cancel_subscription(subscription: dict) -> dict:
    """customer.subscription.deleted: the subscription ended — deactivate the business."""
    sub_id = subscription.get("id") or ""
    meta = dict(subscription.get("metadata") or {})
    business_id = _business_for_subscription(sub_id, meta)
    if business_id is None:
        return {"status": "ignored"}
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET subscription_status = 'cancelled' WHERE id = ?", (business_id,)
        )
        conn.execute(
            "UPDATE subscriptions SET status = 'cancelled' "
            "WHERE business_id = ? AND stripe_subscription_id = ?",
            (business_id, sub_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "cancelled", "business_id": business_id}


def _format_period_end(ts) -> str:
    """Format a Stripe unix timestamp as a YYYY-MM-DD date string."""
    if not ts:
        return ""
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""
