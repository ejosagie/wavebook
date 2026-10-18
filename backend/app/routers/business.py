import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from ..database import get_connection, get_trial_days, row_to_dict, rows_to_dicts
from ..deps import get_current_business, get_current_user, require_owner
from ..phone import validate_uk_phone
from ..schemas import BusinessCreate, BusinessUpdate

router = APIRouter(prefix="/api/business", tags=["business"])

UPLOAD_DIR = None  # set in main via app.state


def _upload_dir():
    return UPLOAD_DIR


@router.post("", status_code=status.HTTP_201_CREATED)
def create_business(data: BusinessCreate, user: dict = Depends(get_current_user)):
    if user.get("business_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Business already exists for this account")

    slug = data.slug.lower().strip()
    if not re.match(r"^[a-z0-9-]{2,63}$", slug):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid slug")

    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM businesses WHERE slug = ?", (slug,)).fetchone()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That website address is already taken")

        trial_ends = (datetime.utcnow() + timedelta(days=get_trial_days())).strftime("%Y-%m-%d")
        cur = conn.execute(
            "INSERT INTO businesses (slug, name, trial_ends_at) VALUES (?, ?, ?)",
            (slug, data.name.strip(), trial_ends),
        )
        business_id = cur.lastrowid
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
        conn.execute("UPDATE users SET business_id = ?, role = 'owner' WHERE id = ?", (business_id, user["id"]))
        conn.commit()
        business = row_to_dict(conn.execute("SELECT * FROM businesses WHERE id = ?", (business_id,)).fetchone())
    finally:
        conn.close()
    return business


@router.get("")
def get_business(business: dict = Depends(get_current_business)):
    return business


@router.patch("")
def update_business(data: BusinessUpdate, business: dict = Depends(get_current_business)):
    updates = data.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return business
    if "contact_phone" in updates:
        try:
            updates["contact_phone"] = validate_uk_phone(updates["contact_phone"])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if "slug" in updates:
        slug = updates["slug"].lower().strip()
        if not re.match(r"^[a-z0-9-]{2,63}$", slug):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid website address")
        updates["slug"] = slug
        conn = get_connection()
        try:
            taken = conn.execute(
                "SELECT id FROM businesses WHERE slug = ? AND id != ?", (slug, business["id"])
            ).fetchone()
        finally:
            conn.close()
        if taken:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That website address is already taken")
    conn = get_connection()
    try:
        fields = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE businesses SET {fields} WHERE id = ?", (*updates.values(), business["id"]))
        conn.commit()
        updated = row_to_dict(conn.execute("SELECT * FROM businesses WHERE id = ?", (business["id"],)).fetchone())
    finally:
        conn.close()
    return updated


@router.post("/logo")
def upload_logo(
    file: UploadFile,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    return _save_upload(file, business, "logo")


@router.post("/about-image")
def upload_about_image(
    file: UploadFile,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    return _save_upload(file, business, "about")


def _save_upload(file: UploadFile, business: dict, kind: str) -> dict:
    allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use JPG, PNG, GIF or WebP")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
    import uuid

    filename = f"{kind}_{business['id']}_{uuid.uuid4().hex[:8]}.{ext}"
    uploads = _upload_dir()
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / filename
    dest.write_bytes(file.file.read())

    path = f"/uploads/{filename}"
    column = "logo_path" if kind == "logo" else "about_image"
    conn = get_connection()
    try:
        conn.execute(f"UPDATE businesses SET {column} = ? WHERE id = ?", (path, business["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"path": path}


@router.get("/gallery")
def get_gallery(business: dict = Depends(get_current_business)):
    conn = get_connection()
    try:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT slot, path, caption FROM gallery WHERE business_id = ? ORDER BY slot",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return rows


@router.post("/gallery/{slot}")
def upload_gallery_image(
    slot: int,
    file: UploadFile,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    if slot < 0 or slot > 7:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slot must be 0-7")
    allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use JPG, PNG, GIF or WebP")

    import uuid

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
    filename = f"gallery_{business['id']}_{slot}_{uuid.uuid4().hex[:8]}.{ext}"
    uploads = _upload_dir()
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / filename
    dest.write_bytes(file.file.read())
    path = f"/uploads/{filename}"

    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE gallery SET path = ?, caption = ? WHERE business_id = ? AND slot = ?",
            (path, "", business["id"], slot),
        )
        if cur.rowcount == 0:
            conn.execute(
                "INSERT INTO gallery (business_id, slot, path, caption) VALUES (?, ?, ?, '')",
                (business["id"], slot, path),
            )
        conn.commit()
    finally:
        conn.close()
    return {"slot": slot, "path": path, "caption": ""}


@router.patch("/gallery/{slot}")
def update_gallery_caption(
    slot: int,
    caption: str,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE gallery SET caption = ? WHERE business_id = ? AND slot = ?",
            (caption, business["id"], slot),
        )
        conn.commit()
    finally:
        conn.close()
    return {"slot": slot, "caption": caption}


@router.delete("/gallery/{slot}")
def delete_gallery_image(
    slot: int,
    business: dict = Depends(get_current_business),
    user: dict = Depends(require_owner),
):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT path FROM gallery WHERE business_id = ? AND slot = ?", (business["id"], slot)
        ).fetchone()
        if row and row["path"]:
            try:
                (_upload_dir() / row["path"].split("/")[-1]).unlink(missing_ok=True)
            except OSError:
                pass
        conn.execute(
            "UPDATE gallery SET path = '', caption = '' WHERE business_id = ? AND slot = ?",
            (business["id"], slot),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
