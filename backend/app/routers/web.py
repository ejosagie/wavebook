import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..database import TRIAL_DAYS_KEY, get_connection, get_trial_days, row_to_dict, rows_to_dicts
from ..phone import validate_phone
from ..routers.auth import register_user
from ..routers.bookings import generate_reference
from ..routers.notifications import add_notification
from ..routers.payments import verify_payment as verify_booking_payment
from ..schemas import SignupRequest
from ..security import create_admin_token, decode_admin_token
from ..services import flutterwave
from ..services.assistant import build_assistant_response
from ..services.ics import build_business_feed_ics
from ..services.emailer import send_booking_received_email, send_owner_new_booking_email
from ..services import emailer
from ..services.notifier import send_business_sms
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
templates.env.globals["trial_days"] = get_trial_days

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"

# ---- Helpers ----


def _get_business_by_slug(slug: str) -> dict | None:
    conn = get_connection()
    try:
        business = row_to_dict(conn.execute("SELECT * FROM businesses WHERE slug = ?", (slug,)).fetchone())
    finally:
        conn.close()
    if business:
        business["theme_color_dark"] = _darken_hex(business.get("theme_color") or "#ec4899")
    return business


def _darken_hex(hex_color: str) -> str:
    """Return a darker shade of a #rrggbb color (used for the tenant site theme)."""
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return hex_color
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        factor = 0.8
        return "#{:02x}{:02x}{:02x}".format(
            int(r * factor), int(g * factor), int(b * factor)
        )
    except ValueError:
        return hex_color


def _tenant_slug(request: Request, path_slug: str | None = None) -> str | None:
    """Resolve tenant slug from subdomain or /t/{slug} path (for local dev)."""
    if path_slug:
        return path_slug
    host = request.headers.get("host", "").split(":")[0].lower()
    base = settings.PUBLIC_BASE_DOMAIN.lower()
    if host.endswith("." + base) and host != base:
        return host[: -(len(base) + 1)]
    return None


def _tenant_base(request: Request, slug: str) -> str:
    """URL prefix for tenant links: '' on the tenant subdomain, '/t/{slug}' on path access."""
    return "" if _tenant_slug(request) == slug else f"/t/{slug}"


def _record_visit(page: str) -> None:
    """Count a public page visit (used for the admin home/download counters)."""
    conn = get_connection()
    try:
        conn.execute("INSERT INTO page_visits (page) VALUES (?)", (page,))
        conn.commit()
    finally:
        conn.close()


CURRENCY_SYMBOLS = {
    "GBP": "£",
    "USD": "$",
    "CAD": "C$",
    "EUR": "€",
    "AUD": "A$",
    "NZD": "NZ$",
    "NGN": "₦",
    "KES": "KSh",
    "ZAR": "R",
}


def _format_price(amount: float, currency: str = "GBP") -> str:
    code = (currency or "GBP").upper()
    symbol = CURRENCY_SYMBOLS.get(code, f"{code} ")
    return f"{symbol}{amount:,.2f}"


def _format_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} hour{'s' if h > 1 else ''} {m} min"
    if h:
        return f"{h} hour{'s' if h > 1 else ''}"
    return f"{m} minutes"

def _is_admin(request: Request) -> bool:
    token = request.cookies.get("wavebook_admin")
    return bool(token and decode_admin_token(token))


def _set_admin_cookie(response, request: Request) -> None:
    response.set_cookie(
        "wavebook_admin",
        create_admin_token(),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=7 * 24 * 3600,
    )


# ---- Landing page ----


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse(request, "signup.html", {"error": None})


@router.post("/signup")
def signup_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(default=""),
    slug: str = Form(default=""),
    currency: str = Form(default="GBP"),
):
    """Create the account and business from the landing page, then show download instructions."""
    try:
        data = SignupRequest(
            email=email,
            password=password,
            full_name=full_name,
            phone=phone,
            business_name=business_name or None,
            slug=slug or None,
            currency=currency,
        )
        register_user(data)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request, "signup.html", {"error": exc.detail}, status_code=exc.status_code
        )
    except Exception:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {"error": "Something went wrong. Please try again."},
            status_code=400,
        )
    return RedirectResponse(url="/signup/success", status_code=303)


@router.get("/signup/success", response_class=HTMLResponse)
def signup_success(request: Request):
    return templates.TemplateResponse(request, "signup_success.html", {})


@router.get("/support", response_class=HTMLResponse)
def support_page(request: Request):
    return templates.TemplateResponse(request, "support.html", {})


@router.get("/download", response_class=HTMLResponse)
def download_page(request: Request):
    _record_visit("download")
    return templates.TemplateResponse(request, "download.html", {})


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {})


@router.get("/copyright", response_class=HTMLResponse)
def copyright_page(request: Request):
    return templates.TemplateResponse(request, "copyright.html", {})


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, access: str | None = None):
    if access and settings.ADMIN_ACCESS_TOKEN and access == settings.ADMIN_ACCESS_TOKEN:
        # Gateway to the admin area — the login page still asks for the password.
        return RedirectResponse(url="/admin", status_code=303)
    _record_visit("home")
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
        {
            "price_gbp": settings.SUBSCRIPTION_PRICE_GBP,
            "plans": settings.SUBSCRIPTION_PLANS,
            "interval_labels": settings.INTERVAL_LABELS,
        },
    )


@router.get("/subscribe/success", response_class=HTMLResponse)
def subscribe_success(request: Request):
    return templates.TemplateResponse(request, "subscribe_success.html", {})


