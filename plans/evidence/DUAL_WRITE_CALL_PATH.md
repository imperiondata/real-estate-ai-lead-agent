# Dual-write worker call path

**Date:** 24 November 2026
**Owner:** Aritro
**Scope:** throwaway `v2_process_restart` on `127.0.0.1` only. Not Render. Not `realestate_db`. Not a live cutover. Not the post-cutover rollback.

`plans/evidence/NOV4_PROCESS_RESTART.log` is the 4 November run. This note does not replace it.

## Call path

```text
scripts/run_v2_process_restart_drill.py
  -> app.migration.process_restart_drill.run_process_restart_drill
    -> python -m app.migration.process_restart_worker --case <case>
    -> terminate that PID after READY
    -> python -m app.migration.process_restart_worker --readback
    -> python -m app.migration.process_restart_worker --recover
```

The worker calls `apply_dual_write` from `app.migration.dry_run`. `DryRunStore` dies with the process. The durability proof is the committed `dual_write_failures` row and the committed lead row, read back by a second operating-system process with a different PID. Recovery upserts the missing side once. The upsert is `ON CONFLICT DO NOTHING`, so a replay does not insert a second row.

## Flag

Global `V2_DUAL_WRITE` stays false. The drill prints the observed `os.environ.get("V2_DUAL_WRITE", "false")` as `live_dual_write_flag=`. It is not a hardcoded string.

The worker still sets `store.dual_write = True` on database `v2_process_restart` only. That is how the drill exercises the dual-write code path while the live flag is false. It does not open a second DSN and it does not point `DATABASE_URL` at Render.

## Injected case

`v2_success_v1_failure` is synthetic. `fail_tables_for_case` returns `["v1_leads"]` only for that case name. The worker then upserts `decision["written"]` through `production_upsert_order`, which commits `v1_leads` before `v2.leads` when both are present.

The injected case skips the V1 write. It does not commit V2 and then fail a later V1 commit. Under the production order, V1 is written first, so V2-success/V1-failure is unreachable unless that case name injects the skip.

`rollback()` is unchanged. This note is not a post-cutover rollback drill.

## Log

`plans/evidence/DUAL_WRITE_CALL_PATH.log`

- `live_dual_write_flag=false`
- `staging_claim=false`
- `render_used=false`
- `live_database_used=false`
- `order=injected production_order=v1_then_v2`
- `duplicate=false`
