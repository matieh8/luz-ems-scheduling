# LUZ EMS Admin: Technical Audit

Date: 2026-11-25. Scope: the code on `staging` at `f67fd30` (live `main` at `1c9d326` has the same app code; only the marketing page `home.html` differs).
Mode: **audit only.** No source code, database, configuration or deployment was changed. This report is the only new file.

## How each item was checked

| Label | Meaning |
|---|---|
| **Verified** | Code read (frontend, backend, database), **and** an automated test exercises it, and the 32-test suite passed during this audit |
| **Implemented** | Code read end to end (UI → API → table) but no automated test covers it |
| **Partial** | Works, with a real gap, listed under "Missing" |
| **Missing** | No code for it |
| **Insecure** | Exists but has a defect described in section 9 (shown next to the main status) |

What was run, and what was not:
- `pytest` on a throwaway temp database: **32 passed, 0 failed** (25 s, 718 deprecation warnings).
- Live site, read-only GET requests only: `/api/health` returned 200, `/api/clients/` without login returned 401, `/docs` and `/openapi.json` returned 200 (they are public), and the response headers were read.
- **Not done:** no login to live, no writes to live, no real WhatsApp, SMS or email sent, no payments, no browser run during this audit. Mobile and dark mode were checked in the browser while they were being built; they were **not re-checked for this report**.

---

## 1. Executive summary

LUZ EMS Admin is a working single-studio management app. The core (dashboard, CRM, bookings, packages, finance, staff roles, equipment, leads, audit log, backups) is built end to end, and most of it has API tests that pass.

| Status | Count |
|---|---|
| Verified | 38 |
| Implemented (no automated test) | 18 |
| Partial | 17 |
| Missing | 17 |
| **Total** | **90** |

The large missing areas are the **client portal** (48, 50–52, 54), **AI** (71–76), **service locations and branches** (63–64) and **multi-tenant SaaS** (81–84).

The most urgent problems are **security and data-safety defects in features that already exist**:
1. **Stored XSS** (P0). A name typed on the public booking page can run JavaScript in the owner's browser and steal the login token (section 9, S1).
2. **Anyone who knows a client's phone number can use up that client's package sessions** through the public booking page (S2).
3. **Deleting a client also deletes their payments**, so past revenue silently disappears from the reports (S3).
4. **Backups sit on the same server and leave out progress photos** (S4).
5. **The CI pipeline deploys without running the tests** (S9).

**Recommendation:** before any new feature work, run a short **Phase 0: hardening** sprint, about 2–3 days (section 12). Then start **Phase 5: Client Portal**, which is the largest gap clients actually see.

---

## 2. Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3, FastAPI 0.115, Pydantic 2.9, SQLAlchemy 2.0, APScheduler 3.10 (jobs every minute), Uvicorn (1 worker) |
| Database | SQLite, one file at `<LUZ_DATA_DIR>/app.db`. Additive self-migration in `backend/migrate.py` |
| Frontend | Vanilla JavaScript, no build step (`frontend/js/*.js`, `frontend/css/app.css`), PWA (`sw.js`, `manifest.webmanifest`), Web Push (`backend/push.py`, VAPID) |
| Messaging | WhatsApp Web bridge (Node, `backend/whatsapp/server.js`, whatsapp-web.js), Twilio (WhatsApp and SMS), SMTP email, and a "demo" mode that only writes to a log |
| Hosting | Ubuntu, nginx 1.24 in front, systemd unit `deploy/luz-ems.service`, `start.sh`. Staging and live run side by side with separate data folders |
| CI/CD | GitHub Actions: `deploy.yml` (on push to `main`) and `deploy-staging.yml` (on push to `staging`). Both SSH into the server and run `deploy.sh` (`git reset --hard`, `pip install`, restart, health check) |
| Tests | `tests/test_api.py`: 32 integration tests using FastAPI TestClient against a temp database |

## 3. Architecture

