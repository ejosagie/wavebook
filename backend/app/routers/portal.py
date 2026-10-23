"""Browser owner portal — Acuity-style account management on the web.

Server-rendered pages protected by an httpOnly session cookie. The forms
reuse the existing API router functions so business logic lives in one place.
"""

from pathlib import Path
from urllib.parse import quote

import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..database import get_connection, row_to_dict, rows_to_dicts
from ..deps import business_tier_features
from ..routers.availability import update_availability
from ..routers.business import update_business
from ..routers.auth import change_password
from ..routers.staff import invite_staff, remove_staff, update_staff
from ..routers.products import (
    _add_product_image,
    _attach_images,
    _delete_stored_image,
)
from ..routers.bookings import update_booking_status
from ..schemas import (
    AvailabilityUpdate,
    BookingStatusUpdate,
    BusinessUpdate,
    ChangePasswordRequest,
    StaffInvite,
    StaffUpdate,
    SUPPORTED_CURRENCIES,
)
from ..security import create_access_token, decode_access_token, hash_password, verify_password
from ..services.slots import DAY_LABELS, DEFAULT_WORKING_DAYS, get_availability_row
from .web import CURRENCY_SYMBOLS

router = APIRouter(prefix="/portal", tags=["portal"])

PORTAL_COOKIE = "wavebook_portal"

# Countries we pay out to by bank transfer, with the bank fields that suit them.
PAYOUT_COUNTRIES = [
    ("GB", "United Kingdom"),
    ("US", "United States"),
    ("CA", "Canada"),
    ("IE", "Ireland"),
    ("AU", "Australia"),
    ("NZ", "New Zealand"),
    ("NG", "Nigeria"),
    ("KE", "Kenya"),
    ("ZA", "South Africa"),
    ("EU", "Europe (other)"),
]

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _portal_user(request: Request) -> dict | None:
    """Return the logged-in user from the portal cookie, or None."""
    token = request.cookies.get(PORTAL_COOKIE)
    if not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    conn = get_connection()
    try:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    finally:
        conn.close()
    if user is None:
        return None
    user.pop("password_hash", None)
    return user


def _require_portal_user(request: Request) -> dict:
    user = _portal_user(request)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/portal/login"})
    return user


def _load_business(user: dict) -> dict | None:
    if not user.get("business_id"):
        return None
    conn = get_connection()
    try:
        business = row_to_dict(
            conn.execute("SELECT * FROM businesses WHERE id = ?", (user["business_id"],)).fetchone()
        )
    finally:
        conn.close()
    return business


def _redirect(path: str, msg: str | None = None, error: str | None = None) -> RedirectResponse:
    url = path
    params = []
    if msg:
        params.append(f"msg={quote(msg)}")
    if error:
        params.append(f"error={quote(error)}")
    if params:
        url += ("&" if "?" in url else "?") + "&".join(params)
    return RedirectResponse(url, status_code=303)


def _set_portal_cookie(response: RedirectResponse, request: Request, user_id: int) -> None:
    response.set_cookie(
        PORTAL_COOKIE,
        create_access_token(user_id),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=7 * 24 * 3600,
    )


def _counts(business_id: int) -> dict:
    conn = get_connection()
    try:
        services = conn.execute(
            "SELECT COUNT(*) AS c FROM services WHERE business_id = ?", (business_id,)
        ).fetchone()["c"]
        products = conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE business_id = ?", (business_id,)
        ).fetchone()["c"]
        staff = conn.execute(
            "SELECT COUNT(*) AS c FROM staff WHERE business_id = ?", (business_id,)
        ).fetchone()["c"]
        bookings = conn.execute(
            "SELECT COUNT(*) AS c FROM bookings WHERE business_id = ?", (business_id,)
        ).fetchone()["c"]
    finally:
        conn.close()
    return {"services": services, "products": products, "staff": staff, "bookings": bookings}


# ---- Login / logout ----