@router.get("/subscribe/cancel", response_class=HTMLResponse)
def subscribe_cancel(request: Request):
    return templates.TemplateResponse(request, "subscribe_cancel.html", {})


@router.get("/subscribe/verify", response_class=HTMLResponse)
def subscribe_verify(request: Request, tx_ref: str = "", transaction_id: str = ""):
    """Flutterwave redirect handler for subscription payments."""
    if not tx_ref or not transaction_id:
        return templates.TemplateResponse(request, "subscribe_cancel.html", {})
    try:
        data = flutterwave.verify_transaction(transaction_id)
    except HTTPException:
        return templates.TemplateResponse(request, "subscribe_cancel.html", {})
    if data.get("status") != "successful" or data.get("tx_ref") != tx_ref:
        return templates.TemplateResponse(request, "subscribe_cancel.html", {})

    business_id = 0
    plan_key = (data.get("meta") or {}).get("plan") or "basic_monthly"
    if tx_ref.startswith("WB-SUB-"):
        parts = tx_ref.split("-")
        try:
            business_id = int(parts[2])
        except (IndexError, ValueError):
            business_id = 0
        # Older refs lack the plan segment; meta is authoritative when present
        if plan_key not in settings.SUBSCRIPTION_PLANS and len(parts) > 3:
            plan_key = parts[3]
    plan_key = settings.LEGACY_PLAN_KEYS.get(plan_key, plan_key)
    if plan_key not in settings.SUBSCRIPTION_PLANS:
        plan_key = "basic_monthly"
    plan = settings.SUBSCRIPTION_PLANS[plan_key]
    if not business_id:
        return templates.TemplateResponse(request, "subscribe_cancel.html", {})

    paid = float(data.get("amount") or 0)
    if paid < plan["price"]:
        return templates.TemplateResponse(request, "subscribe_cancel.html", {})

    conn = get_connection()
    try:
        # Idempotency: never activate twice for the same Flutterwave transaction
        existing = conn.execute(
            "SELECT id FROM subscriptions WHERE stripe_subscription_id = ?", (tx_ref,)
        ).fetchone()
        if existing:
            return templates.TemplateResponse(request, "subscribe_success.html", {})
        # Every paid plan includes the storefront; product caps differ by tier.
        conn.execute(
            "UPDATE businesses SET subscription_status = 'active', storefront_enabled = 1 WHERE id = ?",
            (business_id,),
        )
        conn.execute(
            "INSERT INTO subscriptions (business_id, stripe_subscription_id, status, plan, amount) "
            "VALUES (?, ?, 'active', ?, ?)",
            (business_id, tx_ref, plan_key, paid),
        )
        conn.commit()
    finally:
        conn.close()
    return templates.TemplateResponse(request, "subscribe_success.html", {})


@router.get("/pay/verify")
def pay_verify(request: Request, tx_ref: str = "", transaction_id: str = ""):
    """Flutterwave redirect handler — then show the relevant success page."""
    try:
        result = verify_booking_payment(tx_ref=tx_ref, transaction_id=transaction_id)
    except HTTPException:
        return RedirectResponse(url="/", status_code=303)

    if "order_id" in result:
        order_id = result["order_id"]
        conn = get_connection()
        try:
            order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not order:
                return RedirectResponse(url="/", status_code=303)
            slug = conn.execute(
                "SELECT slug FROM businesses WHERE id = ?", (order["business_id"],)
            ).fetchone()["slug"]
        finally:
            conn.close()
        return RedirectResponse(url=f"/t/{slug}/store/order/{order_id}/success", status_code=303)

    if "business_id" in result:
        return templates.TemplateResponse(request, "pay_success.html", {"kind": "sms"})

    booking_id = result["booking_id"]
    conn = get_connection()
    try:
        booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if not booking:
            return RedirectResponse(url="/", status_code=303)
        slug = conn.execute(
            "SELECT slug FROM businesses WHERE id = ?", (booking["business_id"],)
        ).fetchone()["slug"]
    finally:
        conn.close()
    return RedirectResponse(url=f"/t/{slug}/booking/{booking_id}/paid", status_code=303)


# ---- App metadata (update checks, managed by the platform admin) ----

APP_META_DEFAULTS = {
    "latest_version": "",
    "update_url": "",
    "update_message": "",
}


