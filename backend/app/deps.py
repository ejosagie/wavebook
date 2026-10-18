from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .database import get_connection, row_to_dict
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    conn = get_connection()
    try:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    finally:
        conn.close()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_current_business(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("business_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No business linked to this account")
    conn = get_connection()
    try:
        business = row_to_dict(
            conn.execute("SELECT * FROM businesses WHERE id = ?", (user["business_id"],)).fetchone()
        )
    finally:
        conn.close()
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return business


def require_owner(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")


def get_business_plan(business_id: int) -> tuple[str | None, dict | None]:
    """Return (plan_key, plan) for the business's latest active subscription."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT plan FROM subscriptions WHERE business_id = ? AND status = 'active' "
            "ORDER BY id DESC LIMIT 1",
            (business_id,),
        ).fetchone()
    finally:
        conn.close()
    key = settings.LEGACY_PLAN_KEYS.get(row["plan"], row["plan"]) if row else None
    plan = settings.SUBSCRIPTION_PLANS.get(key) if key else None
    return (key, plan) if plan else (None, None)


def business_tier_features(business: dict) -> dict:
    """Feature limits for the business's current tier.

    Active subs get their plan's features; trials get trial features;
    cancelled/past_due subs get the locked-down 'expired' tier.
    """
    status = business.get("subscription_status")
    if status == "active":
        _, plan = get_business_plan(business["id"])
        if plan:
            return settings.TIER_FEATURES[plan["tier"]]
    if status == "trial":
        return settings.TIER_FEATURES["trial"]
    return settings.TIER_FEATURES["expired"]