```
Browser (admin SPA /admin, public /book, manage link /a/{token}, landing /)
   │  Bearer token in localStorage
nginx ──► Uvicorn ──► FastAPI app (backend/main.py)
                        ├─ AuditMiddleware (logs every successful write)
                        ├─ open routers: /api/auth, /api/public
                        ├─ protected routers (require_auth + role check): 19 routers
                        ├─ APScheduler tick every minute: reminders, follow-ups, package alerts,
                        │   renewal offers, retries, daily summary, daily backup, audit pruning
                        └─ child process: Node WhatsApp Web bridge (+ watchdog thread)
                     SQLite app.db   |   data/photos/<client>/   |   data/backups/
```

Request flow: `require_auth` (`backend/auth.py`) reads the token, re-checks staff accounts against the database, then calls `allowed(role, method, path)` with regex rules per role. Business logic lives directly in the routers. There is no separate service layer, apart from `scheduling.py` and `notifications.py`.

## 4. Database structure

There are 22 tables (`backend/models.py`).

| Area | Tables |
|---|---|
| Clients | `clients`, `body_measurements`, `client_notes`, `progress_photos` |
| Scheduling | `appointments`, `blocked_times`, `business_hours`, `services`, `staff` |
| Packages and sales | `subscription_plans`, `subscriptions`, `discount_codes`, `gift_cards`, `payments`, `expenses` |
| Messaging | `notification_logs`, `message_templates`, `push_subscriptions` |
| Growth and ops | `leads`, `devices`, `device_maintenance`, `audit_logs`, `settings` (one row) |

Key relationships:
- A client has many appointments, subscriptions, payments, measurements, notes and photos, all with `cascade="all, delete-orphan"`.
- An appointment links to a service, staff member and subscription.
- A subscription links to a plan and can point back to the package it renewed (`renewed_from_id`).
- A gift card links to a plan, the purchaser, the redeemer and its payment.
- A maintenance record links to a device and an optional expense.

Integrity notes (details in section 9):
- SQLite foreign keys are **not enforced**, because `PRAGMA foreign_keys=ON` is never set.
- `unique=True` on columns added later (for example `staff.login_username`) is **not** applied to databases that already existed, because `ALTER TABLE ADD COLUMN` cannot add UNIQUE.
- Migrations have no version table.
- Session balance is a stored counter (`subscriptions.sessions_used`), not something recalculated from appointments.

---

## 5. Requirement-by-requirement audit

Priority: **P0** = fix now (security or data loss) · **P1** = next sprint · **P2** = planned · **P3** = later or optional.

### A. Dashboard. `backend/routers/dashboard.py` (`/api/dashboard/overview`, `/api/dashboard/`), `frontend/js/dashboard.js`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 1 | Total revenue | Verified | `overview()`, `test_dashboard_overview`, `test_finance_report` | — | — | P3 |
| 2 | Net profit | Verified | overview profit = payments − expenses (capped at today) | Cash-based, not accrual | Label it "cash profit" | P3 |
| 3 | Active clients | Verified | overview KPIs | — | — | P3 |
| 4 | Daily and monthly sessions | Verified | overview "today" list and month counts | — | — | P3 |
| 5 | Remaining client sessions | Verified | `Subscription.sessions_remaining`, `dash-packages` | — | — | P3 |
| 6 | Expiring packages | Implemented | dashboard alerts, `daily_summary()` | No test of the alert | Add a test | P2 |
| 7 | Upcoming appointments | Implemented | `/api/dashboard/` `upcoming`, `dash-upcoming` | — | — | P3 |
| 8 | Outstanding payments | Verified | `dash-owed`, `balance_due`, `test_owner_reminder_and_unpaid_bills` | — | — | P3 |
| 9 | Revenue and profit charts | Implemented | `dashboard.js` SVG chart (6 months), `/api/reports/timeseries` | Frontend only checked by hand | — | P3 |
| 10 | Monthly comparisons | Verified | month-to-date vs the same days last month | — | — | P3 |
| 11 | Best services and packages | Verified | `top_services`, `top_plans` | — | — | P3 |

