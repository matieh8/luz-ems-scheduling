# Restoring from a backup

Backups are made automatically once a day into `<data folder>/backups` on the server (live: `data/backups`, staging: `data-staging/backups`). There are two kinds of file:

- `app-YYYY-MM-DD_HHMMSS.db`: a complete copy of the database (clients, bookings, payments, everything).
- `photos-YYYY-MM-DD_HHMMSS.zip`: all progress photos, made at the same moment. Only created when there are photos.

You can download either one from **Settings → Backups**. Keep a recent pair somewhere off the server, for example Google Drive or your laptop.

## Restore on the server

1. Stop the app so nothing writes while you restore:
   `sudo systemctl stop luz-ems.service` (staging: `luz-ems-staging.service`)
2. Keep the current database, in case you need it again:
   `cp data/app.db data/app.db.before-restore`
3. Put the backup in place:
   `cp data/backups/app-2026-11-25_030000.db data/app.db`
4. Photos (only if they are missing or damaged):
   `cd data && unzip -o backups/photos-2026-11-25_030000.zip`
   (the zip already contains the `photos/<client id>/...` folders)
5. Start the app again: `sudo systemctl start luz-ems.service`
6. Check that `https://admin.luzfitlife.com/api/health` shows `ok`, then sign in and look at the dashboard and a few clients.

Anything after the backup's time (new bookings and payments) has to be entered again by hand.

## Checking that backups can be restored

The automated test `test_backup_restores_clients_payments_and_photos` makes a backup, restores the database copy into a new file, and checks that the client, their payment and their photo are all there. It runs with every change to the code.
