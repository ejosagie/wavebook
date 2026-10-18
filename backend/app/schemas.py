from pydantic import BaseModel, EmailStr, Field


# ---- Auth ----
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    phone: str = Field(min_length=10)
    business_name: str | None = None
    slug: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ---- Business ----
class BusinessCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=2, pattern=r"^[a-z0-9-]+$")


class BusinessUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    tagline: str | None = None
    about_text: str | None = None
    rules: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    address: str | None = None
    instagram: str | None = None
    facebook: str | None = None
    tiktok: str | None = None
    opening_hours: str | None = None
    deposit_amount: float | None = None
    buffer_minutes: int | None = None
    sms_instructions: str | None = None
    storefront_enabled: bool | None = None
    payout_bank_name: str | None = None
    payout_account_name: str | None = None
    payout_account_number: str | None = None
    payout_sort_code: str | None = None
    theme_color: str | None = None


# ---- Subscription ----
class SubscriptionCheckoutRequest(BaseModel):
    email: EmailStr | None = None  # required for website visitors (no session)
    plan: str = "basic_monthly"


# ---- Storefront products ----
class ProductCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    price: float = Field(ge=0)
    sort_order: int = 0


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = Field(default=None, ge=0)
    image_path: str | None = None
    active: bool | None = None
    sort_order: int | None = None


class StorefrontItem(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class StorefrontCheckout(BaseModel):
    slug: str = Field(min_length=2)
    customer_name: str = Field(min_length=1)
    customer_email: str = ""
    customer_phone: str = ""
    items: list[StorefrontItem]


class OrderUpdate(BaseModel):
    status: str


# ---- Services ----
class ServiceCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    price: float = Field(ge=0)
    duration_minutes: int = Field(ge=5, le=1440)


class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    sort_order: int | None = None


# ---- Availability ----
class DayConfig(BaseModel):
    enabled: bool = True
    start: str = "09:00"
    end: str = "17:00"


class AvailabilityUpdate(BaseModel):
    working_days: dict[str, DayConfig] | None = None
    blocked_dates: list[str] | None = None
    blocked_slots: dict[str, list[str]] | None = None
    slot_interval: int | None = Field(default=None, ge=5, le=240)


# ---- Bookings ----
class BookingCreate(BaseModel):
    customer_name: str = Field(min_length=1)
    customer_email: str = ""
    customer_phone: str = Field(min_length=10)
    service_id: int
    date: str
    time: str
    notes: str = ""


class BookingStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(pending|confirmed|cancelled)$")


# ---- Payments ----
class PaymentIntentCreate(BaseModel):
    booking_id: int


# ---- Text notifications ----
class SendTextRequest(BaseModel):
    phone: str = Field(min_length=5)
    message: str = Field(min_length=1, max_length=1600)


# ---- Staff ----
class StaffInvite(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1)
    phone: str = ""


class StaffUpdate(BaseModel):
    active: bool | None = None


class AssignBookingRequest(BaseModel):
    staff_id: int | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


# ---- Feedback ----
class FeedbackCreate(BaseModel):
    slug: str = Field(min_length=2)
    booking_id: int | None = None
    name: str = Field(min_length=1)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)
