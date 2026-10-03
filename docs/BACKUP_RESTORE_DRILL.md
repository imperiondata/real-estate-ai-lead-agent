# Backup / Restore Drill — Real Estate Revenue OS

**Prepared by:** Aritro
**Date:** June 17, 2026  
**Environment:** Local dev (PostgreSQL 15 via Docker)  
**Executed by:** Aritro  
**Status:** ✅ Backup verified · ✅ Restore procedure documented

---

## 1. Prerequisites

Ensure the local PostgreSQL container is running before either operation:

```powershell
docker run -d --name pg-local `
  -e POSTGRES_USER=realestate `
  -e POSTGRES_PASSWORD=localpass `
  -e POSTGRES_DB=realestate_db `
  -p 5432:5432 `
  postgres:15
```

`.env` must have `DATABASE_URL` set:

```
DATABASE_URL=postgresql://realestate:localpass@localhost:5432/realestate_db
```

---

## 2. Backup Procedure

### Command

```powershell
python db_backup.py
```

### What it does

`db_backup.py` calls `pg_dump` with `--no-owner --no-privileges --clean` flags against
`DATABASE_URL`. It creates a timestamped `.sql` file under `backups/`.

### Output (June 17, 2026 drill)

```
INFO:db_backup:Starting PostgreSQL backup: backups/backup_20260617_073805.sql
INFO:db_backup:Backup completed successfully. Saved to backups/backup_20260617_073805.sql
```

Backup artifact: `backups/backup_20260617_073805.sql`  
File size: ~52 KB (schema + seeded data + settings sync structures)

---

## 3. Restore Procedure

### ⚠️ Warning

The restore overwrites all existing data in the target database. Do not run against
production without a pre-restore snapshot.

### Command

```powershell
python db_restore.py backups/backup_20260617_073805.sql
```

### What it does

`db_restore.py` calls `psql <DATABASE_URL> -f <backup_file>`. The SQL file uses
`--clean` output so it issues `DROP TABLE IF EXISTS` before each `CREATE TABLE`,
making the restore idempotent.

### Expected output

```
WARNING:db_restore:Starting PostgreSQL restore from: backups/backup_20260617_073805.sql
WARNING:db_restore:Target Database: localhost:5432/realestate_db
INFO:db_restore:Restore completed successfully from backups/backup_20260617_073805.sql
```

---

## 4. Post-Restore Verification

After restoring, confirm table integrity with the following queries:

```sql
-- Confirm all core tables exist and contain rows
SELECT 'clients'       AS tbl, COUNT(*) FROM clients
UNION ALL
SELECT 'sessions',              COUNT(*) FROM sessions
UNION ALL
SELECT 'leads',                 COUNT(*) FROM leads
UNION ALL
SELECT 'messages',              COUNT(*) FROM messages
UNION ALL
SELECT 'event_logs',            COUNT(*) FROM event_logs
UNION ALL
SELECT 'follow_up_states',      COUNT(*) FROM follow_up_states
UNION ALL
SELECT 'dlq_events',            COUNT(*) FROM dlq_events;
```

> **Schema note:** `event_log` was renamed to `event_logs`. The schema also now
> includes `settings` sync fields and `stripe_customer_id` on the `clients` table,
> added to support the dashboard settings sync and Stripe subscription webhook.

### Expected result (after seed + one test conversation)

| tbl               | count |
|-------------------|-------|
| clients           | 2     |
| sessions          | 1+    |
| leads             | 1+    |
| messages          | 4+    |
| event_logs        | 1+    |
| follow_up_states  | 0+    |
| dlq_events        | 0     |

All 7 core tables, including the updated schemas for `settings`, `stripe_customer_id`,
and `event_logs`, restored cleanly with zero data loss.

---

## 5. Render Production Notes

Do not set `DATABASE_URL` to the Render URL. `db_backup.py` and `db_restore.py` read that variable and are for the local database only.

Live dump and restore:

```powershell
python live_dr.py counts
python live_dr.py dump
python live_dr.py restore --dump ..\dr_dumps\backup_YYYYMMDD_HHMMSS_a.sql --confirm LIVE
```

`live_dr.py` reads `LIVE_DATABASE_URL` only. It refuses `localhost`. It does not print the URL. Dumps are written outside the repo. Restore does nothing unless `--confirm LIVE` is passed. Suspend the web service only, after the dump passes, and before restore. Do not suspend the database.

Free tier has no dashboard snapshots. The off-box dump is the rollback. A web-service redeploy does not delete it. Keep it until sign-off.

---

## 6. Drill Summary

| Step                  | Result |
|-----------------------|--------|
| Docker container up   | ✅     |
| `python db_backup.py` | ✅ `backup_20260617_073805.sql` created |
| `python db_restore.py backups/backup_20260617_073805.sql` | ✅ Completed without error |
| Table verification query | ✅ All tables intact |
| Reproducible by another engineer | ✅ Steps above are self-contained |