# LUZ EMS Scheduling

A complete scheduling and client-care app for the LUZ EMS studio: calendar and bookings, a public self-booking page, automatic WhatsApp / SMS / email notifications, session packages, payments and revenue reporting.

## What it does

**Scheduling**
- Week, day and agenda calendar in the studio's time zone (Asia/Dubai). Click an empty slot to book, click a session to manage it.
- Opening hours per weekday, blocked time (holidays, breaks), trainer resources, and a "machines / rooms" limit. Double bookings and out-of-hours bookings are rejected (with an admin override).
- Session lifecycle: scheduled → confirmed → completed / no-show / cancelled, plus reschedule. Each step can notify the client.
- Public booking page at `/book`: clients pick a service, trainer, date and a free slot. Each booking gets a private link (`/a/<token>`) where the client can confirm or cancel.

**Notifications to clients** (templates are editable in *Messages → Templates*)
- Booking confirmation, reminder N hours before, reschedule, cancellation, after-session follow-up, package purchased, package running low, package expiring.
- Admin alert on new online bookings.
- Channels: WhatsApp (WhatsApp Web bridge or Twilio), SMS (Twilio) and email (SMTP). Each client chooses which channels they want.
- Demo mode logs everything in the Messages page without sending. Failed messages can be retried.

**Money**
- Session packages (e.g. 10 sessions, 90 days): booking a session uses one, cancelling gives it back.
- Payments per session or package (cash / card / transfer / online); outstanding balances are tracked.
- Revenue page: collected revenue over time, by service, trainer and payment method, session outcomes, top clients, CSV export.

**Clients**
- Profile with history, packages, payments and every message sent. Total spent, outstanding balance, sessions left.

**Admin**
- Password-protected (set the first password with `LUZ_ADMIN_PASSWORD`, change it in Settings → Security).

## Run locally

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env        # optional, adjust ports and password
./start.sh                  # live:    http://localhost:8015
./start-staging.sh --demo-data   # staging: http://localhost:8016 with sample data
```

Staging uses its own database folder (`data-staging/`), its own ports (8016 app, 8021 WhatsApp bridge) and starts in demo mode, so it can run next to the live server on the same machine. Default sign-in password is in `.env.example`; change it after first login.

## Tests

```bash
venv/bin/python -m pytest tests -q
```

## Going live with notifications

1. **Settings → Messaging channels**: turn off *Demo mode*.
2. **WhatsApp**: either *WhatsApp Web* (free; needs Node and `npm install` inside `backend/whatsapp`, then scan the QR code with the business phone) or *Twilio* (enter SID, token and WhatsApp sender).
3. **SMS**: Twilio SMS number; only clients with SMS enabled receive texts.
4. **Email**: SMTP host, port, username, password and from-address.
5. Set **Public URL** so booking and manage links in messages point at the real domain.

## Upgrading the live database

The app adds any missing columns and default rows on start (`backend/migrate.py`); nothing is dropped. Back up `data/app.db` first, deploy, restart.

## Project structure

```
backend/
  main.py            FastAPI app, auth wiring, scheduler, static files
  models.py          SQLAlchemy models (clients, staff, services, appointments, payments, ...)
  schemas.py         Pydantic request / response models
  scheduling.py      Opening hours, conflict detection, slot availability
  notifications.py   Templates, channel delivery (WhatsApp / SMS / email), background jobs
  auth.py            Password hashing and login tokens
  migrate.py         Additive schema migration
  seed.py            Default settings, hours, services, plans, templates
  routers/           API endpoints (clients, staff, services, appointments, subscriptions,
                     payments, reports, notifications, settings, dashboard, public, auth)
  whatsapp/          Node.js WhatsApp Web bridge
frontend/
  index.html         Admin app shell
  css/app.css        Styles
  js/*.js            Admin app (core, calendar, booking, clients, money, messages, settings, dashboard)
  book.html          Public booking page
  manage.html        Client manage-booking page
scripts/seed_demo.py Sample data for staging
tests/test_api.py    End-to-end API tests
```
