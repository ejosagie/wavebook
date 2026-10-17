import secrets
from datetime import date, datetime

from fastapi import APIRouter, Depends

from ..config import settings
from ..deps import get_current_business, require_owner
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
    return {
        "status": business["subscription_status"],
        "price_gbp": settings.SUBSCRIPTION_PRICE_GBP,
        "max_staff": settings.MAX_STAFF,
        "trial_days": settings.TRIAL_DAYS,
        "trial_ends_at": trial_ends,
        "trial_days_left": trial_days_left,
    }


@router.post("/checkout")
def create_checkout(
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    """Create a Flutterwave payment link for the £9.99/month subscription.

    Subscription activation happens on the website only (App Store compliant).
    """
    tx_ref = f"WB-SUB-{business['id']}-{secrets.token_hex(4)}"
    payment_link = flutterwave.create_payment_link(
        tx_ref=tx_ref,
        amount=settings.SUBSCRIPTION_PRICE_GBP,
        currency=settings.FLW_CURRENCY,
        redirect_url=f"{settings.API_PUBLIC_URL}/subscribe/verify",
        customer_email=user["email"],
        meta={
            "business_id": str(business["id"]),
            "type": "subscription",
        },
        title="WaveBook Subscription",
        description=f"Monthly subscription for {business['name']}",
    )
    return {"payment_link": payment_link}
