import json
import secrets
import sqlite3
from pathlib import Path

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    role TEXT NOT NULL DEFAULT 'owner',   -- owner | staff | admin
    business_id INTEGER,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS businesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    tagline TEXT DEFAULT '',
    about_text TEXT DEFAULT '',
    about_image TEXT DEFAULT '',
    logo_path TEXT DEFAULT '',
    rules TEXT DEFAULT '',
    contact_phone TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    address TEXT DEFAULT '',
    instagram TEXT DEFAULT '',
    facebook TEXT DEFAULT '',
    tiktok TEXT DEFAULT '',
    opening_hours TEXT DEFAULT '',
    deposit_amount REAL NOT NULL DEFAULT 20.00,
    buffer_minutes INTEGER NOT NULL DEFAULT 30,
    currency TEXT NOT NULL DEFAULT 'GBP',
    subscription_status TEXT NOT NULL DEFAULT 'trial',  -- trial | active | past_due | cancelled
    stripe_customer_id TEXT DEFAULT '',
    stripe_subscription_id TEXT DEFAULT '',
    shipping_fee_local REAL NOT NULL DEFAULT 0,
    shipping_fee_international REAL NOT NULL DEFAULT 0,
    store_country TEXT NOT NULL DEFAULT 'GB',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    price REAL NOT NULL DEFAULT 0,
    duration_minutes INTEGER NOT NULL DEFAULT 60,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER UNIQUE NOT NULL,
    working_days TEXT NOT NULL DEFAULT '{}',
    blocked_dates TEXT NOT NULL DEFAULT '[]',
    blocked_slots TEXT NOT NULL DEFAULT '{}',
    slot_interval INTEGER NOT NULL DEFAULT 30,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT DEFAULT '',
    customer_phone TEXT DEFAULT '',
    service_id INTEGER,
    service_name TEXT NOT NULL,
    service_price REAL NOT NULL DEFAULT 0,
    service_duration_minutes INTEGER NOT NULL DEFAULT 60,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    notes TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed | cancelled
    confirmation_file TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    booking_id INTEGER,
    stripe_payment_intent_id TEXT DEFAULT '',
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'GBP',
    kind TEXT DEFAULT 'deposit',
    status TEXT DEFAULT 'pending',
    method TEXT DEFAULT 'card',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    booking_id INTEGER NOT NULL,
    number TEXT NOT NULL,
    total REAL NOT NULL DEFAULT 0,
    deposit_paid REAL NOT NULL DEFAULT 0,
    balance_due REAL NOT NULL DEFAULT 0,
    currency TEXT DEFAULT 'GBP',
    status TEXT NOT NULL DEFAULT 'partial',  -- partial | paid
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    stripe_subscription_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'trial',
    plan TEXT NOT NULL DEFAULT 'monthly',
    amount REAL NOT NULL DEFAULT 9.99,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gallery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    path TEXT DEFAULT '',
    caption TEXT DEFAULT '',
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    type TEXT NOT NULL DEFAULT 'booking',
    title TEXT NOT NULL,
    message TEXT DEFAULT '',
    booking_id INTEGER,
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    booking_id INTEGER,
    customer_name TEXT DEFAULT '',
    rating INTEGER NOT NULL DEFAULT 5,
    comment TEXT DEFAULT '',
    approved INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    method TEXT NOT NULL DEFAULT 'bank_transfer',
    reference TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    price REAL NOT NULL DEFAULT 0,
    image_path TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS product_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    business_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    customer_address TEXT DEFAULT '',
    customer_city TEXT DEFAULT '',
    customer_postcode TEXT DEFAULT '',
    customer_country TEXT DEFAULT '',
    shipping_fee REAL NOT NULL DEFAULT 0,
    customer_name TEXT DEFAULT '',
    customer_email TEXT DEFAULT '',
    customer_phone TEXT DEFAULT '',
    items TEXT NOT NULL DEFAULT '[]',
    total REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | paid | confirmed | shipped | cancelled
    payment_ref TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS page_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page TEXT NOT NULL,
    visited_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_phone TEXT DEFAULT '',
    last_message_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    sender TEXT NOT NULL,  -- customer | owner
    body TEXT NOT NULL,
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedback_business ON feedback(business_id, approved);
CREATE INDEX IF NOT EXISTS idx_notifications_business ON notifications(business_id, read);
CREATE INDEX IF NOT EXISTS idx_bookings_business_date ON bookings(business_id, date);
CREATE INDEX IF NOT EXISTS idx_page_visits_page ON page_visits(page);
CREATE INDEX IF NOT EXISTS idx_payments_booking ON payments(booking_id);
CREATE INDEX IF NOT EXISTS idx_services_business ON services(business_id);
CREATE INDEX IF NOT EXISTS idx_users_business ON users(business_id);
CREATE INDEX IF NOT EXISTS idx_product_images_product ON product_images(product_id);
CREATE INDEX IF NOT EXISTS idx_chats_business_phone ON chats(business_id, customer_phone);
CREATE INDEX IF NOT EXISTS idx_chat_messages_chat ON chat_messages(chat_id);
"""


def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    """Add a column to an existing table if it is missing (lightweight migration)."""
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "bookings", "payment_status", "payment_status TEXT DEFAULT 'none'")
        _ensure_column(conn, "bookings", "payment_intent_id", "payment_intent_id TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "sms_template", "sms_template TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "sms_instructions", "sms_instructions TEXT DEFAULT ''")
        _ensure_column(conn, "users", "last_login_at", "last_login_at TEXT DEFAULT ''")
        _ensure_column(conn, "users", "must_change_password", "must_change_password INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "payments", "stripe_payment_intent_id", "stripe_payment_intent_id TEXT DEFAULT ''")
        _ensure_column(conn, "payments", "currency", "currency TEXT DEFAULT 'GBP'")
        _ensure_column(conn, "payments", "kind", "kind TEXT DEFAULT 'deposit'")
        conn.execute("UPDATE payments SET kind = 'deposit' WHERE booking_id IS NOT NULL")
        conn.execute("UPDATE payments SET kind = 'order' WHERE booking_id IS NULL")
        _ensure_column(conn, "payments", "method", "method TEXT DEFAULT 'card'")
        _ensure_column(conn, "businesses", "storefront_enabled", "storefront_enabled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "businesses", "currency", "currency TEXT NOT NULL DEFAULT 'GBP'")
        _ensure_column(conn, "businesses", "payout_bank_name", "payout_bank_name TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "payout_account_name", "payout_account_name TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "payout_account_number", "payout_account_number TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "payout_sort_code", "payout_sort_code TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "payout_country", "payout_country TEXT NOT NULL DEFAULT 'GB'")
        _ensure_column(conn, "businesses", "payout_routing_number", "payout_routing_number TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "payout_iban", "payout_iban TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "payout_swift", "payout_swift TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "payout_bank_address", "payout_bank_address TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "sms_used", "sms_used INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "businesses", "sms_credits", "sms_credits INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "businesses", "shipping_fee_local", "shipping_fee_local REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "businesses", "shipping_fee_international", "shipping_fee_international REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "businesses", "store_country", "store_country TEXT NOT NULL DEFAULT 'GB'")
        _ensure_column(conn, "orders", "customer_address", "customer_address TEXT DEFAULT ''")
        _ensure_column(conn, "orders", "customer_city", "customer_city TEXT DEFAULT ''")
        _ensure_column(conn, "orders", "customer_postcode", "customer_postcode TEXT DEFAULT ''")
        _ensure_column(conn, "orders", "customer_country", "customer_country TEXT DEFAULT ''")
        _ensure_column(conn, "orders", "shipping_fee", "shipping_fee REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "businesses", "trial_ends_at", "trial_ends_at TEXT DEFAULT ''")
        _ensure_column(conn, "businesses", "theme_color", "theme_color TEXT DEFAULT '#ec4899'")
        _ensure_column(conn, "businesses", "dark_theme", "dark_theme INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "bookings", "reference", "reference TEXT DEFAULT ''")
        _ensure_column(conn, "bookings", "reminder_sent", "reminder_sent INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "bookings", "assigned_staff_id", "assigned_staff_id INTEGER")
        _ensure_column(conn, "services", "questions", "questions TEXT DEFAULT '[]'")
        _ensure_column(conn, "bookings", "intake_answers", "intake_answers TEXT DEFAULT '{}'")
        _ensure_column(conn, "bookings", "receipt_sent", "receipt_sent INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "products", "stock", "stock INTEGER")
        _ensure_column(conn, "businesses", "calendar_token", "calendar_token TEXT DEFAULT ''")
        # Move single product images (older app builds) into the multi-image table
        conn.execute(
            "INSERT INTO product_images (product_id, business_id, path) "
            "SELECT id, business_id, image_path FROM products "
            "WHERE image_path != '' AND image_path IS NOT NULL "
            "AND id NOT IN (SELECT product_id FROM product_images)"
        )
        # Backfill a reference for bookings created before the column existed
        missing = conn.execute(
            "SELECT id FROM bookings WHERE reference = '' OR reference IS NULL"
        ).fetchall()
        for row in missing:
            ref = "".join(
                secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6)
            )
            conn.execute("UPDATE bookings SET reference = ? WHERE id = ?", (ref, row["id"]))
        conn.commit()
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    db_path = Path(settings.DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def json_dumps(value) -> str:
    return json.dumps(value)


def json_loads(value: str, default=None):
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default
    except (json.JSONDecodeError, TypeError):
        return default


TRIAL_DAYS_KEY = "trial_days"


def get_trial_days() -> int:
    """Free trial length in days. Set by the platform admin; falls back to settings.TRIAL_DAYS."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (TRIAL_DAYS_KEY,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return settings.TRIAL_DAYS
    try:
        days = int(row["value"])
    except (TypeError, ValueError):
        return settings.TRIAL_DAYS
    return days if days > 0 else settings.TRIAL_DAYS