### B. CRM. `backend/routers/clients.py`, `frontend/js/clients.js`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 12 | Full client profiles | Verified | `clients` table, `test_client_crm_measurements_notes_and_retention` | No assigned trainer field | See 59 | P3 |
| 13 | Payment, package and session history | Implemented | `GET /api/clients/{id}/history` | — | — | P3 |
| 14 | Weight and body measurements | Verified | `body_measurements`, trend chart in `clients.js` | — | — | P3 |
| 15 | Transformation photos | Verified | `progress_photos`, consent required, files in `data/photos`, `test_progress_photos_need_consent_and_stay_private` | **Photos are not backed up** (S4) | Include photos in backups | P1 |
| 16 | Trainer notes and restrictions | Verified | `client_notes`, `clients.health_notes` | Restrictions are free text; no warning when booking | Show health notes on the booking drawer | P2 |
| 17 | Communication history | Partial | `notification_logs` per client | Outbound only; replies from clients are not captured | Needs WhatsApp API webhooks (41) | P2 |
| 18 | Retention and inactivity indicators | Verified | risk score in `clients.py`, `test_retention_levels` | — | — | P3 |

### C. Bookings. `backend/routers/appointments.py`, `backend/scheduling.py`, `frontend/js/calendar.js`, `frontend/js/booking.js`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 19 | Daily, weekly and monthly calendar | Implemented | `calendar.js` (day/week grid, month view, agenda) | No automated UI test | — | P3 |
| 20 | Duplicate booking prevention | Partial | `check_conflicts()` (overlaps, blocked times, `max_concurrent_sessions`) | Check-then-insert race; no database constraint; any role, trainers included, can send `force: true` to skip the check | Limit `force` to owner/manager; serialise the booking write | P1 |
| 21 | Automatic session deduction | Verified | `sessions_used += 1` on booking, refund on cancel, `test_subscription_consumes_sessions_and_refunds_on_cancel` | Deducted when **booked**, not when attended; a no-show keeps the deduction (business rule, not documented); a stored counter can drift | Add a "recalculate balance" check | P2 |
| 22 | Cancellation and rescheduling | Verified | `/status`, `/cancel-series`, `PUT`, public cancel with notice window, `test_repeat_booking_series_and_cancel` | — | — | P3 |
| 23 | Attendance tracking | Verified | `completed` / `no_show`, `late_minutes`, `test_late_arrivals_are_tracked` | — | — | P3 |
| 24 | Appointment reminders | Implemented | `run_reminder_job()` (runs inside `test_jobs_run`, no assertion on the content) | Real delivery depends on the provider | — | P3 |

### D. Packages. `backend/routers/subscriptions.py`, `discounts.py`, `giftcards.py`, `frontend/js/money.js`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 25 | Custom packages | Implemented | `subscription_plans` CRUD | — | — | P3 |
| 26 | Price, sessions and validity | Implemented | plan fields `price`, `sessions_included`, `duration_days` | — | — | P3 |
| 27 | Session balance | Verified | `sessions_remaining` | Drift risk (21) | — | P2 |
| 28 | Expiry alerts | Implemented | `run_subscription_job()` (low balance, expiry) | No dedicated test | Add a test | P2 |
| 29 | Renewal | Verified | `POST /{id}/renew`, `test_package_renewal` | — | — | P3 |
| 30 | Discount codes | Verified | `discount_codes`, `test_discount_codes` | — | — | P3 |
| 31 | Gift cards | Verified | `gift_cards`, `test_gift_cards` | — | — | P3 |

