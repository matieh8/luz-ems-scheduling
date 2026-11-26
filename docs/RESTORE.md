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

## Off-site copies (Amazon S3)

Every new backup is also uploaded to your own S3 bucket, so losing the server does not lose the data.
Set it up once (about 10 minutes, in the AWS console, signed in as yourself):

1. **Bucket**: S3 → Create bucket. Name e.g. `luz-ems-backups-<something unique>` (lower case, no dots),
   region `me-central-1` (UAE). Keep "Block all public access" **on** (the default). Encryption stays on (default).
2. **Keep 90 days**: open the bucket → Management → Create lifecycle rule → apply to all objects →
   "Expire current versions of objects" after 90 days.
3. **Upload-only user**: IAM → Users → Create user `luz-ems-backup` (no console access) →
   Permissions → Attach policies directly → Create policy → JSON:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{ "Effect": "Allow", "Action": "s3:PutObject",
                     "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/luz-ems/*" }]
   }
   ```

   The key can only add files under `luz-ems/`: it cannot read, list or delete anything, so even if it leaked,
   nobody could take or wipe your backups with it.
4. Open the user → Security credentials → Create access key → "Application running outside AWS".
   Copy the Access key ID and Secret access key.
5. In the app: Settings → Backups → Off-site copy (Amazon S3) → fill in the four fields → **Save and test**.
   It uploads the newest backup at once; you should then see it in the bucket under `luz-ems/live/`.

If an upload fails, the app tries again every hour and sends one phone notification.

**Restoring from S3**: in the AWS console open the bucket → `luz-ems/live/` → pick the `app-….db` (and the
`photos-….zip` with the same time) → Download, then follow "Restoring a backup" above, copying the file to
`data/backups/` on the server first (e.g. `scp app-….db ubuntu@server:luz_ems_scheduling/data/backups/`).
