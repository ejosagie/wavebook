import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import settings
from ..database import get_connection, row_to_dict
from ..deps import get_current_user
from ..phone import validate_uk_phone
from ..schemas import LoginRequest, SignupRequest, TokenResponse
from ..security import create_access_token, hash_password, verify_password
from ..services.emailer import send_welcome_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


def register_user(data: SignupRequest) -> dict:
    """Create a user account, optionally with a business and website address."""
    # Validate everything before touching the database so a failed signup
    # never leaves a partial account behind.
    try:
        phone = validate_uk_phone(data.phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    slug = None
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
            trial_ends = (datetime.utcnow() + timedelta(days=settings.TRIAL_DAYS)).strftime("%Y-%m-%d")
            bcur = conn.execute(
                "INSERT INTO businesses (slug, name, trial_ends_at) VALUES (?, ?, ?)",
                (slug, data.business_name.strip(), trial_ends),
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


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    user.pop("password_hash", None)
    return user