### E. Finance. `payments.py`, `expenses.py`, `reports.py`, `frontend/js/finance.js`, `frontend/js/expenses.js`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 32 | Payments | Implemented · **data-loss risk** | `/api/payments` CRUD | Deleting a client deletes their payments (S3) | Block delete or soft-delete | **P0** |
| 33 | Expenses | Verified | `/api/expenses`, CSV export, `test_expense_category_cleanup` | — | — | P3 |
| 34 | Automatic net profit | Verified | `/api/reports/finance` | — | — | P3 |
| 35 | Outstanding balances | Verified | `balance_due`, unpaid bills test | — | — | P3 |
| 36 | Cash flow | Verified | finance report, running balance, `test_finance_report` | — | — | P3 |
| 37 | Revenue per client | Implemented | finance per client, `/reports/top-clients` | — | — | P3 |
| 38 | Service profitability | Partial | `reports.py` profit **estimate** (shared costs spread by sessions) | Not real per-service costing | Optionally tag costs to services | P3 |
| 39 | Transport, fuel, maintenance, equipment, marketing costs | Implemented | keyword groups in `reports.py:40–42`, device maintenance → expense | Grouped by keyword match, so a mistyped category lands in "Other" | Use fixed category choices | P3 |
| 40 | PDF invoices | Partial | `GET /api/payments/{id}/invoice` + print page ("Save as PDF" in the browser) | No server-made PDF file, no sequential invoice numbers, cannot be attached to WhatsApp or email | Server-side PDF with numbering | P2 |

### F. Automation. `backend/notifications.py`, `routers/notifications.py`, `whatsapp/server.js`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 41 | WhatsApp Business API | Partial | Twilio WhatsApp (an official provider) is coded; the default in use is the **unofficial WhatsApp Web bridge** | No direct Meta Cloud API, no approved templates, no inbound webhooks. The WhatsApp Web route can get the number banned | Decide on a provider (cost decision) | P1 |
| 42 | Booking confirmations | Verified | `send_booking_confirmation`, `test_booking_flow_with_notifications_and_payment` | — | — | P3 |
| 43 | Reminders | Implemented | `run_reminder_job` | — | — | P3 |
| 44 | Package expiry messages | Implemented | `run_subscription_job` | — | — | P3 |
| 45 | Post-session follow-ups | Implemented | `run_follow_up_job` | No test | Add a test | P3 |
| 46 | Renewal messages | Verified | `run_renewal_offer_job` (`hold=True`), `test_not_renewed_offers_need_approval` | — | — | P3 |
| 47 | Admin approval before sensitive actions | Partial | `pending_approval` status, approve/discard/approve-all | Only renewal offers are held. **Reception can approve** (`auth.py` `_RECEPTION`). No setting to choose which message types need approval | Approval owner/manager only; per-template "needs approval" | P1 |

### G. Client portal

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 48 | Client accounts | Missing | — | No client login | Phase 5 | P1 |
| 49 | Upcoming appointments | Partial | `/a/{token}` (`manage.html`, `/api/public/appointments/{token}`) shows **one** booking per link | No list | Phase 5 | P1 |
| 50 | Remaining sessions | Missing | — | — | Phase 5 | P1 |
| 51 | Progress and measurements | Missing | the data exists in the CRM | — | Phase 5 | P2 |
| 52 | Package and invoice access | Missing | — | — | Phase 5 | P2 |
| 53 | Online booking | Verified · **insecure** | `/book`, `/api/public/book`, `test_public_booking_and_manage_link` | S2 (phone-number takeover), no rate limit or anti-spam, `staff_id` not checked (S7) | Fix S2 and S7 | **P0** |
| 54 | Renewal requests | Missing | — | — | Phase 5 | P2 |

### H. Staff. `backend/auth.py`, `routers/staff.py`, `routers/reports.py` `/staff`, `frontend/js/team.js`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 55 | Trainer accounts | Verified | `PUT /api/staff/{id}/account`, `test_staff_accounts_and_permissions` | Unique username enforced only in code on migrated databases (S11) | Add a unique index | P2 |
| 56 | Role-based permissions | Verified · gaps | `allowed()` server-side, 403 on deny | Trainers can read every client's payment history (`/clients/{id}/history`) and every message log; any role can delete push devices and send test pushes; owner sessions survive an owner password change (S5) | Tighten the rules | P1 |
| 57 | Trainer performance | Verified | `/api/reports/staff`, `test_trainer_performance_and_commission` | — | — | P3 |
| 58 | Commissions | Verified | `commission_type` / `commission_value` | Report only; no payout record | Optional payout log | P3 |
| 59 | Client and session assignment | Partial | `appointments.staff_id` | No "assigned trainer" per client; trainers see all clients | Add `clients.trainer_id` and optional scoping | P2 |

