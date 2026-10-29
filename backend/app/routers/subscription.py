import secrets
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from ..config import settings
from ..database import get_connection, get_trial_days, row_to_dict
from ..deps import bearer_scheme, business_tier_features, get_business_plan, get_current_business
from ..schemas import SubscriptionCheckoutRequest
from ..security import decode_access_token
from ..services import flutterwave

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
    }


@router.post("/checkout")
def create_checkout(
    payload: SubscriptionCheckoutRequest | None = Body(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    """Create a Flutterwave payment link for a subscription plan.

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
            email = (payload.email or "").strip().lower() if payload else ""
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

    tier = settings.TIER_LABELS.get(plan["tier"], "WaveBook")
    interval_label = settings.INTERVAL_LABELS.get(plan["interval"], plan["interval"].title())
    tx_ref = f"WB-SUB-{business['id']}-{plan_key}-{secrets.token_hex(4)}"
    payment_link = flutterwave.create_payment_link(
        tx_ref=tx_ref,
        amount=amount,
        currency=currency,
        country=currency_info["country"],
        redirect_url=f"{settings.API_PUBLIC_URL}/subscribe/verify",
        customer_email=user["email"],
        meta={
            "business_id": str(business["id"]),
            "type": "subscription",
            "plan": plan_key,
            "currency": currency,
        },
        title=f"{tier} — {interval_label}",
        description=f"{interval_label} subscription for {business['name']}",
    )
    return {"payment_link": payment_link}