@router.get("/api/app/meta")
def app_meta():
    """Public app metadata — the Flutter app checks this for update notices."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT key, value FROM app_meta").fetchall()
    finally:
        conn.close()
    meta = dict(APP_META_DEFAULTS)
    for row in rows:
        meta[row["key"]] = row["value"]
    return meta


@router.post("/admin/app-meta")
def admin_update_app_meta(
    request: Request,
    latest_version: str = Form(default=""),
    update_url: str = Form(default=""),
    update_message: str = Form(default=""),
):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    conn = get_connection()
    try:
        for key, value in {
            "latest_version": latest_version.strip(),
            "update_url": update_url.strip(),
            "update_message": update_message.strip(),
        }.items():
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/trial-days")
def admin_update_trial_days(request: Request, trial_days: int = Form(...)):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    if not 1 <= trial_days <= 90:
        return RedirectResponse(url="/admin", status_code=303)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (TRIAL_DAYS_KEY, str(trial_days)),
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ---- Owner admin dashboard ----

ADMIN_COOKIE = "wavebook_admin"
ADMIN_PAGE_SIZE = 25


def _admin_page(page: int, total: int) -> tuple[int, int, int]:
    total_pages = max(1, (total + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
    page = max(1, min(page, total_pages))
    return page, total_pages, (page - 1) * ADMIN_PAGE_SIZE


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, page: int = 1):
    if not _is_admin(request):
        return templates.TemplateResponse(
            request, "admin_login.html", {"error": None}, status_code=401
        )
    conn = get_connection()
    try:
        total_businesses = conn.execute(
            "SELECT COUNT(*) AS c FROM businesses"
        ).fetchone()["c"]
        page, total_pages, offset = _admin_page(page, total_businesses)
        businesses = rows_to_dicts(
            conn.execute(
                """SELECT b.*,
                          (SELECT COUNT(*) FROM bookings bk WHERE bk.business_id = b.id) AS booking_count,
                          (SELECT COUNT(*) FROM bookings bk WHERE bk.business_id = b.id AND bk.status = 'pending') AS pending_count
                   FROM businesses b ORDER BY b.created_at DESC LIMIT ? OFFSET ?""",
                (ADMIN_PAGE_SIZE, offset),
            ).fetchall()
        )
        total_bookings = conn.execute("SELECT COUNT(*) AS c FROM bookings").fetchone()["c"]
        active_subs = conn.execute(
            "SELECT COUNT(*) AS c FROM businesses WHERE subscription_status = 'active'"
        ).fetchone()["c"]
        meta_rows = conn.execute("SELECT key, value FROM app_meta").fetchall()
    finally:
        conn.close()
    meta = dict(APP_META_DEFAULTS)
    for row in meta_rows:
        meta[row["key"]] = row["value"]
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "businesses": businesses,
            "total_businesses": total_businesses,
            "total_bookings": total_bookings,
            "active_subs": active_subs,
            "app_meta": meta,
            "trial_days": get_trial_days(),
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if settings.ADMIN_PASSWORD and password == settings.ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin", status_code=303)
        _set_admin_cookie(response, request)
        return response
    return templates.TemplateResponse(
        request, "admin_login.html", {"error": "Incorrect password"}, status_code=401
    )


@router.post("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(ADMIN_COOKIE)
    return response


def _admin_or_login(request: Request):
    """Return the admin dashboard response if not authenticated."""
    if not _is_admin(request):
        return templates.TemplateResponse(
            request, "admin_login.html", {"error": None}, status_code=401
        )
    return None


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, page: int = 1):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        page, total_pages, offset = _admin_page(page, total)
        users = rows_to_dicts(
            conn.execute(
                """SELECT u.*, b.name AS business_name, b.slug AS business_slug,
                          b.subscription_status,
                          sub.created_at AS sub_start,
                          sub.plan AS sub_plan,
                          CASE
                            WHEN sub.plan LIKE '%_yearly' THEN date(sub.created_at, '+12 months')
                            WHEN sub.plan LIKE '%_biannual' THEN date(sub.created_at, '+6 months')
                            WHEN sub.plan LIKE '%_quarterly' THEN date(sub.created_at, '+3 months')
                            ELSE date(sub.created_at, '+1 month')
                          END AS sub_end
                   FROM users u
                   LEFT JOIN businesses b ON b.id = u.business_id
                   LEFT JOIN subscriptions sub ON sub.id = (
                       SELECT id FROM subscriptions s
                       WHERE s.business_id = u.business_id
                       ORDER BY s.created_at DESC LIMIT 1
                   )
                   ORDER BY u.created_at DESC LIMIT ? OFFSET ?""",
                (ADMIN_PAGE_SIZE, offset),
            ).fetchall()
        )
        for u in users:
            if u.get("role") == "staff":
                # Staff don't subscribe — the business does. Don't show the
                # business's subscription on their row.
                u["sub_plan"] = None
                u["sub_start"] = None
                u["sub_end"] = None
                u["sub_plan_label"] = ""
                u["is_demo"] = False
            else:
                u["is_demo"] = u.get("business_slug") == "demo"
                u["sub_plan_label"] = settings.TIER_LABELS.get(
                    (u.get("sub_plan") or "").rsplit("_", 1)[0], u.get("sub_plan") or ""
                )
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {"users": users, "total": total, "page": page, "total_pages": total_pages},
    )


@router.post("/admin/users/{user_id}/role")
def admin_user_role(request: Request, user_id: int, role: str = Form(...)):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    if role not in ("owner", "staff", "admin"):
        return RedirectResponse(url="/admin/users", status_code=303)
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/delete")
def admin_user_delete(request: Request, user_id: int):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/businesses/{business_id}/subscription")
def admin_business_subscription(request: Request, business_id: int, status: str = Form(...)):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    if status not in ("trial", "active", "past_due", "cancelled"):
        return RedirectResponse(url="/admin", status_code=303)
    conn = get_connection()
    try:
        conn.execute("UPDATE businesses SET subscription_status = ? WHERE id = ?", (status, business_id))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/businesses/{business_id}/delete")
def admin_business_delete(request: Request, business_id: int):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM businesses WHERE id = ?", (business_id,))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/admin/feedback", response_class=HTMLResponse)
def admin_feedback(request: Request, page: int = 1):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM feedback").fetchone()["c"]
        page, total_pages, offset = _admin_page(page, total)
        feedback = rows_to_dicts(
            conn.execute(
                """SELECT f.*, b.name AS business_name, b.slug AS business_slug
                   FROM feedback f JOIN businesses b ON b.id = f.business_id
                   ORDER BY f.created_at DESC LIMIT ? OFFSET ?""",
                (ADMIN_PAGE_SIZE, offset),
            ).fetchall()
        )
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "admin_feedback.html",
        {"feedback": feedback, "total": total, "page": page, "total_pages": total_pages},
    )


@router.post("/admin/feedback/{feedback_id}/approve")
def admin_feedback_approve(request: Request, feedback_id: int, approved: int = Form(...)):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    conn = get_connection()
    try:
        conn.execute("UPDATE feedback SET approved = ? WHERE id = ?", (1 if approved else 0, feedback_id))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/admin/feedback", status_code=303)


@router.post("/admin/feedback/{feedback_id}/delete")
def admin_feedback_delete(request: Request, feedback_id: int):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/admin/feedback", status_code=303)


@router.get("/admin/bookings", response_class=HTMLResponse)
def admin_bookings(request: Request, page: int = 1, from_date: str = "", to_date: str = ""):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    page = max(page, 1)
    per_page = 50
    where = ""
    params: list = []
    if from_date:
        where += " AND bk.date >= ?"
        params.append(from_date)
    if to_date:
        where += " AND bk.date <= ?"
        params.append(to_date)
    conn = get_connection()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM bookings bk WHERE 1=1{where}", params
        ).fetchone()["c"]
        bookings = rows_to_dicts(
            conn.execute(
                f"""SELECT bk.*, b.name AS business_name, b.slug AS business_slug
                    FROM bookings bk JOIN businesses b ON b.id = bk.business_id
                    WHERE 1=1{where}
                    ORDER BY bk.date DESC, bk.time DESC
                    LIMIT ? OFFSET ?""",
                params + [per_page, (page - 1) * per_page],
            ).fetchall()
        )
    finally:
        conn.close()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(
        request,
        "admin_bookings.html",
        {
            "bookings": bookings,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "from_date": from_date,
            "to_date": to_date,
        },
    )


@router.get("/admin/metrics", response_class=HTMLResponse)
def admin_metrics(request: Request):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    conn = get_connection()
    try:
        def one(sql: str, params=()) -> int:
            return conn.execute(sql, params).fetchone()["c"]

        total_users = one("SELECT COUNT(*) AS c FROM users")
        new_users_30d = one(
            "SELECT COUNT(*) AS c FROM users WHERE created_at >= datetime('now', '-30 days')"
        )
        owners = one("SELECT COUNT(*) AS c FROM users WHERE role = 'owner'")
        staff = one("SELECT COUNT(*) AS c FROM users WHERE role = 'staff'")
        admins = one("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")

        total_businesses = one("SELECT COUNT(*) AS c FROM businesses")
        new_businesses_30d = one(
            "SELECT COUNT(*) AS c FROM businesses WHERE created_at >= datetime('now', '-30 days')"
        )
        active_subs = one(
            "SELECT COUNT(*) AS c FROM businesses WHERE subscription_status = 'active'"
        )
        trial_subs = one(
            "SELECT COUNT(*) AS c FROM businesses WHERE subscription_status = 'trial'"
        )
        past_due = one(
            "SELECT COUNT(*) AS c FROM businesses WHERE subscription_status = 'past_due'"
        )
        cancelled = one(
            "SELECT COUNT(*) AS c FROM businesses WHERE subscription_status = 'cancelled'"
        )

        total_bookings = one("SELECT COUNT(*) AS c FROM bookings")
        bookings_30d = one(
            "SELECT COUNT(*) AS c FROM bookings WHERE created_at >= datetime('now', '-30 days')"
        )
        pending = one("SELECT COUNT(*) AS c FROM bookings WHERE status = 'pending'")
        confirmed = one("SELECT COUNT(*) AS c FROM bookings WHERE status = 'confirmed'")
        cancelled_bookings = one(
            "SELECT COUNT(*) AS c FROM bookings WHERE status = 'cancelled'"
        )
        revenue_30d = conn.execute(
            """SELECT COALESCE(SUM(service_price), 0) AS s FROM bookings
               WHERE status != 'cancelled' AND created_at >= datetime('now', '-30 days')"""
        ).fetchone()["s"]

        feedback_total = one("SELECT COUNT(*) AS c FROM feedback")
        feedback_approved = one("SELECT COUNT(*) AS c FROM feedback WHERE approved = 1")
        avg_rating = conn.execute(
            "SELECT COALESCE(AVG(rating), 0) AS s FROM feedback"
        ).fetchone()["s"]

        recent_logins = rows_to_dicts(
            conn.execute(
                """SELECT full_name, email, last_login_at FROM users
                   WHERE last_login_at != '' ORDER BY last_login_at DESC LIMIT 10"""
            ).fetchall()
        )
    finally:
        conn.close()

    trial_rate = round(trial_subs / total_businesses * 100, 1) if total_businesses else 0.0
    churn_rate = (
        round(cancelled / (active_subs + cancelled) * 100, 1)
        if (active_subs + cancelled)
        else 0.0
    )
    return templates.TemplateResponse(
        request,
        "admin_metrics.html",
        {
            "total_users": total_users,
            "new_users_30d": new_users_30d,
            "owners": owners,
            "staff": staff,
            "admins": admins,
            "total_businesses": total_businesses,
            "new_businesses_30d": new_businesses_30d,
            "active_subs": active_subs,
            "trial_subs": trial_subs,
            "past_due": past_due,
            "cancelled": cancelled,
            "trial_rate": trial_rate,
            "churn_rate": churn_rate,
            "total_bookings": total_bookings,
            "bookings_30d": bookings_30d,
            "pending": pending,
            "confirmed": confirmed,
            "cancelled_bookings": cancelled_bookings,
            "revenue_30d": revenue_30d,
            "feedback_total": feedback_total,
            "feedback_approved": feedback_approved,
            "avg_rating": avg_rating,
            "recent_logins": recent_logins,
        },
    )


@router.get("/admin/visits", response_class=HTMLResponse)
def admin_visits(request: Request):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    conn = get_connection()
    try:
        def one(sql: str, params=()) -> int:
            return conn.execute(sql, params).fetchone()["c"]

        def page_counts(page: str) -> dict:
            return {
                "total": one(
                    "SELECT COUNT(*) AS c FROM page_visits WHERE page = ?", (page,)
                ),
                "today": one(
                    "SELECT COUNT(*) AS c FROM page_visits WHERE page = ? AND visited_at >= date('now')",
                    (page,),
                ),
                "h24": one(
                    "SELECT COUNT(*) AS c FROM page_visits WHERE page = ? AND visited_at >= datetime('now', '-24 hours')",
                    (page,),
                ),
                "d7": one(
                    "SELECT COUNT(*) AS c FROM page_visits WHERE page = ? AND visited_at >= datetime('now', '-7 days')",
                    (page,),
                ),
                "d30": one(
                    "SELECT COUNT(*) AS c FROM page_visits WHERE page = ? AND visited_at >= datetime('now', '-30 days')",
                    (page,),
                ),
            }

        home = page_counts("home")
        download = page_counts("download")
        recent = rows_to_dicts(
            conn.execute(
                "SELECT page, visited_at FROM page_visits ORDER BY id DESC LIMIT 100"
            ).fetchall()
        )
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "admin_visits.html",
        {
            "home": home,
            "download": download,
            "recent": recent,
        },
    )


@router.get("/admin/finances", response_class=HTMLResponse)
def admin_finances(
    request: Request,
    from_date: str = "",
    to_date: str = "",
    spage: int = 1,
    bpage: int = 1,
):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    conn = get_connection()
    try:
        def sum_paid(kind: str) -> float:
            return conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS s FROM payments WHERE status = 'paid' AND kind = ?",
                (kind,),
            ).fetchone()["s"]

        deposits_collected = sum_paid("deposit")
        orders_collected = sum_paid("order")
        sms_topup_collected = sum_paid("sms_topup")
        business_collected = round(deposits_collected + orders_collected, 2)
        total_settled = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s FROM settlements"
        ).fetchone()["s"]

        b_total = conn.execute("SELECT COUNT(*) AS c FROM businesses").fetchone()["c"]
        bpage, b_total_pages, b_offset = _admin_page(bpage, b_total)
        businesses = rows_to_dicts(
            conn.execute(
                """SELECT b.id, b.name, b.slug, b.subscription_status,
                          COALESCE((SELECT SUM(p.amount) FROM payments p
                                    WHERE p.business_id = b.id AND p.status = 'paid' AND p.kind IN ('deposit', 'order')), 0) AS collected,
                          COALESCE((SELECT SUM(s.amount) FROM settlements s
                                    WHERE s.business_id = b.id), 0) AS settled
                   FROM businesses b
                   ORDER BY collected DESC LIMIT ? OFFSET ?""",
                (ADMIN_PAGE_SIZE, b_offset),
            ).fetchall()
        )
        for b in businesses:
            b["outstanding"] = round(b["collected"] - b["settled"], 2)

        recent_payments = rows_to_dicts(
            conn.execute(
                """SELECT p.*, b.name AS business_name, b.slug AS business_slug
                   FROM payments p JOIN businesses b ON b.id = p.business_id
                   ORDER BY p.created_at DESC LIMIT 20"""
            ).fetchall()
        )
        settlements = rows_to_dicts(
            conn.execute(
                """SELECT s.*, b.name AS business_name, b.slug AS business_slug
                   FROM settlements s JOIN businesses b ON b.id = s.business_id
                   ORDER BY s.created_at DESC LIMIT 20"""
            ).fetchall()
        )

        # Subscription revenue (GBP) with optional date range — investor-facing.
        sub_where = "WHERE sub.status = 'active'"
        sub_params: list = []
        if from_date:
            sub_where += " AND sub.created_at >= ?"
            sub_params.append(from_date)
        if to_date:
            sub_where += " AND sub.created_at <= ?"
            sub_params.append(to_date + " 23:59:59")
        sub_total = conn.execute(
            f"SELECT COALESCE(SUM(sub.amount), 0) AS s FROM subscriptions sub {sub_where}",
            sub_params,
        ).fetchone()["s"]
        sub_count = conn.execute(
            f"SELECT COUNT(*) AS c FROM subscriptions sub {sub_where}", sub_params
        ).fetchone()["c"]
        spage, sub_total_pages, sub_offset = _admin_page(spage, sub_count)
        subscription_payments = rows_to_dicts(
            conn.execute(
                f"""SELECT sub.id, sub.plan, sub.amount, sub.created_at,
                           b.name AS business_name, b.slug AS business_slug
                    FROM subscriptions sub JOIN businesses b ON b.id = sub.business_id
                    {sub_where} ORDER BY sub.created_at DESC LIMIT ? OFFSET ?""",
                sub_params + [ADMIN_PAGE_SIZE, sub_offset],
            ).fetchall()
        )
        for sp in subscription_payments:
            sp["plan_label"] = settings.TIER_LABELS.get(
                sp["plan"].rsplit("_", 1)[0], sp["plan"]
            )
    finally:
        conn.close()
    outstanding = round(business_collected - total_settled, 2)
    return templates.TemplateResponse(
        request,
        "admin_finances.html",
        {
            "business_collected": business_collected,
            "deposits_collected": deposits_collected,
            "orders_collected": orders_collected,
            "sms_topup_collected": sms_topup_collected,
            "total_settled": total_settled,
            "outstanding": outstanding,
            "businesses": businesses,
            "recent_payments": recent_payments,
            "settlements": settlements,
            "b_total": b_total,
            "bpage": bpage,
            "b_total_pages": b_total_pages,
            "sub_total": sub_total,
            "subscription_payments": subscription_payments,
            "sub_count": sub_count,
            "spage": spage,
            "sub_total_pages": sub_total_pages,
            "from_date": from_date,
            "to_date": to_date,
        },
    )


@router.get("/admin/settlements", response_class=HTMLResponse)
def admin_settlements(request: Request, page: int = 1, bpage: int = 1):
    blocked = _admin_or_login(request)
    if blocked:
        return blocked
    conn = get_connection()
    try:
        b_total = conn.execute("SELECT COUNT(*) AS c FROM businesses").fetchone()["c"]
        bpage, b_total_pages, b_offset = _admin_page(bpage, b_total)
        businesses = rows_to_dicts(
            conn.execute(
                """SELECT b.id, b.name, b.slug, b.contact_email,
                          COALESCE((SELECT SUM(p.amount) FROM payments p
                                    WHERE p.business_id = b.id AND p.status = 'paid' AND p.kind IN ('deposit', 'order')), 0) AS collected,
                          COALESCE((SELECT SUM(s.amount) FROM settlements s
                                    WHERE s.business_id = b.id), 0) AS settled
                   FROM businesses b
                   ORDER BY collected DESC LIMIT ? OFFSET ?""",
                (ADMIN_PAGE_SIZE, b_offset),
            ).fetchall()
        )
        for b in businesses:
            b["outstanding"] = round(b["collected"] - b["settled"], 2)
        total = conn.execute("SELECT COUNT(*) AS c FROM settlements").fetchone()["c"]
        page, total_pages, offset = _admin_page(page, total)
        settlements = rows_to_dicts(
            conn.execute(
                """SELECT s.*, b.name AS business_name, b.slug AS business_slug
                   FROM settlements s JOIN businesses b ON b.id = s.business_id
                   ORDER BY s.created_at DESC LIMIT ? OFFSET ?""",
                (ADMIN_PAGE_SIZE, offset),
            ).fetchall()
        )
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "admin_settlements.html",
        {
            "businesses": businesses,
            "settlements": settlements,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "b_total": b_total,
            "bpage": bpage,
            "b_total_pages": b_total_pages,
        },
    )


@router.post("/admin/settlements")
def admin_settlement(
    request: Request,
    business_id: int = Form(...),
    amount: float = Form(...),
    method: str = Form("bank_transfer"),
    reference: str = Form(""),
    notes: str = Form(""),
    notify: bool = Form(False),
):
    if not _is_admin(request):
        return RedirectResponse(url="/admin", status_code=303)
    if amount <= 0:
        return RedirectResponse(url="/admin/settlements", status_code=303)
    conn = get_connection()
    try:
        business = conn.execute(
            "SELECT * FROM businesses WHERE id = ?", (business_id,)
        ).fetchone()
        if not business:
            return RedirectResponse(url="/admin/settlements", status_code=303)
        conn.execute(
            """INSERT INTO settlements (business_id, amount, method, reference, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (business_id, amount, method, reference, notes),
        )
        if notify:
            add_notification(
                conn,
                business_id,
                "Payment settled",
                f"WaveBook paid you {amount:.2f} {business['currency'] or 'GBP'} "
                f"via {method.replace('_', ' ').title()}"
                + (f" (reference: {reference})" if reference else ""),
                type_="settlement",
            )
        conn.commit()
    finally:
        conn.close()
    if notify:
        owner = None
        conn = get_connection()
        try:
            owner = conn.execute(
                "SELECT email, full_name FROM users WHERE business_id = ? AND role = 'owner' LIMIT 1",
                (business_id,),
            ).fetchone()
        finally:
            conn.close()
        if owner:
            emailer.send_email(
                owner["email"],
                "WaveBook — payment settled",
                f"Hi {owner['full_name']},\n\n"
                f"We've settled {amount:.2f} {business['currency'] or 'GBP'} to your business "
                f"({business['name']}) via {method.replace('_', ' ').title()}.\n"
                + (f"Reference: {reference}\n" if reference else "")
                + (f"Notes: {notes}\n" if notes else "")
                + "\nThis money was collected from your customers on your behalf.\n\n"
                "Thanks,\nThe WaveBook team",
            )
    return RedirectResponse(url="/admin/settlements", status_code=303)


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
        feedback = rows_to_dicts(
            conn.execute(
                "SELECT * FROM feedback WHERE business_id = ? AND approved = 1 ORDER BY created_at DESC LIMIT 20",
                (business["id"],),
            ).fetchall()
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
            "feedback": feedback,
            "day_labels": DAY_LABELS,
            "tenant_base": _tenant_base(request, slug),
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
            "tenant_base": _tenant_base(request, slug),
            "format_price": _format_price,
            "format_duration": _format_duration,
        },
    )