### I. Equipment and services. `routers/devices.py`, `routers/services.py`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 60 | EMS equipment inventory | Verified | `devices`, `test_devices_and_maintenance` | — | — | P3 |
| 61 | Maintenance tracking | Verified | `device_maintenance`, service-due alert on the dashboard | — | — | P3 |
| 62 | Service and pricing management | Implemented | `/api/services` CRUD | — | — | P3 |
| 63 | Service locations | Missing | no location field anywhere in the code | — | Phase 6 | P2 |
| 64 | Multi-location | Missing | — | — | Phase 6/8 | P3 |

### J. Marketing and sales. `routers/leads.py`, `frontend/js/leads.js`

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 65 | Lead management | Verified | `leads` pipeline, `test_leads_referrals_and_conversion` | — | — | P3 |
| 66 | Lead source tracking | Verified | `leads.source`, report by source | — | — | P3 |
| 67 | Referral system | Verified | `clients.referred_by_client_id`, `/api/leads/referrals` | — | — | P3 |
| 68 | Referral rewards | Partial | "Mark reward given" + note | Manual only; no automatic credit or free session | Optional automatic reward | P3 |
| 69 | Lead conversion analytics | Verified | `/api/leads/report` | — | — | P3 |
| 70 | Inactive client follow-up | Partial | retention risk, `/subscriptions/not-renewed`, renewal offer | No win-back message for inactive clients who have no package | "Inactive N days" job, with approval | P2 |

### K. AI

| # | Requirement | Status | Evidence | Next action | P |
|---|---|---|---|---|---|
| 71 | AI business assistant | Missing | no LLM code or keys in the repo | Phase 7 (needs an API key and a monthly budget) | P3 |
| 72 | Natural-language finance questions | Missing | — | Phase 7 | P3 |
| 73 | Monthly business analysis | Missing | the data exists in `/reports/finance` | Phase 7 | P3 |
| 74 | Follow-up recommendations | Missing | the retention score is a rule-based start | Phase 7 | P3 |
| 75 | PDF report generation | Missing | only CSV exports (`/reports/export/*.csv`, `/expenses/export.csv`) | Phase 3 (shared with 40) | P2 |
| 76 | Sales growth recommendations | Missing | — | Phase 7 | P3 |

### L. Security and SaaS

| # | Requirement | Status | Evidence | Missing / note | Next action | P |
|---|---|---|---|---|---|---|
| 77 | Secure auth and server-side authorization | Partial · **insecure points** | PBKDF2 hashes, HMAC-signed tokens, server role checks, login throttling | S1, S5, S6, S10, S13, S14 | Phase 0 | **P0** |
| 78 | Automated backups | Partial | `backend/backups.py`, daily, 14 kept, `test_database_backups` | Same server only; photos not included; restore never tested (S4) | Off-site copy + photos + restore drill | P1 |
| 79 | Client data privacy | Partial | photo consent, secrets hidden from staff, private photo files | XSS (S1), secrets in plain text (S8), broad trainer read access, no data-export or retention policy | Phase 0 + P2 items | P1 |
| 80 | Audit logs | Verified | `backend/audit.py`, `test_audit_log_records_every_change` | Reads, logins and denied requests are not logged | Log logins and denials | P2 |
| 81 | Multi-tenant architecture | Missing | one SQLite database and one settings row | Phase 8 | P3 |
| 82 | Subscription billing | Missing | — | Phase 8 | P3 |
| 83 | Super Admin dashboard | Missing | — | Phase 8 | P3 |
| 84 | SaaS company management | Missing | — | Phase 8 | P3 |
| 85 | Dark mode | Implemented | `core.js` `setTheme`, `app.css` `:root[data-theme]` | Not re-checked in the browser for this audit | — | P3 |
| 86 | Mobile responsiveness | Implemented | responsive CSS, PWA | Checked at 375/768/1280 while it was being built; not re-checked for this audit | Re-test after Phase 0 | P3 |
| 87 | Database integrity | Partial | FKs and cascades declared | FKs not enforced (S11); deleting a client wipes payments (S3); unique not applied after migration; no migration versions | Phase 0 / P1 | P1 |
| 88 | API reliability and errors | Partial | consistent `HTTPException` with clear messages | No rate limiting; errors swallowed with `print()`; no structured logs or alerting; 718 `utcnow()` deprecation warnings | — | P2 |
| 89 | Production deployment and config | Partial | Actions → SSH → `deploy.sh` with health check, `.env.example`, systemd | No tests before deploy (S9), no rollback, `/docs` public, no security headers (S10), 1 worker + SQLite | Phase 0 | P1 |
| 90 | Tests and code quality | Partial | 32 passing API tests | No frontend tests; CI never runs the tests; one 1000-line test file; no coverage figure | CI test step + the tests listed here | P1 |

