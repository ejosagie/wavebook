import re
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_connection, get_trial_days, row_to_dict
from ..deps import get_current_user
from ..phone import validate_phone
from ..schemas import ChangePasswordRequest, ForgotPasswordRequest, LoginRequest, SignupRequest, TokenResponse, SUPPORTED_CURRENCIES
from ..security import create_access_token, hash_password, verify_password
from ..services.emailer import send_password_reset_email, send_welcome_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


def register_user(data: SignupRequest) -> dict:
    """Create a user account, optionally with a business and website address."""
    # Validate everything before touching the database so a failed signup
    # never leaves a partial account behind.
    try:
        phone = validate_phone(data.phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    slug = None
    currency = (data.currency or "GBP").upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported currency")
    if data.business_name and data.slug:
        slug = data.slug.lower().strip()
        if not re.match(r"^[a-z0-9-]{2,63}$", slug):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid website address")

    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (data.email.lower(),)).fetchone()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        if slug:
            taken = conn.execute("SELECT id FROM businesses WHERE slug = ?", (slug,)).fetchone()
            if taken:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That website address is already taken")
        password_hash = hash_password(data.password)
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, full_name, phone, role) VALUES (?, ?, ?, ?, 'owner')",
            (data.email.lower(), password_hash, data.full_name, phone),
        )
        user_id = cur.lastrowid
        business = None
        if slug:
            trial_ends = (datetime.utcnow() + timedelta(days=get_trial_days())).strftime("%Y-%m-%d")
            bcur = conn.execute(
                "INSERT INTO businesses (slug, name, trial_ends_at, currency) VALUES (?, ?, ?, ?)",
                (slug, data.business_name.strip(), trial_ends, currency),
            )
            business_id = bcur.lastrowid
            conn.execute(
                "INSERT INTO availability (business_id, working_days, blocked_dates, blocked_slots, slot_interval) "
                "VALUES (?, '{}', '[]', '{}', 30)",
                (business_id,),
            )
            for slot in range(8):
                conn.execute(
                    "INSERT INTO gallery (business_id, slot, path, caption) VALUES (?, ?, '', '')",
                    (business_id, slot),
                )
            conn.execute("UPDATE users SET business_id = ?, role = 'owner' WHERE id = ?", (business_id, user_id))
            business = row_to_dict(conn.execute("SELECT * FROM businesses WHERE id = ?", (business_id,)).fetchone())
        conn.commit()
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    # Notify the new business owner by email
    send_welcome_email(user["email"], user["full_name"], business)
    return user


@router.post("/signup", response_model=TokenResponse)
def signup(data: SignupRequest):
    user = register_user(data)
    token = create_access_token(user["id"])
    return TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest):
    conn = get_connection()
    try:
        user = row_to_dict(
            conn.execute("SELECT * FROM users WHERE email = ?", (data.email.lower(),)).fetchone()
        )
    finally:
        conn.close()
    if user is None or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (user["id"],)
        )
        conn.commit()
    finally:
        conn.close()
    user["last_login_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    user.pop("password_hash", None)
    token = create_access_token(user["id"])
    return TokenResponse(access_token=token, user=user)


def reset_password(email: str) -> bool:
    """Set a temporary password for the user and email it to them.

    Returns True when a matching account was found and reset.
    """
    conn = get_connection()
    found = False
    try:
        user = row_to_dict(
            conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
            ).fetchone()
        )
        if user:
            found = True
            alphabet = string.ascii_letters + string.digits
            temp_password = "".join(secrets.choice(alphabet) for _ in range(12))
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                (hash_password(temp_password), user["id"]),
            )
            conn.commit()
            send_password_reset_email(user["email"], user["full_name"], temp_password)
    finally:
        conn.close()
    return found


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest):
    """Reset a user's password to a temporary one and email it to them.

    Returns ok even when the email is unknown so the endpoint can't be used
    to probe which accounts exist.
    """
    reset_password(data.email)
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    user.pop("password_hash", None)
    return user


@router.post("/change-password")
def change_password(data: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not verify_password(data.current_password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (hash_password(data.new_password), user["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