@router.get("/t/{slug}/calendar.ics", response_class=PlainTextResponse)
def tenant_calendar_feed(slug: str, token: str = ""):
    """Subscribable iCal feed of confirmed bookings for a business."""
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if business.get("calendar_token") and token != business["calendar_token"]:
        raise HTTPException(status_code=403, detail="Invalid calendar token")
    conn = get_connection()
    try:
        bookings = rows_to_dicts(
            conn.execute(
                "SELECT * FROM bookings WHERE business_id = ? AND status = 'confirmed' ORDER BY date, time",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return PlainTextResponse(
        build_business_feed_ics(bookings, business),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{slug}-calendar.ics"'},
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
        for svc in services:
            try:
                svc["questions"] = json.loads(svc.get("questions") or "[]")
            except json.JSONDecodeError:
                svc["questions"] = []
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
            "tenant_base": _tenant_base(request, slug),
            "format_price": _format_price,
            "format_duration": _format_duration,
        },
    )


@router.get("/t/{slug}/api/slots")
def tenant_slots(slug: str, date: str, service_id: str | None = None):
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    service_id = int(service_id) if service_id and service_id.strip().isdigit() else None
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


@router.post("/t/{slug}/api/assistant")
def tenant_assistant(slug: str, payload: dict):
    """Rule-based AI booking assistant — parses natural language into real slots."""
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    message = (payload.get("message") or "").strip()
    if not message:
        return {
            "reply": "Tell me what you'd like to book — for example, 'a haircut tomorrow afternoon'.",
            "services": [],
            "slots": [],
        }
    conn = get_connection()
    try:
        services = rows_to_dicts(
            conn.execute(
                "SELECT * FROM services WHERE business_id = ? ORDER BY sort_order, id",
                (business["id"],),
            ).fetchall()
        )
        availability = get_availability_row(
            conn.execute("SELECT * FROM availability WHERE business_id = ?", (business["id"],)).fetchone()
        )
    finally:
        conn.close()

    def slots_for(date_str: str, duration_minutes: int) -> list[str]:
        conn = get_connection()
        try:
            confirmed = conn.execute(
                "SELECT * FROM bookings WHERE business_id = ? AND date = ? AND status = 'confirmed'",
                (business["id"], date_str),
            ).fetchall()
        finally:
            conn.close()
        return get_available_time_slots(
            date_str,
            availability,
            rows_to_dicts(confirmed),
            duration_minutes,
            int(business["buffer_minutes"] or 30),
        )

    return build_assistant_response(
        message,
        services,
        business,
        availability,
        date.today(),
        slots_for,
    )


@router.post("/t/{slug}/feedback")
def tenant_feedback_submit(
    slug: str,
    name: str = Form(...),
    rating: int = Form(5),
    comment: str = Form(""),
):
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO feedback (business_id, customer_name, rating, comment) VALUES (?, ?, ?, ?)",
            (business["id"], name.strip(), max(1, min(5, rating)), comment.strip()),
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url=f"/t/{slug}#feedback", status_code=303)


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

    try:
        phone = validate_phone(phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
                service_name, service_price, service_duration_minutes, date, time, notes, reference, intake_answers)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                business["id"], name.strip(), email.strip(), phone, service["id"],
                service["name"], service["price"], service["duration_minutes"],
                date, time, notes.strip(), generate_reference(),
                json.dumps(await _collect_intake_answers(service, request)),
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

    # Notify the owner by text message
    if business.get("contact_phone"):
        send_business_sms(
            business,
            business["contact_phone"],
            f"New booking: {name.strip()} booked {service['name']} on {date} at {time} "
            f"({business['name']}). Ref: {booking.get('reference', booking_id)}",
        )

    # Email the customer their booking reference and manage link
    send_booking_received_email(booking, business)
    send_owner_new_booking_email(booking, business)

    return templates.TemplateResponse(
        request,
        "tenant/booking_success.html",
        {
            "business": business,
            "booking": booking,
            "deposit_amount": min(float(business["deposit_amount"] or 0), float(service["price"] or 0)),
            "tenant_base": _tenant_base(request, slug),
            "format_price": _format_price,
        },
    )