@router.get("/login", response_class=HTMLResponse)
def portal_login_page(request: Request):
    if _portal_user(request):
        return RedirectResponse(url="/portal", status_code=303)
    return templates.TemplateResponse(
        request,
        "portal_login.html",
        {"error": request.query_params.get("error"), "msg": request.query_params.get("msg")},
    )


@router.post("/login")
def portal_login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = get_connection()
    try:
        user = row_to_dict(
            conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        )
    finally:
        conn.close()
    if user is None or not verify_password(password, user["password_hash"]):
        return _redirect("/portal/login", error="Invalid email or password")
    if user.get("role") not in ("owner", "admin"):
        return _redirect("/portal/login", error="Staff accounts use the WaveBook mobile app")
    if not user.get("business_id"):
        return _redirect("/portal/login", error="No business is linked to this account")
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (user["id"],))
        conn.commit()
    finally:
        conn.close()
    response = _redirect("/portal", msg="Welcome back")
    _set_portal_cookie(response, request, user["id"])
    if user.get("must_change_password"):
        response = _redirect("/portal/change-password", msg="Please set a new password")
        _set_portal_cookie(response, request, user["id"])
    return response


@router.get("/change-password", response_class=HTMLResponse)
def portal_change_password_page(request: Request):
    user = _require_portal_user(request)
    return templates.TemplateResponse(
        request,
        "portal_change_password.html",
        {"error": request.query_params.get("error"), "msg": request.query_params.get("msg")},
    )


