from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import get_current_business, require_owner
from ..schemas import ServiceCreate, ServiceUpdate

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("")
def list_services(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT * FROM services WHERE business_id = ? ORDER BY sort_order, id",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return rows


@router.post("", status_code=status.HTTP_201_CREATED)
def create_service(data: ServiceCreate, business: dict = Depends(get_current_business), user: dict = Depends(require_owner)):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO services (business_id, name, description, price, duration_minutes) VALUES (?, ?, ?, ?, ?)",
            (business["id"], data.name.strip(), data.description, data.price, data.duration_minutes),
        )
        conn.commit()
        service = row_to_dict(conn.execute("SELECT * FROM services WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()
    return service


@router.patch("/{service_id}")
def update_service(
    service_id: int,
    data: ServiceUpdate,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM services WHERE id = ? AND business_id = ?", (service_id, business["id"])
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        updates = data.model_dump(exclude_unset=True, exclude_none=True)
        if updates:
            fields = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE services SET {fields} WHERE id = ?", (*updates.values(), service_id))
            conn.commit()
        service = row_to_dict(conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone())
    finally:
        conn.close()
    return service


@router.delete("/{service_id}")
def delete_service(
    service_id: int,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM services WHERE id = ? AND business_id = ?", (service_id, business["id"])
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return {"ok": True}
