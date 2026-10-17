from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import get_current_business
from ..schemas import FeedbackCreate

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_feedback(data: FeedbackCreate):
    """Public endpoint — customers leave feedback for a business by slug."""
    conn = get_connection()
    try:
        business = conn.execute(
            "SELECT id FROM businesses WHERE slug = ?", (data.slug.lower().strip(),)
        ).fetchone()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        cur = conn.execute(
            "INSERT INTO feedback (business_id, booking_id, customer_name, rating, comment) VALUES (?, ?, ?, ?, ?)",
            (business["id"], data.booking_id, data.name.strip(), data.rating, data.comment.strip()),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM feedback WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


@router.get("")
def list_feedback(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        rows = rows_to_dicts(
            conn.execute(
                """SELECT f.*, b.date AS booking_date, b.time AS booking_time, b.service_name
                   FROM feedback f
                   LEFT JOIN bookings b ON b.id = f.booking_id
                   WHERE f.business_id = ?
                   ORDER BY f.created_at DESC""",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return rows


@router.delete("/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback(feedback_id: int, business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM feedback WHERE id = ? AND business_id = ?", (feedback_id, business["id"])
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Feedback not found")
    finally:
        conn.close()