---

## 6. Working features (Verified or Implemented: 56)

- Dashboard: 1–11.
- CRM: 12–16, 18.
- Bookings: 19, 21–24.
- Packages: 25–31.
- Finance: 32–37, 39.
- Messages: 42–46.
- Online booking: 53 (**with S2**).
- Staff: 55–58.
- Equipment and services: 60–62.
- Leads and referrals: 65–67, 69.
- Audit log: 80.
- Dark mode and mobile: 85–86.

## 7. Partially working features (17)

| # | What is missing |
|---|---|
| 17 | Outbound messages only |
| 20 | Race condition; `force` open to every role |
| 38 | Profit is an estimate |
| 40 | Print-to-PDF only |
| 41 | No direct Meta API; unofficial bridge |
| 47 | Only renewal offers are held, and reception can approve them |
| 49 | One booking per link |
| 59 | No client-to-trainer assignment |
| 68 | Manual rewards |
| 70 | No win-back for inactive clients |
| 77 | Auth security gaps |
| 78 | Backup gaps |
| 79 | Privacy gaps |
| 87 | Database integrity |
| 88 | API reliability |
| 89 | Deployment |
| 90 | Tests |

## 8. Missing features (17)

- Client portal: 48, 50, 51, 52, 54.
- Service locations and branches: 63, 64.
- AI: 71–76 (including 75, PDF reports).
- SaaS: 81–84.

---

## 9. Bugs and security vulnerabilities

No passwords, keys or tokens are printed here.

