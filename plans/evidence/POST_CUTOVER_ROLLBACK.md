# Post-cutover rollback drill

**Date:** 25 November 2026
**Owner:** Aritro (drill) / Maitri (app-read assertion and matrix gating)
**Scope:** throwaway `v2_post_cutover_rollback` on `127.0.0.1` only.
**Tier:** synthetic database fixtures. Not staging. Not Render. Not a live cutover.

This is Item 4 of Piyush's remediation list. The 4 November proof
(`plans/evidence/NOV4_APP_ROLLBACK.log`) and `rollback()` are the **pre-cutover**
procedure: dual-write off, reads on V1, shadow dropped. That is not this drill.
Neither `rollback()` nor the 4 November log was changed.

## What "post-cutover" means here

After the read cut, reads are on V2 and dual-write is on. The post-cutover
rollback moves reads back to V1 while dual-write stays on, so V1 keeps receiving
writes and the shadow keeps matching it. Dropping the shadow is a later step,
not this one.

`switch_reads_to_v1(store)` in `app/migration/dry_run.py` only sets
`read_source = "v1"`. It does not touch `dual_write`, the shadow rows, or the
failure records. It does not call `rollback()`.

## Call path

```text
scripts/run_v2_post_cutover_rollback_drill.py   (or scripts/prove_v2_post_cutover_rollback.py)
  -> app.migration.post_cutover_rollback_drill.run_post_cutover_rollback_drill
     -> reset_database()            drop/create v2_post_cutover_rollback on 127.0.0.1
     -> _create_schema()            V1 ORM tables (clients, sessions, leads) + schema v2
     -> seed                        one V1 row and its shadow row, checksum recorded
     -> DryRunStore                 read_source="v2", dual_write=True (harness only)
     -> switch_reads_to_v1(store)   read_source="v1", dual-write and shadow retained
     -> apply_dual_write            decision only; production_upsert_order gives V1 then V2
     -> commit V1, then upsert v2.leads
     -> _app_read_latest()          serialize_lead on the newest V1 ORM row, no HTTP
     -> counts + SHA-256            no lost or duplicated committed row
     -> drop_database()             in a finally block
```

Global `V2_DUAL_WRITE` stays `false`. The drill prints the observed value and
refuses to run if it is anything else. `dual_write_source=drill_harness` records
that the in-memory store was switched on for this drill only.

## What the raw log shows

`plans/evidence/POST_CUTOVER_ROLLBACK.log`

| Line | Meaning |
|---|---|
| `staging_claim=false` / `render_used=false` / `live_database_used=false` | Not staging, not Render, not the app database |
| `live_dual_write_flag=false` | The global flag was observed, not hardcoded |
| `SIMULATED_CUT read_source=v2 dual_write=true` | Starts in post-cutover mode |
| `SWITCH read_source=v1 dual_write_still_on=true shadow_retained=true` | The rollback switched reads only |
| `WRITE_ORDER v1_then_v2` | Production order from `production_upsert_order`, not the injected case |
| `V1_LATEST v1_latest=true v1_id=2 shadow_id=2` | The newest row is the new row on both sides |
| `APP_READ app_read=serialize_lead lead_id=2 lead_temperature=Hot` | The application read path is compatible with the V1 row |
| `COUNTS v1_total=2 shadow_total=2 new_v1_rows=1 new_shadow_rows=1 duplicate=false` | Exact counts, no duplicate |
| `CHECKSUM v1_checksum_unchanged=true before=… after=…` | The original row is byte-identical |
| `TABLE_CHECKSUM v1=… shadow=… table_checksum_equal=true` | The full V1 and shadow tables digest identically, so nothing was lost or duplicated |
| `INTEGRITY lost=false` | No committed row was lost |
| `POST_CUTOVER_ROLLBACK_PASS` | The run completed |

The log records both totals (`2` and `2`) and the new row's per-side counts
(`1` and `1`). "Counts are 1" refers to the new row on each side, not the table
total.

## Tests

`tests/test_v2_post_cutover_rollback.py`

- `test_switch_reads_to_v1_keeps_dual_write_and_the_shadow` — in-memory;
  monkeypatches `rollback` to raise if called, then asserts `read_source="v1"`,
  `dual_write is True`, and the shadow is unchanged.
- `test_post_cutover_rollback_drill_passes_and_cleans_up` — Postgres; runs the
  drill, asserts every `REQUIRED_LINES` entry, and asserts the throwaway
  database is gone. Fails rather than skips when local Postgres is down, the
  same way `tests/test_v2_agency_isolation.py` does.

## What this does not claim

- Not Render, not `realestate_db`, not a live read cut.
- Not `rollback()`. `tests/test_v2_migration_dry_run.py::test_rollback_drops_the_shadow_and_leaves_v1`
  is unchanged.
- Not staging or production behaviour. The tier is synthetic fixtures.
- The seed row is a fixture written directly to V1 and the shadow. Only the
  post-switch record goes through `production_upsert_order`.
