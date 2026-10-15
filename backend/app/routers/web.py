from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..database import get_connection, row_to_dict, rows_to_dicts
from ..services.slots import (
    DAY_LABELS,
    blocked_dates_json,
    get_availability_row,
    get_available_time_slots,
    is_date_blocked,
)

router = APIRouter(tags=["web"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"

# ---- Helpers ----


def _get_business_by_slug(slug: str) -> dict | None:
    conn = get_connection()
    try:
        return row_to_dict(conn.execute("SELECT * FROM businesses WHERE slug = ?", (slug,)).fetchone())
    finally:
        conn.close()


def _tenant_slug(request: Request, path_slug: str | None = None) -> str | None:
    """Resolve tenant slug from subdomain or /t/{slug} path (for local dev)."""
    if path_slug:
        return path_slug
    host = request.headers.get("host", "")
    base = settings.BASE_URL.replace("http://", "").replace("https://", "").split(":")[0]
    if host.endswith(base) and host != base:
        return host.split(".")[0]
    return None


def _format_price(amount: float, currency: str = "GBP") -> str:
    symbol = "£" if currency == "GBP" else "$"
    return f"{symbol}{amount:,.2f}"


def _format_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} hour{'s' if h > 1 else ''} {m} min"
    if h:
        return f"{h} hour{'s' if h > 1 else ''}"
    return f"{m} minutes"


# ---- Landing page ----


@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        request,
        "landing.html",
        {"price_gbp": settings.SUBSCRIPTION_PRICE_GBP, "max_staff": settings.MAX_STAFF},
    )


# ---- Subscription pages ----


@router.get("/subscribe", response_class=HTMLResponse)
def subscribe_page(request: Request):
    return templates.TemplateResponse(
        request,
        "subscribe.html",
        {"price_gbp": settings.SUBSCRIPTION_PRICE_GBP},
    )


@router.get("/subscribe/success", response_class=HTMLResponse)
def subscribe_success(request: Request):
    return templates.TemplateResponse(request, "subscribe_success.html", {})


@router.get("/subscribe/cancel", response_class=HTMLResponse)
def subscribe_cancel(request: Request):
    return templates.TemplateResponse(request, "subscribe_cancel.html", {})


# ---- Owner admin dashboard ----


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    conn = get_connection()
    try:
        businesses = rows_to_dicts(
            conn.execute(
                """SELECT b.*,
                          (SELECT COUNT(*) FROM bookings bk WHERE bk.business_id = b.id) AS booking_count,
                          (SELECT COUNT(*) FROM bookings bk WHERE bk.business_id = b.id AND bk.status = 'pending') AS pending_count
                   FROM businesses b ORDER BY b.created_at DESC"""
            ).fetchall()
        )
        total_bookings = conn.execute("SELECT COUNT(*) AS c FROM bookings").fetchone()["c"]
        total_businesses = conn.execute("SELECT COUNT(*) AS c FROM businesses").fetchone()["c"]
        active_subs = conn.execute(
            "SELECT COUNT(*) AS c FROM businesses WHERE subscription_status = 'active'"
        ).fetchone()["c"]
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "businesses": businesses,
            "total_bookings": total_bookings,
            "total_businesses": total_businesses,
            "active_subs": active_subs,
        },
    )


# ---- Tenant booking sites ----


@router.get("/t/{slug}", response_class=HTMLResponse)
def tenant_home(request: Request, slug: str):
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    conn = get_connection()
    try:
        services = rows_to_dicts(
            conn.execute(
                "SELECT * FROM services WHERE business_id = ? ORDER BY sort_order, id", (business["id"],)
            ).fetchall()
        )
        gallery = rows_to_dicts(
            conn.execute(
                "SELECT slot, path, caption FROM gallery WHERE business_id = ? AND path != '' ORDER BY slot",
                (business["id"],),
            ).fetchall()
        )
        availability = get_availability_row(
            conn.execute("SELECT * FROM availability WHERE business_id = ?", (business["id"],)).fetchone()
        )
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "tenant/index.html",
        {
            "business": business,
            "services": services,
            "gallery": gallery,
            "availability": availability,
            "day_labels": DAY_LABELS,
            "format_price": _format_price,
            "format_duration": _format_duration,
        },
    )


@router.get("/t/{slug}/services", response_class=HTMLResponse)
def tenant_services(request: Request, slug: str):
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    conn = get_connection()
    try:
        services = rows_to_dicts(
            conn.execute(
                "SELECT * FROM services WHERE business_id = ? ORDER BY sort_order, id", (business["id"],)
            ).fetchall()
        )
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "tenant/services.html",
        {
            "business": business,
            "services": services,
            "format_price": _format_price,
            "format_duration": _format_duration,
        },
    )


@router.get("/t/{slug}/booking", response_class=HTMLResponse)
def tenant_booking_page(request: Request, slug: str, service: int | None = None):
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    conn = get_connection()
    try:
        services = rows_to_dicts(
            conn.execute(
                "SELECT * FROM services WHERE business_id = ? ORDER BY sort_order, id", (business["id"],)
            ).fetchall()
        )
        availability = get_availability_row(
            conn.execute("SELECT * FROM availability WHERE business_id = ?", (business["id"],)).fetchone()
        )
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "tenant/booking.html",
        {
            "business": business,
            "services": services,
            "selected_service": service,
            "blocked_dates": blocked_dates_json(availability),
            "today": date.today().isoformat(),
            "format_price": _format_price,
            "format_duration": _format_duration,
        },
    )