| ID | Severity | Finding | Where | Risk | Fix |
|---|---|---|---|---|---|
| **S1** | **Critical (P0)** | **Stored XSS through inline `onclick` attributes.** `esc()` turns `'` into `&#039;`, but the browser decodes entities in an attribute value **before** running it as JavaScript, so the quote comes back and ends the JS string. The extra `.replace(/'/g, "\\'")` runs after `esc()` and does nothing. | `clients.js:73` (`deleteClient(..., '${esc(c.name)...}')`), `calendar.js:55` (block reason), `leads.js:84` (referrer name), `booking.js:143` (service name), `dashboard.js:99` (alert link) | A client name typed on the **public** `/book` page, such as `x');…//`, runs code when staff click "Delete" on that client. The login token is in `localStorage`, so it can be stolen. Confirmed by reading the code path, **not** by running an attack | Stop putting text inside inline `onclick`: use `data-*` attributes and `addEventListener`. Add a Content-Security-Policy |
| **S2** | **High (P0)** | **Public booking attaches to an existing client by phone number** and deducts a session from that client's active package, with no verification | `routers/public.py` `book()`: matches on `normalize_phone`, then `sub.sessions_used += 1` | Anyone who knows a client's number can book in their name, use up their sessions and fill the calendar | Online bookings don't deduct a package until staff confirm them, or require a one-time code to the phone |
| **S3** | **High (P0)** | **Deleting a client deletes their payments, subscriptions and appointments** (`cascade="all, delete-orphan"`) | `models.py:35–40`, `routers/clients.py` `delete_client` | Past revenue disappears from the dashboard, cash flow and finance reports. The audit log keeps a snapshot, but the reports change | Block delete when payments exist (archive instead), or soft-delete |
| **S4** | High (P1) | Backups only on the same disk; **progress photos not backed up**; restore never tested | `backend/backups.py` | Losing the server means losing everything | Nightly off-site copy (low cost), include `data/photos`, write and test a restore procedure |
| **S5** | Medium (P1) | **Owner tokens are not revoked when the owner password changes** (staff tokens carry a password stamp, owner tokens do not); tokens last 30 days; no logout on the server | `auth.py` `create_token` / `parse_token` | A stolen owner token keeps working for up to 30 days after a password change. The password shared in chat earlier should be changed **and** this fixed | Add the password stamp to owner tokens; shorter lifetime |
| **S6** | Medium (P1) | Login throttling uses the `X-Forwarded-For` header from the client as-is, and keeps its counts in memory | `routers/auth.py` `login` | An attacker can change the header on every try and get unlimited password guesses; counts reset on restart | Use only the IP set by nginx; also throttle per username; nginx `limit_req` |
| **S7** | Medium (P1) | Public endpoints have no rate limit or anti-spam; `staff_id` in public booking is not checked | `routers/public.py` | Fake bookings fill the calendar and trigger messages to any number (cost when Twilio is on) | nginx `limit_req` on `/api/public/`, check that `staff_id` exists and is active, a simple anti-bot check |
| **S8** | Medium (P2) | Provider secrets (Twilio token, SMTP password) stored in plain text in the `settings` table, so they are also inside every backup file | `models.py` `Setting` | Anyone with a backup file has the messaging credentials | Move secrets to `.env`, or encrypt them with a key kept outside the database |
| **S9** | Medium (P1) | **CI deploys without running tests**; `git reset --hard` with no rollback | `.github/workflows/*.yml`, `deploy.sh` | A broken commit goes straight to live | A `pytest` job that must pass before deploy; keep the previous commit for rollback |
| **S10** | Low (P1) | `/docs` and `/openapi.json` are public on live (checked: 200); no HSTS, CSP, X-Frame-Options or X-Content-Type-Options headers (checked on `/admin`); CORS `*`; token also accepted in the URL `?token=` (ends up in nginx logs) | `main.py`, nginx | Easier mapping of the API; clickjacking; tokens in logs | `docs_url=None, openapi_url=None` on live, add headers in nginx, restrict CORS, accept tokens in the header only |
| S11 | Low (P2) | SQLite foreign keys not enforced; `unique` not applied to columns added by migration | `database.py`, `migrate.py` | Orphan rows; possible duplicate usernames if the code check is skipped | `PRAGMA foreign_keys=ON` on connect (test first), add unique indexes in migrate |
| S12 | Low (P2) | Booking conflict check is not atomic | `scheduling.check_conflicts` + insert | Two bookings at the same moment can both succeed | `BEGIN IMMEDIATE` around check and insert |
| S13 | Low (P2) | Default admin password fallback `luz-admin` if `LUZ_ADMIN_PASSWORD` is not set on a new install; owner minimum length is 6 (staff 8) | `auth.py`, `routers/auth.py` | Weak first-run password | Refuse to start without one; minimum 10 |
| S14 | Low (P3) | PBKDF2-SHA256 at 100,000 rounds (current advice is 600,000 or more), 8-byte salt | `auth.py` | Below current guidance | Raise the rounds; rehash on next login |
| S15 | Info | WhatsApp Web bridge (whatsapp-web.js) is not an official API | `backend/whatsapp/` | The studio's number can be banned | See 41 |

- **SQL injection: none found.** All queries use the SQLAlchemy ORM or bound parameters. The only raw SQL is in `migrate.py`, and it builds names from the models, not from user input.
- **Path traversal: none found.** Backup downloads are checked with a strict regex, and photo filenames are random names made by the server.

## 10. Technical debt and performance

