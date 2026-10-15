# WaveBook

WaveBook is a modern, UK-focused booking and scheduling platform for solo business owners and small teams. One subscription (£9.99/month), all features included.

## Repo layout

- `backend/` — FastAPI (Python) backend on SQLite. Serves:
  - `/api/*` — REST API for the Flutter app (auth, business, services, availability, bookings, customers, staff, notifications, subscription)
  - `/` — landing page (getwavebook.com)
  - `/subscribe` — subscription page (Stripe checkout)
  - `/admin` — platform owner dashboard
  - `/t/{slug}` — tenant booking sites (also served at `<slug>.wab.is`)
- `app/` — Flutter app for iOS + Android (business owner app)

## Domains

- Main site + API: `getwavebook.com` (API at `getwavebook.com/api/*`)
- Tenant booking sites: `<business>.wab.is`
- Subscription activation happens on the website only (App Store compliant)

## Backend quickstart

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # then fill in values
python run.py                   # http://localhost:8000
```

A working `.env` is already present in `backend/.env` with the SMS Works JWT configured (SMS sending is live). Add Stripe keys when ready.

## SMS provider

Text notifications are sent via **The SMS Works** (`POST https://api.thesmsworks.co.uk/v1/message/send`).

- `SMSWORKS_API_KEY` — the full JWT from the SMS Works dashboard (including the `JWT ` prefix)
- `SMSWORKS_SENDER_ID` — sender name, max 11 chars (default `WaveBook`)
- If the key is empty, SMS falls back to console logging (dev mode)

Support: support@getwavebook.com

## Flutter app quickstart

```bash
cd app
flutter pub get
flutter run
```

The app connects to `https://getwavebook.com` by default. For local development, override with:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000   # Android emulator
flutter run --dart-define=API_BASE_URL=http://localhost:8000  # iOS simulator
```

## Features

- Sign up + business setup (each business gets `<slug>.wab.is`)
- Services, availability (slot engine with buffers), bookings with deposit flow
- Gallery, staff (up to 5), customer profiles, settings
- Real-time booking notifications (popup in app)
- Stripe subscription (£9.99/month) via website checkout
- Dark/white/pink beauty theme across app, website and admin