@router.get("/t/{slug}/booking/{booking_id}/paid")
def tenant_booking_paid(request: Request, slug: str, booking_id: int):
    """Landing page after a successful Flutterwave deposit payment."""
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
            "tenant_base": _tenant_base(request, slug),
            "format_price": _format_price,
        },
    )


# ---- Customer booking management portal (reschedule / cancel) ----


async def _collect_intake_answers(service, request: Request) -> dict:
    """Read `answer_<id>` form fields for the service's intake questions."""
    answers: dict[str, str] = {}
    try:
        questions = json.loads(service["questions"] or "[]")
    except json.JSONDecodeError:
        return answers
    form = await request.form()
    for q in questions:
        qid = str(q.get("id", ""))
        if not qid:
            continue
        value = (form.get(f"answer_{qid}") or "").strip()
        if q.get("required") and not value:
            raise HTTPException(status_code=400, detail=f"Please answer: {q.get('label', '')}")
        answers[qid] = value
    return answers


def _lookup_booking(reference: str, email: str) -> tuple[dict | None, dict | None]:
    """Find a booking by reference + customer email. Returns (booking, business)."""
    conn = get_connection()
    try:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE reference = ? COLLATE NOCASE AND customer_email = ? COLLATE NOCASE",
            (reference.strip(), email.strip()),
        ).fetchone()
        business = None
        if booking:
            business = row_to_dict(
                conn.execute("SELECT * FROM businesses WHERE id = ?", (booking["business_id"],)).fetchone()
            )
        return row_to_dict(booking), business
    finally:
        conn.close()


