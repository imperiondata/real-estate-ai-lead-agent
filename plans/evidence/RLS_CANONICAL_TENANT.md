# Canonical tenant context proof

**Date:** 24 November 2026
**Owner:** Aritro
**Scope:** throwaway `v2_isolation_drill` on `127.0.0.1` only. Not V1. Not Render. Not staging.
**Tier:** synthetic database fixtures. Not staging.

## Name

The only GUC is `app.current_tenant_id`. `app.tenant_id` and `app.current_client_id` are not set. `plans/architecture-sprint/00_SYSTEM_ARCHITECTURE.md` is historical and now uses the same name.

`app.migration.tenant_context.set_current_tenant_id` is `set_config('app.current_tenant_id', value, true)`. A missing value raises. It is not replaced with tenant 1. An invalid value is passed through so the policy cast fails closed.

## What this does not change

V1 `SessionLocal` does not call the helper. `database.py` and `main.py` do not set the GUC. V1 still filters by `client_id`. RLS is not enabled on V1 or on Render. M-16 stays target-only.

`plans/evidence/ISOLATION_DRILL.log` is the 1 November policy-shape run. This note does not replace it.

## What the new log must show

`plans/evidence/RLS_CANONICAL_TENANT.log`

- `staging_claim=false`
- `render_used=false`
- `live_database_used=false`
- `v1_render_rls=not_shipped`
- `RLS_ROLE rolsuper=false rolbypassrls=false app_is_owner=false relforcerowsecurity=true`
- `APP_PRIVILEGES select=true insert=true update=true delete=false truncate=false`
- missing setting returns 0 rows
- a non-UUID returns `22P02` and 0 rows
