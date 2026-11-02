# LUZ EMS Scheduling

A lightweight scheduling website for LUZ EMS with automatic WhatsApp booking confirmations, 12-hour reminders, session revenue tracking, and subscription packages.

## Features

- **Client management** — store names, phone numbers, emails, and notes.
- **Service catalog** — treatments, durations, prices, and colors.
- **Booking calendar** — week view, create sessions, see upcoming appointments.
- **WhatsApp notifications** — instant booking confirmation + automated 12-hour reminder.
  - **Demo mode** — log messages locally (no cost).
  - **WhatsApp Web** — free, uses the business's own phone number (scan QR code).
  - **Twilio** — paid official WhatsApp Business API.
- **Subscriptions / packages** — sell session packs (e.g., 10 sessions) and track usage.
- **Weekly revenue dashboard** — appointment income + subscription sales, broken down by service.
- **Message log** — see every confirmation and reminder that was sent.

## Run locally

```bash
cd /home/ubuntu/luz_ems_scheduling
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8015 --workers 1
```

Or use the helper script:

```bash
./start.sh
```

Then open `http://<server-ip>:8015/` in a browser.

## Free WhatsApp from the business phone (WhatsApp Web)

This uses the unofficial `whatsapp-web.js` library. It is free, but it is not officially supported by WhatsApp and may be restricted for bulk/commercial messaging.

1. In **Settings**, choose **WhatsApp Web (free, own number)** as the provider.
2. Turn off **Demo mode** and turn on **WhatsApp enabled**.
3. A QR code appears. Scan it with the business phone's WhatsApp app (Menu → Linked Devices → Link a Device).
4. Once connected, all booking confirmations and reminders are sent from that number for free.

## Twilio WhatsApp setup (official, paid)

1. Create a [Twilio](https://www.twilio.com) account and enable the WhatsApp sandbox.
2. In **Settings**, choose **Twilio** as the provider.
3. Turn off **Demo mode**, turn on **WhatsApp enabled**.
4. Enter Twilio Account SID, Auth Token, and WhatsApp sender number.
5. Save — new bookings and reminders will send real messages.

## Project structure

```
luz_ems_scheduling/
├── backend/
│   ├── main.py                  # FastAPI app + scheduler + WhatsApp bridge launcher
│   ├── database.py              # SQLite setup
│   ├── models.py                # SQLAlchemy models
│   ├── schemas.py               # Pydantic schemas
│   ├── notifications.py         # WhatsApp routing (demo / whatsapp_web / twilio)
│   ├── whatsapp_web_client.py   # Python client for the Node bridge
│   ├── seed.py                  # Default data
│   ├── routers/
│   │   ├── clients.py
│   │   ├── services.py
│   │   ├── appointments.py
│   │   ├── settings.py
│   │   ├── dashboard.py
│   │   ├── notifications.py
│   │   └── subscriptions.py
│   └── whatsapp/
│       ├── server.js            # Node.js whatsapp-web.js bridge
│       └── package.json
├── frontend/
│   └── index.html               # Single-page app UI
├── data/
│   ├── app.db                   # SQLite database
│   ├── demo_messages.log        # Logged messages in demo mode
│   ├── whatsapp_session/        # WhatsApp Web session data
│   └── whatsapp_qr.txt          # Latest QR code
├── start.sh
└── requirements.txt
```
