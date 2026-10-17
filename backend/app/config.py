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
    # SMTP (email notifications — leave empty to log instead)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "WaveBook <no-reply@getwavebook.com>")

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    SUBSCRIPTION_PRICE_GBP: float = 9.99
    MAX_STAFF: int = 5
    TRIAL_DAYS: int = 14
    SMS_FREE_LIMIT: int = 50  # free SMS per business
    SMS_TOPUP_PRICE_GBP: float = 5.00
    SMS_TOPUP_CREDITS: int = 50  # SMS added per £5 top-up


settings = Settings()
