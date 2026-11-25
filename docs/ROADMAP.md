# LUZ EMS: development checklist status

Status of the owner's checklist (items 1–90). ✅ done · 🟡 partly · ⬜ not started · 🔑 needs an owner decision, account or spend first.
Work lands on `staging` first, then `main` (live) after the owner tries it.

## 1–17 Design and dashboard
✅ 1 Premium Emerald theme · ✅ 2 New dashboard · ✅ 3 Dark mode (light / dark / follow device) · ✅ 4 Sidebar/icons · ✅ 5 Responsive · ✅ 6 Unified type/icons/cards · ✅ 7–17 Dashboard figures

## 18–24 CRM
✅ 18 Client profile · ✅ 19 Payments, packages, sessions history · ✅ 20 Weight, measurements, body fat · ✅ 21 Before/after photos with consent ·
✅ 22 Trainer notes, injuries, restrictions · ✅ 23 Contact log · ✅ 24 Regularity / churn risk

## 25–30 Sessions and bookings
✅ 25 Day, week, month (+agenda) · ✅ 26 No double booking · ✅ 27 Auto-deduct package session · ✅ 28 Cancel / reschedule ·
✅ 29 Attendance, no-show, late minutes · ✅ 30 Reminders

## 31–37 Packages
✅ 31–34 Plans, price, sessions, validity, usage, expiry alerts · ✅ 35 Renewal (with carry-over) · ✅ 36 Discount codes · ✅ 37 Gift cards

## 38–46 Money
✅ 38–41 Payments, expenses, net profit, money owed · ✅ 42 Cash flow · ✅ 43 Average revenue per client · ✅ 44 Profit per service/package (estimate) ·
✅ 45 Expense categories + business groups in Finance · ✅ 46 Invoices (print / Save as PDF; studio is not VAT registered, so plain "Invoice" with no VAT line)

## 47–53 Automation and WhatsApp
🔑 47 WhatsApp Business API (Meta account + per-message cost; today: WhatsApp Web bridge / Twilio) · ✅ 48–51 Confirmations, reminders, expiry, follow-up · ✅ 52 Renewal offers · ✅ 53 Owner approval before marketing messages go out (payments are only ever recorded by the owner)

## 54–60 Client portal
🔑 54–60 Client accounts (how clients sign in, e.g. a one-time code by WhatsApp). Today: public booking page + per-booking link.

## 61–65 Staff
✅ 61–62 Staff logins and role permissions (server-enforced) · ✅ 63 Trainer performance · ✅ 64 Commissions · 🟡 65 Sessions per trainer (assignment exists)

## 66–70 Equipment and services
✅ 66–67 EMS devices, service schedule, maintenance log (+ expense) · ✅ 68 Services and prices · ⬜ 69 Service locations · ⬜ 70 Multi-branch

## 71–76 Marketing
✅ 71 Leads pipeline · ✅ 72 Client source · ✅ 73–74 Referrals and rewards · ✅ 75 Conversion by source · ✅ 76 Clients who did not renew

## 77–82 AI
🔑 77–82 Assistant, natural-language questions, monthly analysis, PDF reports (needs an AI API key and a monthly cost)

## 83–90 Security and SaaS
✅ 83 Server-side login, roles, lockout after wrong passwords · ✅ 84 Automatic daily database backups (14 kept on the server; download for off-site copy) · 🟡 85 Data protection · ✅ 86 Audit log (every change, secrets hidden, 1 year) ·
🔑 87–90 Multi-tenant SaaS, subscriptions, super admin, selling to other studios (big business decision)

## Phase 0: hardening (from docs/AUDIT_REPORT.md, 2026-11-25)
✅ S1 XSS in buttons fixed (`jsArg`) + security headers · ✅ S2 online bookings don't use a package until the studio confirms or completes them; stored name not revealed ·
✅ S3 a client who paid is archived, never deleted with their payments · ✅ S4 backups include photos (zip) + restore guide `docs/RESTORE.md` (off-site copy still manual) ·
✅ S5 owner password change signs out other devices; old tokens need one new sign-in · ✅ S6 login lock can't be dodged with a fake header; per-account limit ·
✅ S7 public booking rate limit + trainer check · ✅ S9 GitHub runs the tests before every deploy · ✅ S10 `/docs` hidden on live/staging ·
✅ only owner/manager can approve held messages or book over a clash · ✅ tests for expiring packages, expiry and follow-up messages
