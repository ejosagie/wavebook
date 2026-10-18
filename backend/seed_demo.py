"""Seed a demo account (test@gmail.com / test) with realistic salon data.

Run on the VPS from /opt/wavebook/backend:
    .venv/bin/python seed_demo.py
Idempotent: deletes any existing demo user/business data first.
"""
import json
from datetime import date, timedelta

from app.database import get_connection
from app.security import hash_password

EMAIL = "test@gmail.com"
SLUG = "demo"

conn = get_connection()


def cols(t):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}


def ins(t, **kw):
    kw = {k: v for k, v in kw.items() if k in cols(t)}
    keys = ",".join(kw)
    ph = ",".join("?" * len(kw))
    cur = conn.execute(f"INSERT INTO {t} ({keys}) VALUES ({ph})", tuple(kw.values()))
    return cur.lastrowid


try:
    # --- wipe existing demo data ---
    row = conn.execute("SELECT id, business_id FROM users WHERE email = ?", (EMAIL,)).fetchone()
    old_bid = None
    if row:
        old_bid = row["business_id"]
    biz = conn.execute("SELECT id FROM businesses WHERE slug = ?", (SLUG,)).fetchone()
    if biz:
        old_bid = biz["id"]
    if old_bid:
        for t in ("bookings", "services", "availability", "customers", "staff", "payments",
                  "subscriptions", "products", "orders", "notifications", "feedback",
                  "gallery", "settlements"):
            conn.execute(f"DELETE FROM {t} WHERE business_id = ?", (old_bid,))
        conn.execute("DELETE FROM users WHERE business_id = ?", (old_bid,))
        conn.execute("DELETE FROM businesses WHERE id = ?", (old_bid,))
    conn.execute("DELETE FROM users WHERE email = ?", (EMAIL,))

    # --- business ---
    bid = ins(
        "businesses",
        slug=SLUG,
        name="Blush & Bloom Studio",
        tagline="Hair, beauty & nails in the heart of London",
        about_text="A boutique salon offering cuts, colour, nails and facials. "
                   "Small team, big attention to detail — every visit is tailored to you.",
        contact_phone="+44 20 7946 0958",
        contact_email=EMAIL,
        address="14 Rosewater Lane, London E8 3PN",
        instagram="blushandbloomldn",
        opening_hours="Mon–Sat 9:00–18:00",
        deposit_amount=20.00,
        buffer_minutes=30,
        currency="GBP",
        subscription_status="active",
        storefront_enabled=1,
        trial_ends_at=(date.today() + timedelta(days=365)).isoformat(),
        theme_color="#ec4899",
    )

    # --- owner user ---
    uid = ins(
        "users",
        email=EMAIL,
        password_hash=hash_password(PASSWORD := "test"),
        full_name="Demo Owner",
        phone="+447700900123",
        role="owner",
        business_id=bid,
    )

    # --- a staff member for the demo ---
    staff_uid = ins(
        "users",
        email="ava@blushandbloom.co.uk",
        password_hash=hash_password("test"),
        full_name="Ava Smith",
        phone="+447700900124",
        role="staff",
        business_id=bid,
    )
    ins("staff", business_id=bid, user_id=staff_uid, active=1)

    # --- availability: Mon–Sat 09:00–18:00 ---
    working = {d: {"enabled": True, "start": "09:00", "end": "18:00"}
               for d in ("mon", "tue", "wed", "thu", "fri", "sat")}
    working["sun"] = {"enabled": False, "start": "09:00", "end": "18:00"}
    ins("availability", business_id=bid, working_days=json.dumps(working),
        blocked_dates="[]", blocked_slots="{}", slot_interval=30)

    # --- services ---
    services = [
        ("Women's Haircut & Style", "Wash, cut and finish.", 45.00, 60),
        ("Men's Haircut", "Cut and style with a hot-towel finish.", 28.00, 45),
        ("Full Colour", "Root-to-tip colour with gloss.", 75.00, 120),
        ("Balayage", "Hand-painted balayage with toner.", 110.00, 150),
        ("Gel Manicure", "Shape, cuticle care and gel polish.", 32.00, 45),
        ("Luxury Facial", "60-minute deep-cleanse facial.", 55.00, 60),
        ("Blowout", "Wash and bouncy blow-dry.", 30.00, 30),
    ]
    svc_ids = []
    for i, (name, desc, price, dur) in enumerate(services):
        svc_ids.append(ins("services", business_id=bid, name=name, description=desc,
                           price=price, duration_minutes=dur, sort_order=i))

    # --- products (storefront) ---
    products = [
        ("Argan Hair Oil 50ml", "Nourishing oil for shine and softness.", 14.00),
        ("Repair Shampoo 250ml", "Sulphate-free strengthening shampoo.", 12.00),
        ("Hydrating Face Serum", "Hyaluronic serum used in our facials.", 18.00),
        ("Silk Scrunchie Set", "Set of 3 gentle silk scrunchies.", 9.00),
        ("£25 Gift Voucher", "Redeemable on any service in store.", 25.00),
    ]
    for i, (name, desc, price) in enumerate(products):
        ins("products", business_id=bid, name=name, description=desc,
            price=price, active=1, sort_order=i)

    # --- customers ---
    customers = [
        ("Sophie Turner", "sophie.t@example.com", "+447911100001"),
        ("Emma Wilson", "emma.w@example.com", "+447911100002"),
        ("James Carter", "james.c@example.com", "+447911100003"),
        ("Priya Patel", "priya.p@example.com", "+447911100004"),
        ("Olivia Brown", "olivia.b@example.com", "+447911100005"),
        ("Daniel Lee", "daniel.l@example.com", "+447911100006"),
    ]
    for name, email, phone in customers:
        ins("customers", business_id=bid, name=name, email=email, phone=phone)

    # --- bookings: past, today, upcoming ---
    today = date.today()
    bookings = [
        # (days offset, time, service idx, customer idx, status, payment_status)
        (-4, "10:00", 0, 0, "confirmed", "paid"),
        (-2, "14:00", 5, 1, "confirmed", "paid"),
        (0, "09:30", 1, 2, "confirmed", "paid"),
        (0, "11:00", 4, 3, "confirmed", "paid"),
        (0, "15:30", 6, 4, "pending", "none"),
        (1, "10:00", 3, 0, "confirmed", "paid"),
        (1, "13:00", 2, 5, "confirmed", "paid"),
        (2, "09:00", 0, 1, "pending", "none"),
        (2, "16:00", 5, 4, "confirmed", "paid"),
        (4, "11:30", 3, 2, "confirmed", "none"),
        (6, "10:30", 6, 3, "pending", "none"),
    ]
    notes = {
        0: "Regular client — prefers stylist Ava",
        4: "First visit, asked about balayage",
        7: "Requested quiet appointment",
    }
    booking_ids = []
    for i, (off, t, si, ci, st, pay) in enumerate(bookings):
        s = services[si]
        c = customers[ci]
        bid_row = ins(
            "bookings",
            business_id=bid,
            customer_name=c[0],
            customer_email=c[1],
            customer_phone=c[2],
            service_id=svc_ids[si],
            service_name=s[0],
            service_price=s[2],
            service_duration_minutes=s[3],
            date=(today + timedelta(days=off)).isoformat(),
            time=t,
            notes=notes.get(i, ""),
            status=st,
            payment_status=pay,
        )
        booking_ids.append((bid_row, s[2], st, pay, off))

    # --- payments for the paid bookings ---
    for bid_row, price, st, pay, off in booking_ids:
        if pay == "paid":
            ins("payments", business_id=bid, booking_id=bid_row,
                amount=20.00, currency="GBP", status="paid", method="card")

    # --- a few store orders ---
    ins("orders", business_id=bid, customer_name="Sophie Turner",
        customer_email="sophie.t@example.com", customer_phone="+447911100001",
        items=json.dumps([{"product_id": 1, "name": "Argan Hair Oil 50ml",
                           "price": 14.00, "qty": 2}]),
        total=28.00, status="shipped", payment_ref="DEMO-ORD-1")
    ins("orders", business_id=bid, customer_name="Emma Wilson",
        customer_email="emma.w@example.com", customer_phone="+447911100002",
        items=json.dumps([{"product_id": 3, "name": "Hydrating Face Serum",
                           "price": 18.00, "qty": 1}]),
        total=18.00, status="paid", payment_ref="DEMO-ORD-2")
    ins("orders", business_id=bid, customer_name="Daniel Lee",
        customer_email="daniel.l@example.com", customer_phone="+447911100006",
        items=json.dumps([{"product_id": 5, "name": "£25 Gift Voucher",
                           "price": 25.00, "qty": 1}]),
        total=25.00, status="pending", payment_ref="DEMO-ORD-3")

    # --- reviews for the tenant page ---
    for rating, comment, name in [
        (5, "Best balayage I've had — Ava is brilliant!", "Sophie T."),
        (5, "Lovely studio, easy online booking.", "Emma W."),
        (4, "Great haircut and friendly team.", "James C."),
    ]:
        ins("feedback", business_id=bid, rating=rating, comment=comment,
            customer_name=name, approved=1)

    # --- notifications ---
    for title, msg in [
        ("New booking", "Blowout — today at 15:30"),
        ("New order", "£25 Gift Voucher (£25.00)"),
        ("New booking", "Balayage — tomorrow at 10:00"),
    ]:
        ins("notifications", business_id=bid, type="booking", title=title,
            body=msg, message=msg, read=0)

    # --- active premium subscription so every feature is unlocked ---
    ins("subscriptions", business_id=bid, stripe_subscription_id="DEMO-SUB",
        status="active", plan="premium_monthly", amount=14.99)

    conn.commit()
    print(f"DEMO SEEDED: business_id={bid} slug={SLUG} user_id={uid}")
finally:
    conn.close()
