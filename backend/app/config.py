import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "wavebook.db"))
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    # Public domains
    PUBLIC_BASE_DOMAIN: str = os.getenv("PUBLIC_BASE_DOMAIN", "wab.is")  # tenant booking sites: <slug>.wab.is
    API_PUBLIC_URL: str = os.getenv("API_PUBLIC_URL", "https://getwavebook.com")  # main site + API
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_ID_MONTHLY: str = os.getenv("STRIPE_PRICE_ID_MONTHLY", "")
    STRIPE_CURRENCY: str = os.getenv("STRIPE_CURRENCY", "gbp")
    # The SMS Works (https://www.thesmsworks.co.uk) — JWT auth, placeholder until keys are added
    SMSWORKS_API_KEY: str = os.getenv("SMSWORKS_API_KEY", "")  # JSON Web Token from the SMS Works dashboard
    SMSWORKS_SENDER_ID: str = os.getenv("SMSWORKS_SENDER_ID", "WaveBook")  # max 11 chars
    GOCARDLESS_ACCESS_TOKEN: str = os.getenv("GOCARDLESS_ACCESS_TOKEN", "")
    GOCARDLESS_WEBHOOK_SECRET: str = os.getenv("GOCARDLESS_WEBHOOK_SECRET", "")
    # Platform admin access (set in .env / server environment)
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_ACCESS_TOKEN: str = os.getenv("ADMIN_ACCESS_TOKEN", "")  # ?access=... link on the landing page
    # Flutterwave (card payments for bookings and subscriptions)
    FLW_PUBLIC_KEY: str = os.getenv("FLW_PUBLIC_KEY", "")
    FLW_SECRET_KEY: str = os.getenv("FLW_SECRET_KEY", "")
    FLW_ENCRYPTION_KEY: str = os.getenv("FLW_ENCRYPTION_KEY", "")
    FLW_CURRENCY: str = os.getenv("FLW_CURRENCY", "GBP")
    FLW_COUNTRY: str = os.getenv("FLW_COUNTRY", "GB")
    # Email relay: the VPS POSTs emails to this PHP endpoint on the NeuroWaves hosting,
    # which sends them with mail(). Leave NOTIFY_TOKEN empty to log emails instead.
    NOTIFY_URL: str = os.getenv("NOTIFY_URL", "https://neurowavesdatasystems.ng/notification/notification.php")
    NOTIFY_TOKEN: str = os.getenv("NOTIFY_TOKEN", "")
    # Google Cloud Storage (product/shop images + backups). Leave empty to store
    # images on the local disk (backend/uploads) instead of GCS.
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "")  # public bucket for product images
    GCS_PREFIX: str = os.getenv("GCS_PREFIX", "")  # folder inside GCS_BUCKET_NAME, e.g. wavebook
    GCS_BACKUP_BUCKET: str = os.getenv("GCS_BACKUP_BUCKET", "")  # private bucket for DB + uploads backups

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    SUBSCRIPTION_PRICE_GBP: float = 19.99
    # Subscription plans: tier x billing interval.
    # basic = booking + store (5 products), shop = unlimited products,
    # premium = unlimited products + 80 free SMS.
    # Keys must not contain '-' (hyphens are used in tx_ref parsing).
    SUBSCRIPTION_PLANS: dict = {
        "basic_monthly":     {"tier": "basic",   "interval": "monthly",   "price": 9.99},
        "basic_quarterly":   {"tier": "basic",   "interval": "quarterly", "price": 27.99},
        "basic_biannual":    {"tier": "basic",   "interval": "biannual",  "price": 54.99},
        "basic_yearly":      {"tier": "basic",   "interval": "yearly",    "price": 99.99},
        "shop_monthly":      {"tier": "shop",    "interval": "monthly",   "price": 12.99},
        "shop_quarterly":    {"tier": "shop",    "interval": "quarterly", "price": 36.99},
        "shop_biannual":     {"tier": "shop",    "interval": "biannual",  "price": 69.99},
        "shop_yearly":       {"tier": "shop",    "interval": "yearly",    "price": 129.99},
        "premium_monthly":   {"tier": "premium", "interval": "monthly",   "price": 19.99},
        "premium_quarterly": {"tier": "premium", "interval": "quarterly", "price": 56.99},
        "premium_biannual":  {"tier": "premium", "interval": "biannual",  "price": 109.99},
        "premium_yearly":    {"tier": "premium", "interval": "yearly",    "price": 199.99},
    }
    INTERVAL_LABELS: dict = {
        "monthly": "Monthly", "quarterly": "Quarterly (3 months)",
        "biannual": "6 Months", "yearly": "Yearly",
    }
    TIER_LABELS: dict = {
        "basic": "WaveBook Basic", "shop": "WaveBook + Shop",
        "premium": "WaveBook Premium",
    }
    MAX_STAFF: int = 5
    # Per-tier feature limits. max_products None = unlimited.
    TIER_FEATURES: dict = {
        "trial":   {"storefront": True, "max_products": None, "free_sms": 50, "max_staff": MAX_STAFF},
        "basic":   {"storefront": True, "max_products": 5,    "free_sms": 50, "max_staff": 0},
        "shop":    {"storefront": True, "max_products": None, "free_sms": 50, "max_staff": 0},
        "premium": {"storefront": True, "max_products": None, "free_sms": 80, "max_staff": MAX_STAFF},
        "expired": {"storefront": False, "max_products": 0, "free_sms": 0, "max_staff": 0},
    }
    # Plan keys from before the 3-tier rename -> current keys.
    LEGACY_PLAN_KEYS: dict = {
        "standard_monthly": "basic_monthly",
        "standard_quarterly": "basic_quarterly",
        "standard_biannual": "basic_biannual",
        "standard_yearly": "basic_yearly",
    }
    TRIAL_DAYS: int = 7  # default; admins can change it from the admin dashboard
    SMS_FREE_LIMIT: int = 50  # default free SMS per business (plan tiers may override)
    SMS_TOPUP_PRICE_GBP: float = 5.00
    SMS_TOPUP_CREDITS: int = 50  # SMS added per £5 top-up
    # Storefront order statuses: pending -> paid -> confirmed -> shipped (or cancelled)
    ORDER_STATUSES: tuple = ("pending", "paid", "confirmed", "shipped", "cancelled")


settings = Settings()
