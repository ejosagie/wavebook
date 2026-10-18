import re
from datetime import date, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .database import get_connection, row_to_dict
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

STAFF_ALLOWED_ROUTES = (
    ("GET", re.compile(r"^/api/(auth/me|app/meta|health)$")),
    ("POST", re.compile(r"^/api/auth/(login|signup|change-password)$")),
)
STAFF_BOOKING_ROUTES = (
    ("GET", re.compile(r"^/api/bookings/mine$")),
)


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
    business["subscription_status"] = effective_subscription_status(business)
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


def _trial_end_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def effective_subscription_status(business: dict) -> str:
    """A trial ends on its trial_ends_at date; from then on the business is 'expired'."""
    status = business.get("subscription_status")
    if status == "trial":
        end = _trial_end_date(business.get("trial_ends_at"))
        if end is not None and date.today() >= end:
            return "expired"
    return status


def business_tier_features(business: dict) -> dict:
    """Feature limits for the business's current tier.

    Active subs get their plan's features; trials get trial features;
    cancelled/past_due subs get the locked-down 'expired' tier.
    """
    status = effective_subscription_status(business)
    if status == "active":
        _, plan = get_business_plan(business["id"])
        if plan:
            return settings.TIER_FEATURES[plan["tier"]]
    if status == "trial":
        return settings.TIER_FEATURES["trial"]
    return settings.TIER_FEATURES["expired"]


def _route_matches(method: str, path: str, rules) -> bool:
    return any(method == rule_method and pattern.match(path) for rule_method, pattern in rules)


def enforce_staff_access(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Staff accounts only reach their assigned bookings and their own account routes.

    Every other API route is owner-only. Staff also lose access if the business is no longer on a plan that includes staff.
    """
    path = request.url.path
    if credentials is None or not path.startswith("/api/"):
        return
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        return
    conn = get_connection()
    try:
        user = row_to_dict(conn.execute("SELECT role, business_id FROM users WHERE id = ?", (user_id,)).fetchone())
        business = None
        if user and user["role"] == "staff" and user["business_id"]:
            business = row_to_dict(
                conn.execute("SELECT * FROM businesses WHERE id = ?", (user["business_id"],)).fetchone()
            )
    finally:
        conn.close()
    if not user or user["role"] != "staff":
        return
    if _route_matches(request.method, path, STAFF_ALLOWED_ROUTES):
        return
    if business is None or business_tier_features(business)["max_staff"] == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access is not included in this business's plan",
        )
    if not _route_matches(request.method, path, STAFF_BOOKING_ROUTES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff accounts can only view their assigned bookings",
        )
