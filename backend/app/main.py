from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import (
    auth,
    availability,
    bookings,
    business,
    customers,
    notifications,
    payments,
    services,
    staff,
    subscription,
    web,
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"

app = FastAPI(title="WaveBook API", version="0.1.0")

# Wire upload dir into the business router
business.UPLOAD_DIR = UPLOADS_DIR

# Static files (CSS, uploaded images)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.on_event("startup")
def on_startup():
    init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# API routers
app.include_router(auth.router)
app.include_router(business.router)
app.include_router(services.router)
app.include_router(availability.router)
app.include_router(bookings.router)
app.include_router(customers.router)
app.include_router(notifications.router)
app.include_router(payments.router)
app.include_router(staff.router)
app.include_router(subscription.router)

# Web pages (landing, subscribe, admin, tenant booking sites)
app.include_router(web.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "WaveBook", "version": "0.1.0"}