@router.get("/t/{slug}/api/slots")
def tenant_slots(slug: str, date: str, service_id: int | None = None):
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    conn = get_connection()
    try:
        availability_row = conn.execute(
            "SELECT * FROM availability WHERE business_id = ?", (business["id"],)
        ).fetchone()
        service = None
        if service_id:
            service = conn.execute(
                "SELECT * FROM services WHERE id = ? AND business_id = ?", (service_id, business["id"])
            ).fetchone()
        confirmed = conn.execute(
            "SELECT * FROM bookings WHERE business_id = ? AND date = ? AND status = 'confirmed'",
            (business["id"], date),
        ).fetchall()
    finally:
        conn.close()

    availability = get_availability_row(availability_row)
    if is_date_blocked(date, availability):
        return {"blocked": True, "slots": []}
    duration = int(service["duration_minutes"]) if service else 60
    slots = get_available_time_slots(
        date,
        availability,
        rows_to_dicts(confirmed),
        duration,
        int(business["buffer_minutes"] or 30),
    )
    return {"blocked": False, "slots": slots}


@router.post("/t/{slug}/booking")
async def tenant_booking_submit(
    request: Request,
    slug: str,
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(...),
    service_id: int = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    notes: str = Form(""),
):
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    conn = get_connection()
    try:
        service = conn.execute(
            "SELECT * FROM services WHERE id = ? AND business_id = ?", (service_id, business["id"])
        ).fetchone()
        if not service:
            raise HTTPException(status_code=400, detail="Invalid service selected")

        availability = get_availability_row(
            conn.execute("SELECT * FROM availability WHERE business_id = ?", (business["id"],)).fetchone()
        )
        if is_date_blocked(date, availability):
            raise HTTPException(status_code=400, detail="That date is not available")

        confirmed = conn.execute(
            "SELECT * FROM bookings WHERE business_id = ? AND date = ? AND status = 'confirmed'",
            (business["id"], date),
        ).fetchall()
        slots = get_available_time_slots(
            date,
            availability,
            rows_to_dicts(confirmed),
            int(service["duration_minutes"] or 60),
            int(business["buffer_minutes"] or 30),
        )
        if time not in slots:
            raise HTTPException(status_code=400, detail="That time slot is no longer available")

        cur = conn.execute(
            """INSERT INTO bookings
               (business_id, customer_name, customer_email, customer_phone, service_id,
                service_name, service_price, service_duration_minutes, date, time, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                business["id"], name.strip(), email.strip(), phone.strip(), service["id"],
                service["name"], service["price"], service["duration_minutes"],
                date, time, notes.strip(),
            ),
        )
        booking_id = cur.lastrowid
        conn.execute(
            "INSERT INTO notifications (business_id, type, title, message, booking_id) VALUES (?, 'booking', ?, ?, ?)",
            (
                business["id"],
                "New booking received",
                f"{name.strip()} booked {service['name']} on {date} at {time}",
                booking_id,
            ),
        )
        conn.commit()
        booking = row_to_dict(conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone())
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "tenant/booking_success.html",
        {
            "business": business,
            "booking": booking,
            "deposit_amount": min(float(business["deposit_amount"] or 0), float(service["price"] or 0)),
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "format_price": _format_price,
        },
    )


@router.get("/t/{slug}/booking/{booking_id}/paid")
def tenant_booking_paid(request: Request, slug: str, booking_id: int):
    """Landing page after a successful Stripe deposit payment."""
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    conn = get_connection()
    try:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE id = ? AND business_id = ?",
            (booking_id, business["id"]),
        ).fetchone()
    finally:
        conn.close()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return templates.TemplateResponse(
        request,
        "tenant/booking_success.html",
        {
            "business": business,
            "booking": row_to_dict(booking),
            "deposit_amount": 0.0,
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "format_price": _format_price,
        },
    )


@router.post("/t/{slug}/upload-confirmation")
async def tenant_upload_confirmation(
    request: Request,
    slug: str,
    booking_ref: str = Form(...),
    confirmation: UploadFile = Form(...),
):
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    allowed = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}
    if confirmation.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Invalid file type. Use an image or PDF.")

    conn = get_connection()
    try:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE id = ? AND business_id = ?", (booking_ref, business["id"])
        ).fetchone()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking reference not found")

        import uuid

        ext = confirmation.filename.rsplit(".", 1)[-1].lower() if "." in confirmation.filename else "bin"
        filename = f"conf_{business['id']}_{booking_ref}_{uuid.uuid4().hex[:8]}.{ext}"
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        dest = UPLOADS_DIR / filename
        dest.write_bytes(await confirmation.read())

        conn.execute(
            "UPDATE bookings SET confirmation_file = ? WHERE id = ?",
            (f"/uploads/{filename}", booking_ref),
        )
        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "tenant/confirmation_uploaded.html",
        {"business": business},
    )
