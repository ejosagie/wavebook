from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_connection, row_to_dict
from ..deps import get_current_user
from ..phone import validate_uk_phone
from ..schemas import LoginRequest, SignupRequest, TokenResponse
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
def signup(data: SignupRequest):
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (data.email.lower(),)).fetchone()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        try:
            phone = validate_uk_phone(data.phone)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        password_hash = hash_password(data.password)
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, full_name, phone, role) VALUES (?, ?, ?, ?, 'owner')",
            (data.email.lower(), password_hash, data.full_name, phone),
        )
        conn.commit()
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
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
    user.pop("password_hash", None)
    token = create_access_token(user["id"])
    return TokenResponse(access_token=token, user=user)


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    user.pop("password_hash", None)
    return user