@router.post("/change-password")
def portal_change_password_submit(
    request: Request, current_password: str = Form(...), new_password: str = Form(...)
):
    user = _require_portal_user(request)
    if len(new_password) < 8:
        return _redirect("/portal/change-password", error="New password must be at least 8 characters")
    conn = get_connection()
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if row is None or not verify_password(current_password, row["password_hash"]):
            return _redirect("/portal/change-password", error="Current password is incorrect")
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (hash_password(new_password), user["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal", msg="Password updated")


@router.post("/logout")
def portal_logout():
    response = _redirect("/portal/login", msg="You have been signed out")
    response.delete_cookie(PORTAL_COOKIE)
    return response


# ---- Dashboard ----


@router.get("", response_class=HTMLResponse)
def portal_dashboard(request: Request):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")

    conn = get_connection()
    try:
        availability = get_availability_row(
            conn.execute(
                "SELECT * FROM availability WHERE business_id = ?", (business["id"],)
            ).fetchone()
        )
        staff_rows = conn.execute(
            """SELECT s.id, s.active, u.email, u.full_name, u.phone
               FROM staff s JOIN users u ON u.id = s.user_id
               WHERE s.business_id = ? ORDER BY s.id""",
            (business["id"],),
        ).fetchall()
        products = rows_to_dicts(
            conn.execute(
                "SELECT * FROM products WHERE business_id = ? ORDER BY sort_order, id",
                (business["id"],),
            ).fetchall()
        )
        _attach_images(conn, products)
        order_rows = conn.execute(
            "SELECT * FROM orders WHERE business_id = ? ORDER BY id DESC",
            (business["id"],),
        ).fetchall()
        orders = []
        for row in order_rows:
            order = dict(row)
            try:
                order["items"] = json.loads(order.get("items") or "[]")
            except json.JSONDecodeError:
                order["items"] = []
            orders.append(order)
        services = rows_to_dicts(
            conn.execute(
                "SELECT * FROM services WHERE business_id = ? ORDER BY sort_order, id",
                (business["id"],),
            ).fetchall()
        )
        bookings = rows_to_dicts(
            conn.execute(
                "SELECT * FROM bookings WHERE business_id = ? ORDER BY date DESC, time DESC LIMIT 200",
                (business["id"],),
            ).fetchall()
        )
        feedback = rows_to_dicts(
            conn.execute(
                "SELECT * FROM feedback WHERE business_id = ? ORDER BY id DESC",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "portal_dashboard.html",
        {
            "user": user,
            "business": business,
            "availability": availability,
            "staff": [dict(r) for r in staff_rows],
            "products": products,
            "orders": orders,
            "order_statuses": settings.ORDER_STATUSES,
            "services": services,
            "bookings": bookings,
            "booking_statuses": ("pending", "confirmed", "cancelled"),
            "feedback": feedback,
            "counts": _counts(business["id"]),
            "day_order": DAY_ORDER,
            "day_labels": DAY_LABELS,
            "currencies": sorted(SUPPORTED_CURRENCIES),
            "currency_symbols": CURRENCY_SYMBOLS,
            "payout_countries": PAYOUT_COUNTRIES,
            "website_url": f"https://{business['slug']}.{settings.PUBLIC_BASE_DOMAIN}",
            "active_tab": request.query_params.get("tab", "overview"),
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


# ---- Calendar ----


@router.post("/calendar")
def portal_calendar_save(
    request: Request,
    slot_interval: int = Form(30),
    blocked_dates: str = Form(""),
    mon_enabled: str = Form(""),
    mon_start: str = Form("09:00"),
    mon_end: str = Form("17:00"),
    tue_enabled: str = Form(""),
    tue_start: str = Form("09:00"),
    tue_end: str = Form("17:00"),
    wed_enabled: str = Form(""),
    wed_start: str = Form("09:00"),
    wed_end: str = Form("17:00"),
    thu_enabled: str = Form(""),
    thu_start: str = Form("09:00"),
    thu_end: str = Form("17:00"),
    fri_enabled: str = Form(""),
    fri_start: str = Form("09:00"),
    fri_end: str = Form("17:00"),
    sat_enabled: str = Form(""),
    sat_start: str = Form("09:00"),
    sat_end: str = Form("17:00"),
    sun_enabled: str = Form(""),
    sun_start: str = Form("09:00"),
    sun_end: str = Form("17:00"),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")

    working_days = {}
    for day in DAY_ORDER:
        enabled = locals().get(f"{day}_enabled") == "on"
        start = locals().get(f"{day}_start") or "09:00"
        end = locals().get(f"{day}_end") or "17:00"
        working_days[day] = {"enabled": enabled, "start": start, "end": end}

    dates = [line.strip() for line in blocked_dates.splitlines() if line.strip()]

    try:
        update_availability(
            data=AvailabilityUpdate(
                working_days=working_days,
                blocked_dates=dates,
                slot_interval=max(5, min(240, slot_interval)),
            ),
            business=business,
            user=user,
        )
    except HTTPException as exc:
        return _redirect("/portal?tab=calendar", error=exc.detail)
    return _redirect("/portal?tab=calendar", msg="Calendar settings saved")


# ---- Staff ----


@router.post("/staff")
def portal_staff_invite(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    try:
        invite_staff(
            data=StaffInvite(full_name=full_name, email=email, phone=phone),
            business=business,
            user=user,
        )
    except HTTPException as exc:
        return _redirect("/portal?tab=staff", error=exc.detail)
    return _redirect("/portal?tab=staff", msg="Staff member invited")


@router.post("/staff/{staff_id}/toggle")
def portal_staff_toggle(staff_id: int, request: Request, active: str = Form("")):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    try:
        update_staff(
            staff_id=staff_id,
            data=StaffUpdate(active=active == "on"),
            business=business,
            user=user,
        )
    except HTTPException as exc:
        return _redirect("/portal?tab=staff", error=exc.detail)
    return _redirect("/portal?tab=staff", msg="Staff member updated")


@router.post("/staff/{staff_id}/remove")
def portal_staff_remove(staff_id: int, request: Request):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    try:
        remove_staff(staff_id=staff_id, business=business, user=user)
    except HTTPException as exc:
        return _redirect("/portal?tab=staff", error=exc.detail)
    return _redirect("/portal?tab=staff", msg="Staff member removed")


# ---- Payments ----


@router.post("/payments")
def portal_payments_save(
    request: Request,
    currency: str = Form("GBP"),
    deposit_amount: float = Form(0.0),
    payout_country: str = Form("GB"),
    payout_bank_name: str = Form(""),
    payout_account_name: str = Form(""),
    payout_account_number: str = Form(""),
    payout_sort_code: str = Form(""),
    payout_routing_number: str = Form(""),
    payout_iban: str = Form(""),
    payout_swift: str = Form(""),
    payout_bank_address: str = Form(""),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    try:
        update_business(
            data=BusinessUpdate(
                currency=currency,
                deposit_amount=max(0.0, deposit_amount),
                payout_country=payout_country.strip().upper(),
                payout_bank_name=payout_bank_name.strip(),
                payout_account_name=payout_account_name.strip(),
                payout_account_number=payout_account_number.strip(),
                payout_sort_code=payout_sort_code.strip(),
                payout_routing_number=payout_routing_number.strip(),
                payout_iban=payout_iban.strip(),
                payout_swift=payout_swift.strip(),
                payout_bank_address=payout_bank_address.strip(),
            ),
            business=business,
        )
    except HTTPException as exc:
        return _redirect("/portal?tab=payments", error=exc.detail)
    return _redirect("/portal?tab=payments", msg="Payment settings saved")


# ---- Services ----


@router.post("/services")
def portal_service_add(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(0.0),
    duration_minutes: int = Form(60),
    sort_order: int = Form(0),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    if not name.strip() or not (5 <= duration_minutes <= 1440) or price < 0:
        return _redirect("/portal?tab=services", error="Enter a service name, a valid price and duration")
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO services (business_id, name, description, price, duration_minutes, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (business["id"], name.strip(), description.strip(), price, duration_minutes, sort_order),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal?tab=services", msg="Service added")


@router.post("/services/{service_id}")
def portal_service_update(
    request: Request,
    service_id: int,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(0.0),
    duration_minutes: int = Form(60),
    sort_order: int = Form(0),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    if not name.strip() or not (5 <= duration_minutes <= 1440) or price < 0:
        return _redirect("/portal?tab=services", error="Enter a service name, a valid price and duration")
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT id FROM services WHERE id = ? AND business_id = ?",
            (service_id, business["id"]),
        ).fetchone()
        if not exists:
            return _redirect("/portal?tab=services", error="Service not found")
        conn.execute(
            "UPDATE services SET name = ?, description = ?, price = ?, duration_minutes = ?, "
            "sort_order = ? WHERE id = ? AND business_id = ?",
            (name.strip(), description.strip(), price, duration_minutes, sort_order, service_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal?tab=services", msg="Service updated")


@router.post("/services/{service_id}/delete")
def portal_service_delete(request: Request, service_id: int):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM services WHERE id = ? AND business_id = ?",
            (service_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal?tab=services", msg="Service deleted")


# ---- Bookings ----


@router.post("/bookings/{booking_id}/status")
def portal_booking_status(request: Request, booking_id: int, status: str = Form(...)):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    if status not in ("pending", "confirmed", "cancelled"):
        return _redirect("/portal?tab=bookings", error="Invalid booking status")
    try:
        update_booking_status(
            booking_id=booking_id,
            data=BookingStatusUpdate(status=status),
            business=business,
            user=user,
        )
    except HTTPException as exc:
        return _redirect("/portal?tab=bookings", error=exc.detail)
    return _redirect("/portal?tab=bookings", msg=f"Booking {status}")


# ---- Feedback ----


@router.post("/feedback/{feedback_id}/toggle")
def portal_feedback_toggle(request: Request, feedback_id: int):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT approved FROM feedback WHERE id = ? AND business_id = ?",
            (feedback_id, business["id"]),
        ).fetchone()
        if not row:
            return _redirect("/portal?tab=feedback", error="Review not found")
        conn.execute(
            "UPDATE feedback SET approved = ? WHERE id = ? AND business_id = ?",
            (0 if row["approved"] else 1, feedback_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal?tab=feedback", msg="Review updated")


@router.post("/feedback/{feedback_id}/delete")
def portal_feedback_delete(request: Request, feedback_id: int):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM feedback WHERE id = ? AND business_id = ?",
            (feedback_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal?tab=feedback", msg="Review removed")


# ---- Shop ----


def _product_row(conn, business_id: int, product_id: int):
    return conn.execute(
        "SELECT * FROM products WHERE id = ? AND business_id = ?",
        (product_id, business_id),
    ).fetchone()


def _stock_value(raw: str) -> int | None:
    raw = (raw or "").strip()
    return int(raw) if raw else None


@router.post("/shop")
def portal_shop_save(
    request: Request,
    storefront_enabled: str = Form(""),
    store_country: str = Form("GB"),
    shipping_fee_local: float = Form(0.0),
    shipping_fee_international: float = Form(0.0),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    try:
        update_business(
            data=BusinessUpdate(
                storefront_enabled=storefront_enabled == "on",
                store_country=(store_country or "GB").strip().upper(),
                shipping_fee_local=max(0.0, shipping_fee_local),
                shipping_fee_international=max(0.0, shipping_fee_international),
            ),
            business=business,
        )
    except HTTPException as exc:
        return _redirect("/portal?tab=shop", error=exc.detail)
    return _redirect("/portal?tab=shop", msg="Shop settings saved")


@router.post("/products")
def portal_product_add(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(0.0),
    sort_order: int = Form(0),
    stock: str = Form(""),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    if not name.strip() or price <= 0:
        return _redirect("/portal?tab=shop", error="Enter a product name and a price above 0")
    max_products = business_tier_features(business)["max_products"]
    conn = get_connection()
    try:
        if max_products is not None:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM products WHERE business_id = ?",
                (business["id"],),
            ).fetchone()["c"]
            if count >= max_products:
                return _redirect(
                    "/portal?tab=shop",
                    error=f"Your plan allows up to {max_products} products. Upgrade for unlimited products.",
                )
        conn.execute(
            "INSERT INTO products (business_id, name, description, price, sort_order, stock) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (business["id"], name.strip(), description.strip(), price, sort_order, _stock_value(stock)),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal?tab=shop", msg="Product added")


@router.post("/products/{product_id}")
def portal_product_update(
    request: Request,
    product_id: int,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(0.0),
    sort_order: int = Form(0),
    stock: str = Form(""),
    active: str = Form(""),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    if not name.strip() or price <= 0:
        return _redirect("/portal?tab=shop", error="Enter a product name and a price above 0")
    conn = get_connection()
    try:
        if not _product_row(conn, business["id"], product_id):
            return _redirect("/portal?tab=shop", error="Product not found")
        conn.execute(
            "UPDATE products SET name = ?, description = ?, price = ?, sort_order = ?, "
            "stock = ?, active = ? WHERE id = ? AND business_id = ?",
            (
                name.strip(),
                description.strip(),
                price,
                sort_order,
                _stock_value(stock),
                1 if active == "on" else 0,
                product_id,
                business["id"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal?tab=shop", msg="Product updated")


@router.post("/products/{product_id}/delete")
def portal_product_delete(request: Request, product_id: int):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    conn = get_connection()
    try:
        row = _product_row(conn, business["id"], product_id)
        if not row:
            return _redirect("/portal?tab=shop", error="Product not found")
        stored = {r["path"] for r in conn.execute(
            "SELECT path FROM product_images WHERE product_id = ?", (product_id,)
        ).fetchall()}
        if row["image_path"]:
            stored.add(row["image_path"])
        conn.execute("DELETE FROM products WHERE id = ? AND business_id = ?", (product_id, business["id"]))
        conn.commit()
    finally:
        conn.close()
    for path in stored:
        _delete_stored_image(path)
    return _redirect("/portal?tab=shop", msg="Product deleted")


@router.post("/products/{product_id}/images")
def portal_product_image_add(request: Request, product_id: int, file: UploadFile = File(...)):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    if not file.filename:
        return _redirect("/portal?tab=shop", error="Choose an image first")
    try:
        _add_product_image(business, product_id, file)
    except HTTPException as exc:
        return _redirect("/portal?tab=shop", error=exc.detail)
    return _redirect("/portal?tab=shop", msg="Photo added")


@router.post("/products/{product_id}/images/{image_id}/delete")
def portal_product_image_delete(request: Request, product_id: int, image_id: int):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, path FROM product_images WHERE id = ? AND product_id = ? AND business_id = ?",
            (image_id, product_id, business["id"]),
        ).fetchone()
        if not row:
            return _redirect("/portal?tab=shop", error="Photo not found")
        conn.execute("DELETE FROM product_images WHERE id = ?", (image_id,))
        remaining = conn.execute(
            "SELECT path FROM product_images WHERE product_id = ? ORDER BY id LIMIT 1", (product_id,)
        ).fetchone()
        conn.execute(
            "UPDATE products SET image_path = ? WHERE id = ? AND business_id = ?",
            (remaining["path"] if remaining else "", product_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    _delete_stored_image(row["path"])
    return _redirect("/portal?tab=shop", msg="Photo removed")


@router.post("/orders/{order_id}/status")
def portal_order_status(request: Request, order_id: int, status: str = Form(...)):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    if status not in settings.ORDER_STATUSES:
        return _redirect("/portal?tab=shop", error="Invalid order status")
    conn = get_connection()
    try:
        order = conn.execute(
            "SELECT id FROM orders WHERE id = ? AND business_id = ?",
            (order_id, business["id"]),
        ).fetchone()
        if not order:
            return _redirect("/portal?tab=shop", error="Order not found")
        conn.execute(
            "UPDATE orders SET status = ? WHERE id = ? AND business_id = ?",
            (status, order_id, business["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return _redirect("/portal?tab=shop", msg="Order updated")


# ---- Customization ----


@router.post("/customize")
def portal_customize_save(
    request: Request,
    name: str = Form(...),
    tagline: str = Form(""),
    about_text: str = Form(""),
    rules: str = Form(""),
    contact_phone: str = Form(""),
    contact_email: str = Form(""),
    address: str = Form(""),
    instagram: str = Form(""),
    facebook: str = Form(""),
    tiktok: str = Form(""),
    opening_hours: str = Form(""),
    theme_color: str = Form("#ec4899"),
    storefront_enabled: str = Form(""),
):
    user = _require_portal_user(request)
    business = _load_business(user)
    if business is None:
        return _redirect("/portal/login", error="No business is linked to this account")
    try:
        update_business(
            data=BusinessUpdate(
                name=name.strip(),
                tagline=tagline.strip(),
                about_text=about_text.strip(),
                rules=rules.strip(),
                contact_phone=contact_phone.strip(),
                contact_email=contact_email.strip(),
                address=address.strip(),
                instagram=instagram.strip(),
                facebook=facebook.strip(),
                tiktok=tiktok.strip(),
                opening_hours=opening_hours.strip(),
                theme_color=theme_color.strip() or "#ec4899",
                storefront_enabled=storefront_enabled == "on",
            ),
            business=business,
        )
    except HTTPException as exc:
        return _redirect("/portal?tab=customize", error=exc.detail)
    return _redirect("/portal?tab=customize", msg="Website settings saved")


# ---- Account ----


@router.post("/account")
def portal_account_save(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
):
    user = _require_portal_user(request)
    try:
        change_password(
            data=ChangePasswordRequest(
                current_password=current_password, new_password=new_password
            ),
            user=user,
        )
    except HTTPException as exc:
        return _redirect("/portal?tab=account", error=exc.detail)
    return _redirect("/portal?tab=account", msg="Password changed")
