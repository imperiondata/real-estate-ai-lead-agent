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

## 5. INF-01 S3 proof

A local dump followed by a local restore is not the proof. `scripts/prove_inf01_s3_drill.py` dumps the local database, uploads that file with `ChecksumAlgorithm=SHA256`, and refuses to download unless `HeadObject` `ChecksumSHA256` matches the local digest. It then restores into local `inf01_drill` and matches table counts. It refuses a non-local source or restore host. It does not read `LIVE_DATABASE_URL`. It does not print the URL, the AWS key, or row data.

```powershell
python scripts/prove_inf01_s3_drill.py --check
python scripts/prove_inf01_s3_drill.py
```

`--check` does not dump or upload. The full run needs `S3_BACKUP_BUCKET`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY`. Set `AWS_REGION=ap-south-1`. If it is unset, the script falls back to `us-east-1`. Do not set `KMS_KEY_ARN` for the AES-256 bucket. The moto test in `tests/test_p0_security_remediation.py` is not this proof.

### Completed run (2026-10-21)

Local Postgres only. Not Render. No new script commit. The script was `2ce644d` on `remediation/p0-security-fixes`.

| Field | Result |
|-------|--------|
| backup_id | `inf01-drill/20261021T162032Z/local_backup_20261021T162032Z.sql` |
| bucket | `ai-unique-system-paas-production-backups` |
| region | `ap-south-1` |
| sse | `AES256` (KMS not set) |
| started_at | `2026-10-21T16:20:32Z` |
| finished_at | `2026-10-21T16:21:53Z` |
| recovery_seconds | `81.565` |
| s3_checksum_match | yes |
| sidecar_match | yes |
| counts_match | yes |
| source_db | `realestate_db` |
| restore_db | `inf01_drill` |
| result | `INF01_S3_DRILL_PASS` |

`HeadObject` `ChecksumSHA256` matched the local digest before download. Sixteen public tables were counted on the source and on `inf01_drill`. The counts matched. Local dump files were deleted. The S3 object and its `.sha256` sidecar were left in the bucket.

## 6. Render Production Notes

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

## 7. Earlier local restore (2026-06-17)

This table is `db_backup.py` / `db_restore.py` only. It is not the INF-01 S3 proof. That proof is section 5.

| Step                  | Result |
|-----------------------|--------|
| Docker container up   | ✅     |
| `python db_backup.py` | ✅ `backup_20260617_073805.sql` created |
| `python db_restore.py backups/backup_20260617_073805.sql` | ✅ Completed without error |
| Table verification query | ✅ All tables intact |
| Reproducible by another engineer | ✅ Steps above are self-contained |