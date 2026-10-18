import secrets

from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import business_tier_features, get_current_business, require_owner
from ..schemas import StaffInvite, StaffUpdate
from ..security import hash_password
from ..services.emailer import send_staff_invite_email

router = APIRouter(prefix="/api/staff", tags=["staff"])


@router.get("")
def list_staff(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        rows = rows_to_dicts(
            conn.execute(
                """SELECT s.id, s.active, s.created_at, u.id AS user_id, u.email, u.full_name, u.phone
                   FROM staff s JOIN users u ON u.id = s.user_id
                   WHERE s.business_id = ? ORDER BY s.id""",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return rows


@router.post("", status_code=status.HTTP_201_CREATED)
def invite_staff(
    data: StaffInvite,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    max_staff = business_tier_features(business)["max_staff"]
    if max_staff == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff accounts are available on WaveBook Premium",
        )
    conn = get_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM staff WHERE business_id = ?", (business["id"],)
        ).fetchone()["c"]
        if count >= max_staff:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum of {max_staff} staff members allowed",
            )

        temp_password = None
        existing_user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (data.email.lower(),)
        ).fetchone()
        if existing_user:
            if existing_user["business_id"]:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email already belongs to another business")
            user_id = existing_user["id"]
            conn.execute(
                "UPDATE users SET business_id = ?, full_name = ?, phone = ?, role = 'staff' WHERE id = ?",
                (business["id"], data.full_name, data.phone, user_id),
            )
        else:
            # Temporary password; staff set their own on first login (flow added later)
            temp_password = secrets.token_urlsafe(9)
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, full_name, phone, role, business_id) VALUES (?, ?, ?, ?, 'staff', ?)",
                (data.email.lower(), hash_password(temp_password), data.full_name, data.phone, business["id"]),
            )
            user_id = cur.lastrowid

        conn.execute(
            "INSERT INTO staff (business_id, user_id, active) VALUES (?, ?, 1)",
            (business["id"], user_id),
        )
        conn.commit()
        staff = row_to_dict(
            conn.execute(
                """SELECT s.id, s.active, u.email, u.full_name, u.phone
                   FROM staff s JOIN users u ON u.id = s.user_id WHERE s.id = ?""",
                (conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"],),
            ).fetchone()
        )
    finally:
        conn.close()
    send_staff_invite_email(data.email.lower(), data.full_name, business["name"], temp_password)
    return staff


@router.patch("/{staff_id}")
def update_staff(
    staff_id: int,
    data: StaffUpdate,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM staff WHERE id = ? AND business_id = ?", (staff_id, business["id"])
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
        if data.active is not None:
            conn.execute("UPDATE staff SET active = ? WHERE id = ?", (1 if data.active else 0, staff_id))
        conn.commit()
        staff = row_to_dict(
            conn.execute(
                """SELECT s.id, s.active, u.email, u.full_name, u.phone
                   FROM staff s JOIN users u ON u.id = s.user_id WHERE s.id = ?""",
                (staff_id,),
            ).fetchone()
        )
    finally:
        conn.close()
    return staff


@router.delete("/{staff_id}")
def remove_staff(
    staff_id: int,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM staff WHERE id = ? AND business_id = ?", (staff_id, business["id"])
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
        conn.execute("DELETE FROM staff WHERE id = ?", (staff_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (existing["user_id"],))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
