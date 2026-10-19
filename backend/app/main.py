import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import get_connection, init_db, row_to_dict
from .deps import enforce_staff_access
from .routers import (
    auth,
    availability,
    bookings,
    business,
    chats,
    customers,
    feedback,
    notifications,
    payments,
    products,
    reports,
    services,
    staff,
    subscription,
    web,
)
from .services.emailer import send_booking_reminder_email

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"

app = FastAPI(title="WaveBook API", version="0.2.2", dependencies=[Depends(enforce_staff_access)])

# Wire upload dir into the business and products routers
business.UPLOAD_DIR = UPLOADS_DIR
products.UPLOAD_DIR = UPLOADS_DIR

# Static files (CSS, uploaded images)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


async def _reminder_sweep() -> None:
    """Send reminder emails for confirmed bookings happening within 24 hours."""
    while True:
        try:
            conn = get_connection()
            try:
                now = datetime.now()
                window_end = now + timedelta(hours=24)
                rows = conn.execute(
                    "SELECT * FROM bookings WHERE status = 'confirmed' AND reminder_sent = 0 "
                    "AND customer_email != ''"
                ).fetchall()
                for row in rows:
                    booking = row_to_dict(row)
                    try:
                        when = datetime.fromisoformat(f"{booking['date']}T{booking['time']}")
                    except ValueError:
                        continue
                    if now <= when <= window_end:
                        # Claim the row first so concurrent workers never double-send
                        claimed = conn.execute(
                            "UPDATE bookings SET reminder_sent = 1 WHERE id = ? AND reminder_sent = 0",
                            (booking["id"],),
                        ).rowcount
                        if not claimed:
                            continue
                        business = row_to_dict(
                            conn.execute(
                                "SELECT * FROM businesses WHERE id = ?", (booking["business_id"],)
                            ).fetchone()
                        )
                        if business:
                            send_booking_reminder_email(booking, business)
                conn.commit()
            finally:
                conn.close()
        except Exception:  # pragma: no cover - keep the loop alive
            pass
        await asyncio.sleep(60 * 60)


@app.on_event("startup")
def on_startup():
    init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.get_event_loop().create_task(_reminder_sweep())


# API routers
app.include_router(auth.router)
app.include_router(business.router)
app.include_router(services.router)
app.include_router(availability.router)
app.include_router(bookings.router)
app.include_router(chats.router)
app.include_router(customers.router)
app.include_router(feedback.router)
app.include_router(notifications.router)
app.include_router(payments.router)
app.include_router(products.router)
app.include_router(reports.router)
app.include_router(staff.router)
app.include_router(subscription.router)

# Web pages (landing, subscribe, admin, tenant booking sites)
app.include_router(web.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "WaveBook", "version": "0.2.2"}
