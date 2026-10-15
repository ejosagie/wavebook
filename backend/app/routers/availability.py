from fastapi import APIRouter, Depends, HTTPException

from ..database import get_connection, json_dumps, row_to_dict
from ..deps import get_current_business, require_owner
from ..schemas import AvailabilityUpdate
from ..services.slots import DEFAULT_WORKING_DAYS, get_availability_row

router = APIRouter(prefix="/api/availability", tags=["availability"])


@router.get("")
def get_availability(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM availability WHERE business_id = ?", (business["id"],)
        ).fetchone()
    finally:
        conn.close()
    return get_availability_row(row)


@router.put("")
def update_availability(
    data: AvailabilityUpdate,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM availability WHERE business_id = ?", (business["id"],)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO availability (business_id, working_days, blocked_dates, blocked_slots, slot_interval) "
                "VALUES (?, '{}', '[]', '{}', 30)",
                (business["id"],),
            )
            row = conn.execute(
                "SELECT * FROM availability WHERE business_id = ?", (business["id"],)
            ).fetchone()

        current = get_availability_row(row)
        working_days = current["working_days"]
        if data.working_days is not None:
            merged = dict(DEFAULT_WORKING_DAYS)
            for key, cfg in data.working_days.items():
                merged[key] = cfg.model_dump()
            working_days = merged

        blocked_dates = data.blocked_dates if data.blocked_dates is not None else current["blocked_dates"]
        blocked_slots = data.blocked_slots if data.blocked_slots is not None else current["blocked_slots"]
        slot_interval = data.slot_interval if data.slot_interval is not None else current["slot_interval"]

        conn.execute(
            "UPDATE availability SET working_days = ?, blocked_dates = ?, blocked_slots = ?, slot_interval = ? "
            "WHERE business_id = ?",
            (
                json_dumps(working_days),
                json_dumps(blocked_dates),
                json_dumps(blocked_slots),
                slot_interval,
                business["id"],
            ),
        )
        conn.commit()
        updated = row_to_dict(
            conn.execute("SELECT * FROM availability WHERE business_id = ?", (business["id"],)).fetchone()
        )
    finally:
        conn.close()
    return get_availability_row(updated)