- **Business logic lives in the routers**, with no service layer. That makes the portal and SaaS work harder.
- **SQLite + 1 worker + jobs inside the web process.** Fine for one studio; not suitable for multi-tenant use.
- **Python loops over whole tables.** For example, public booking runs `for c in db.query(models.Client).all()` to match a phone number. This slows down as the data grows. Store a normalised, indexed phone column.
- **Stored counter for session balance** (`sessions_used`). It can drift from the real appointments.
- `datetime.utcnow()` is deprecated (718 warnings in the tests).
- No migration versioning; additive changes only.
- The frontend is global functions with HTML built from strings. That is what causes the XSS pattern (S1), and it is hard to test.
- Errors are logged with `print()`. There is no error tracking or uptime alert.
- One 1000-line test file; no frontend or end-to-end tests.

## 11. Recommended improvements, in order

1. Fix S1, S2, S3 (P0).
2. Run tests in CI before deploy; disable `/docs` on live; add security headers (S9, S10).
3. Off-site backups including photos, plus a restore drill (S4).
4. Owner token revocation, proper throttling, public rate limit (S5, S6, S7).
5. Tighten roles: approvals owner/manager only, trainer read scope, `force` override (47, 56, 20).
6. Server-side PDF invoices and reports (40, 75).
7. Then new features in the phases below.

---

## 12. Development roadmap

| Phase | Scope | Done today | Complexity | Depends on | Estimate |
|---|---|---|---|---|---|
| **0. Hardening** *(new, recommended first)* | S1–S7, S9, S10; approvals and `force` owner/manager only; tests for 6, 28, 45 | — | Low–Medium | — | 2–3 days |
| 1. Core dashboard and CRM | Left: assigned trainer per client (59), health-note warning when booking (16) | ~90% | Low | 0 | 1–2 days |
| 2. Booking and package automation | Left: atomic booking (S12), balance re-check (21/27), win-back job for inactive clients (70) | ~85% | Low–Medium | 0 | 2–3 days |
| 3. Financial intelligence | Left: server PDF invoices with numbering (40), PDF monthly report (75), fixed expense categories (39) | ~80% | Medium | 0 | 3–4 days |
| 4. WhatsApp and notifications | Official provider (Twilio WhatsApp, already coded, or Meta Cloud API), approved templates, inbound webhook to capture replies (17), per-template approval (47) | ~65% | Medium | Business decision + Meta/Twilio account (**costs money**) | 4–6 days once the account exists |
| 5. Client portal | Client login by one-time WhatsApp/SMS code, upcoming bookings, sessions left, progress, invoices, renewal request (48–54) | ~15% (booking page + manage link) | Medium–High | Phase 0 (S1, S2 first); Phase 4 to deliver the codes; Phase 3 for invoices | 1.5–2 weeks |
| 6. Staff and equipment | Left: service locations (63), payout log (58) | ~85% | Low–Medium | 0 | 2–3 days (multi-location goes with Phase 8) |
| 7. AI business assistant | Plain-language finance questions, monthly analysis, follow-up and growth suggestions (71–76), read-only over the existing reports | 0% | Medium | Phase 3; an API key and monthly budget (**costs money**) | 1–2 weeks |
| 8. Multi-tenant SaaS | Tenants, data isolation, subscription billing, super admin, company management, multi-location (64, 81–84). Needs SQLite → Postgres, a service layer, jobs moved out of the web process | 0% | **High** | All earlier phases; a business decision | 6–10 weeks |

## Recommendation for the first phase

**Start with Phase 0 (hardening), then Phase 5 (Client Portal).**

- Phase 0 comes first because three of the findings (S1, S2, S3) can hurt the business now. S1 and S2 can be triggered from the public booking page by anyone, and S3 erases revenue history. They are small fixes (2–3 days), and the portal would widen the same public surface, so they must be closed before it.
- After that, Phase 5 is the most valuable step. Phases 1, 2, 3 and 6 are already 80–90% done, so more work there improves things only a little. The portal is the largest gap clients can see, and it reuses data that already exists. It needs one decision from you: **how clients sign in.** My recommendation is a one-time code sent by WhatsApp or SMS.

No changes are made until you approve.