@router.get("/booking/manage", response_class=HTMLResponse)
def booking_manage_page(request: Request):
    return templates.TemplateResponse(
        request,
        "booking_manage.html",
        {"booking": None, "business": None, "error": None, "slots": [], "today": date.today().isoformat()},
    )


@router.post("/booking/manage")
def booking_manage_lookup(
    request: Request,
    email: str = Form(...),
    reference: str = Form(...),
):
    booking, business = _lookup_booking(reference, email)
    if not booking:
        return templates.TemplateResponse(
            request,
            "booking_manage.html",
            {
                "booking": None,
                "business": None,
                "error": "No booking found. Check your email address and booking reference.",
                "slots": [],
                "today": date.today().isoformat(),
            },
        )
    return templates.TemplateResponse(
        request,
        "booking_manage.html",
        {"booking": booking, "business": business, "error": None, "slots": [], "today": date.today().isoformat()},
    )


@router.post("/booking/manage/{booking_id}/reschedule")
def booking_manage_reschedule(
    request: Request,
    booking_id: int,
    email: str = Form(...),
    reference: str = Form(...),
    new_date: str = Form(...),
    time: str = Form(...),
):
    booking, business = _lookup_booking(reference, email)
    if not booking or booking["id"] != booking_id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="This booking has been cancelled")

    conn = get_connection()
    try:
        service = conn.execute(
            "SELECT * FROM services WHERE id = ? AND business_id = ?",
            (booking["service_id"], business["id"]),
        ).fetchone()
        if not service:
            raise HTTPException(status_code=400, detail="Service no longer available")
        availability = get_availability_row(
            conn.execute("SELECT * FROM availability WHERE business_id = ?", (business["id"],)).fetchone()
        )
        if is_date_blocked(new_date, availability):
            raise HTTPException(status_code=400, detail="That date is not available")
        confirmed = conn.execute(
            "SELECT * FROM bookings WHERE business_id = ? AND date = ? AND status = 'confirmed'",
            (business["id"], new_date),
        ).fetchall()
        slots = get_available_time_slots(
            new_date,
            availability,
            rows_to_dicts(confirmed),
            int(service["duration_minutes"] or 60),
            int(business["buffer_minutes"] or 30),
        )
        if time not in slots:
            raise HTTPException(status_code=400, detail="That time slot is no longer available")
        conn.execute(
            "UPDATE bookings SET date = ?, time = ?, reminder_sent = 0 WHERE id = ?",
            (new_date, time, booking_id),
        )
        conn.execute(
            "INSERT INTO notifications (business_id, type, title, message, booking_id) "
            "VALUES (?, 'booking', ?, ?, ?)",
            (
                business["id"],
                "Booking rescheduled",
                f"{booking['customer_name']} moved {booking['service_name']} to {new_date} at {time}",
                booking_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    booking["date"] = new_date
    booking["time"] = time
    return templates.TemplateResponse(
        request,
        "booking_manage.html",
        {
            "booking": booking,
            "business": business,
            "error": None,
            "slots": [],
            "today": date.today().isoformat(),
            "notice": f"Your booking has been rescheduled to {new_date} at {time}.",
        },
    )


@router.post("/booking/manage/{booking_id}/cancel")
def booking_manage_cancel(
    request: Request,
    booking_id: int,
    email: str = Form(...),
    reference: str = Form(...),
):
    booking, business = _lookup_booking(reference, email)
    if not booking or booking["id"] != booking_id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["status"] == "cancelled":
        return templates.TemplateResponse(
            request,
            "booking_manage.html",
            {"booking": booking, "business": business, "error": None, "slots": [], "today": date.today().isoformat(), "notice": "This booking was already cancelled."},
        )
    conn = get_connection()
    try:
        conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        conn.execute(
            "INSERT INTO notifications (business_id, type, title, message, booking_id) "
            "VALUES (?, 'booking', ?, ?, ?)",
            (
                business["id"],
                "Booking cancelled",
                f"{booking['customer_name']} cancelled {booking['service_name']} on {booking['date']} at {booking['time']}",
                booking_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    booking["status"] = "cancelled"
    return templates.TemplateResponse(
        request,
        "booking_manage.html",
        {
            "booking": booking,
            "business": business,
            "error": None,
            "slots": [],
            "today": date.today().isoformat(),
            "notice": "Your booking has been cancelled.",
        },
    )


@router.get("/t/{slug}/store", response_class=HTMLResponse)
def tenant_store(request: Request, slug: str):
    """Public storefront for a business (only when the owner enables it)."""
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if not business["storefront_enabled"] or business["subscription_status"] == "cancelled":
        raise HTTPException(status_code=404, detail="Storefront not enabled")
    conn = get_connection()
    try:
        products = rows_to_dicts(
            conn.execute(
                "SELECT * FROM products WHERE business_id = ? AND active = 1 ORDER BY sort_order, id",
                (business["id"],),
            ).fetchall()
        )
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "tenant/store.html",
        {
            "business": business,
            "products": products,
            "tenant_base": _tenant_base(request, slug),
            "format_price": _format_price,
        },
    )


@router.get("/t/{slug}/store/order/{order_id}/success", response_class=HTMLResponse)
def tenant_store_order_success(request: Request, slug: str, order_id: int):
    """Landing page after a successful storefront payment."""
    business = _get_business_by_slug(slug)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    conn = get_connection()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND business_id = ?",
            (order_id, business["id"]),
        ).fetchone()
    finally:
        conn.close()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return templates.TemplateResponse(
        request,
        "tenant/store_success.html",
        {
            "business": business,
            "order": row_to_dict(order),
            "tenant_base": _tenant_base(request, slug),
            "format_price": _format_price,
        },
    )
