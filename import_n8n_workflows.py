"""IREIOS 3.0 — n8n Workflow Import Script

Creates and activates 6 n8n workflows from JSON definitions in n8n_workflows/.

Auth (TWO KEYS — do not mix):
  * N8N_MANAGEMENT_API_KEY — JWT from n8n UI Settings → n8n API
    Used as X-N8N-API-KEY on POST /api/v1/workflows (this script).
  * N8N_API_KEY — webhook Header Auth secret only (backend bridge).
    Never works for the management API (always 401).

Usage:
    python import_n8n_workflows.py                   # import all
    python import_n8n_workflows.py --workflow 1       # import WF-1 only
    python import_n8n_workflows.py --dry-run          # show what would be created
    python import_n8n_workflows.py --deactivate-all   # deactivate all active workflows
    python import_n8n_workflows.py --list             # list existing

CLI fallback (no management JWT): see docs/N8N_INTEGRATION.md § Import
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import os

N8N_BASE_URL = (os.getenv("N8N_BASE_URL", "http://localhost:5678")).rstrip("/")
# Management JWT only — never the webhook secret.
N8N_MANAGEMENT_API_KEY = (
    os.getenv("N8N_MANAGEMENT_API_KEY", "").strip()
    or os.getenv("N8N_PUBLIC_API_KEY", "").strip()
)
N8N_WEBHOOK_BASE = os.getenv("N8N_WEBHOOK_BASE", N8N_BASE_URL).rstrip("/")
N8N_CONTAINER = os.getenv("N8N_CONTAINER", "n8n-local")

WORKFLOW_DIR = Path(__file__).parent / "n8n_workflows"

WORKFLOW_FILES = {
    1: "wf1_hot_lead_alert.json",
    2: "wf2_site_visit_fanout.json",
    3: "wf3_hitl_notify.json",
    4: "wf4_crm_note.json",
    5: "wf5_marketing_report.json",
    6: "wf6_dlq_depth_monitor.json",
}

WORKFLOW_DESCRIPTIONS = {
    1: "Hot Lead Alert -> Gmail",
    2: "Site Visit Fan-out -> Gmail",
    3: "HITL Manager Notify -> Gmail",
    4: "CRM Note -> Google Sheets",
    5: "Marketing Report -> Gmail + CSV",
    6: "DLQ Depth Monitor -> Gmail (cron)",
}

# Credential name → n8n type key used on nodes
CRED_NAME_TO_TYPE = {
    "IREIOS API Key": "httpHeaderAuth",
    "Gmail account": "gmailOAuth2",
    "Google Sheets account": "googleSheetsOAuth2Api",
}

# Fields n8n rejects or should not be POSTed on create
_STRIP_TOP_LEVEL = {
    "id",
    "updatedAt",
    "createdAt",
    "active",
    "isArchived",
    "versionId",
    "activeVersionId",
    "versionCounter",
    "triggerCount",
    "tags",
    "shared",
    "meta",
    "pinData",
    "staticData",
    "versionMetadata",
    "sourceWorkflowId",
    "nodeGroups",
    "description",
}


def api_headers() -> dict:
    return {
        "X-N8N-API-KEY": N8N_MANAGEMENT_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _prepare_payload(data: dict, cred_by_name: dict[str, dict]) -> dict:
    """Strip read-only fields and inject live credential IDs by name."""
    out = {k: v for k, v in data.items() if k not in _STRIP_TOP_LEVEL}
    nodes = []
    for node in out.get("nodes") or []:
        n = dict(node)
        creds = n.get("credentials")
        if isinstance(creds, dict) and creds:
            fixed: dict = {}
            for ctype, cref in creds.items():
                if not isinstance(cref, dict):
                    continue
                name = (cref.get("name") or "").strip()
                match = cred_by_name.get(name) if name else None
                if match:
                    fixed[ctype] = {"id": match["id"], "name": match["name"]}
                elif cref.get("id"):
                    fixed[ctype] = {"id": cref["id"], "name": name or cref.get("name", "")}
                else:
                    # leave name-only so UI can still match; may warn
                    fixed[ctype] = {"id": "", "name": name}
            n["credentials"] = fixed
        nodes.append(n)
    out["nodes"] = nodes
    if "settings" not in out:
        out["settings"] = {"executionOrder": "v1"}
    return out


async def resolve_credentials(client: httpx.AsyncClient) -> dict[str, dict]:
    """Map credential name → {id, name, type}. REST first, CLI export fallback."""
    by_name: dict[str, dict] = {}

    # Public API (may 401/404 on some editions)
    for path in ("/api/v1/credentials", "/rest/credentials"):
        try:
            resp = await client.get(f"{N8N_BASE_URL}{path}", headers=api_headers())
            if resp.status_code != 200:
                continue
            body = resp.json()
            rows = body if isinstance(body, list) else body.get("data") or body.get("credentials") or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = (row.get("name") or "").strip()
                cid = row.get("id")
                if name and cid:
                    by_name[name] = {
                        "id": str(cid),
                        "name": name,
                        "type": row.get("type") or "",
                    }
            if by_name:
                print(f"Credentials via REST {path}: {len(by_name)}")
                return by_name
        except Exception as exc:  # noqa: BLE001
            print(f"  REST credentials {path} failed: {exc}")

    # CLI export inside Docker (no secrets needed in response for id/name/type)
    print(f"Falling back to: docker exec {N8N_CONTAINER} n8n export:credentials --all")
    try:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                N8N_CONTAINER,
                "n8n",
                "export:credentials",
                "--all",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        raw = (proc.stdout or "").strip()
        if proc.returncode != 0 or not raw:
            print(f"  CLI export failed rc={proc.returncode}: {(proc.stderr or '')[:300]}")
            return by_name
        # stdout may include log lines before JSON
        start = raw.find("[")
        if start < 0:
            start = raw.find("{")
        blob = raw[start:] if start >= 0 else raw
        data = json.loads(blob)
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = (row.get("name") or "").strip()
            cid = row.get("id")
            if name and cid:
                by_name[name] = {
                    "id": str(cid),
                    "name": name,
                    "type": row.get("type") or "",
                }
        print(f"Credentials via CLI: {len(by_name)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  CLI credential resolve failed: {exc}")
    return by_name


async def import_workflow(client: httpx.AsyncClient, data: dict) -> tuple[dict, int]:
    url = f"{N8N_BASE_URL}/api/v1/workflows"
    resp = await client.post(url, json=data, headers=api_headers())
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {"raw": resp.text[:500]}
    return body, resp.status_code


async def activate_workflow(client: httpx.AsyncClient, workflow_n8n_id: str) -> tuple[dict, int]:
    url = f"{N8N_BASE_URL}/api/v1/workflows/{workflow_n8n_id}/activate"
    resp = await client.post(url, headers=api_headers())
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {"raw": resp.text[:500]}
    return body, resp.status_code


async def list_workflows(client: httpx.AsyncClient) -> list:
    url = f"{N8N_BASE_URL}/api/v1/workflows"
    resp = await client.get(url, headers=api_headers())
    if resp.status_code == 200:
        body = resp.json()
        if isinstance(body, list):
            return body
        return body.get("data", []) or []
    if resp.status_code == 401:
        print(
            "ERROR: management API returned 401.\n"
            "  N8N_MANAGEMENT_API_KEY must be a JWT from n8n UI → Settings → n8n API.\n"
            "  Do NOT use N8N_API_KEY (webhook secret) here — that always 401s /api/v1/*.\n"
            "  Create key: http://localhost:5678/settings/api"
        )
    return []


async def deactivate_workflow(client: httpx.AsyncClient, workflow_n8n_id: str) -> tuple[dict, int]:
    url = f"{N8N_BASE_URL}/api/v1/workflows/{workflow_n8n_id}/deactivate"
    resp = await client.post(url, headers=api_headers())
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {"raw": resp.text[:500]}
    return body, resp.status_code


def _get_webhook_path(fpath: Path) -> str:
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)
    for node in data.get("nodes", []):
        if node.get("type") == "n8n-nodes-base.webhook":
            return node.get("parameters", {}).get("path", "unknown")
    return "(cron/no-webhook)"


def _print_missing_mgmt_key() -> None:
    print("ERROR: N8N_MANAGEMENT_API_KEY not set.")
    print("  1. Open http://localhost:5678/settings/api")
    print("  2. Create an API key (JWT)")
    print("  3. Put it in .env: N8N_MANAGEMENT_API_KEY=<jwt>")
    print("  4. Re-run this script")
    print()
    print("CLI fallback (no JWT):")
    print("  docker cp n8n_workflows n8n-local:/tmp/n8n_workflows")
    print("  docker exec -u node n8n-local n8n import:workflow --separate --input=/tmp/n8n_workflows")
    print("  # then publish each workflow id + docker restart n8n-local")
    print("  See docs/N8N_INTEGRATION.md")


async def run_import(
    workflow_filter: int | None = None,
    dry_run: bool = False,
    deactivate: bool = False,
):
    if not N8N_MANAGEMENT_API_KEY:
        _print_missing_mgmt_key()
        sys.exit(1)

    # Guard: common mistake — putting webhook secret in management slot
    webhook_secret = (os.getenv("N8N_API_KEY") or "").strip()
    if webhook_secret and N8N_MANAGEMENT_API_KEY == webhook_secret:
        print(
            "ERROR: N8N_MANAGEMENT_API_KEY equals N8N_API_KEY (webhook secret).\n"
            "  Management API needs a JWT from Settings → n8n API, not the webhook secret."
        )
        sys.exit(1)

    print(f"n8n base URL: {N8N_BASE_URL}")
    print(f"Management API key: {N8N_MANAGEMENT_API_KEY[:8]}...")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            health = await client.get(f"{N8N_BASE_URL}/healthz")
            if health.status_code != 200:
                print(f"WARNING: n8n health check returned {health.status_code}")
            else:
                print("n8n health check: OK")
        except Exception as e:
            print(f"ERROR: Cannot reach n8n at {N8N_BASE_URL}: {e}")
            sys.exit(1)

        if deactivate:
            existing = await list_workflows(client)
            print(f"\nDeactivating {len(existing)} workflows...")
            for wf in existing:
                if wf.get("active"):
                    await deactivate_workflow(client, wf["id"])
                    print(f"  Deactivated: {wf.get('name', wf['id'])}")
            print("Done.")
            return

        existing = await list_workflows(client)
        if existing is None:
            existing = []
        # list_workflows prints 401 and returns [] — detect failed auth via probe
        probe = await client.get(f"{N8N_BASE_URL}/api/v1/workflows", headers=api_headers())
        if probe.status_code == 401:
            sys.exit(1)

        existing_names = {wf.get("name"): wf for wf in existing}
        print(f"Existing workflows: {len(existing)}")
        for wf in existing:
            status = "ACTIVE" if wf.get("active") else "inactive"
            print(f"  [{status}] {wf.get('name', wf['id'])}")
        print()

        cred_by_name = await resolve_credentials(client)
        for required in CRED_NAME_TO_TYPE:
            if required not in cred_by_name:
                print(f"WARNING: credential named '{required}' not found in n8n — link manually after import")
        if cred_by_name:
            print("Resolved credentials:")
            for name, meta in cred_by_name.items():
                print(f"  {name!r} → id={meta['id']} type={meta.get('type')}")
            print()

        ids_to_import = [workflow_filter] if workflow_filter else list(WORKFLOW_FILES.keys())
        created: dict[int, str] = {}

        for wf_id in ids_to_import:
            fname = WORKFLOW_FILES.get(wf_id)
            if not fname:
                print(f"WARNING: Unknown workflow ID {wf_id}, skipping")
                continue

            fpath = WORKFLOW_DIR / fname
            if not fpath.exists():
                print(f"ERROR: {fpath} not found")
                continue

            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)

            desc = WORKFLOW_DESCRIPTIONS.get(wf_id, "")
            print(f"--- WF-{wf_id}: {desc}")
            print(f"    File: {fname}")

            payload = _prepare_payload(data, cred_by_name)

            # Guard: empty Gmail sendTo is intentional in repo — warn so ops set it in UI.
            for node in payload.get("nodes") or []:
                if node.get("type") == "n8n-nodes-base.gmail":
                    sto = (node.get("parameters") or {}).get("sendTo")
                    if not (sto or "").strip():
                        print(
                            "    WARNING: Gmail node has empty sendTo — "
                            "set recipient in n8n UI before e2e email tests"
                        )

            if dry_run:
                print(f"    [DRY RUN] Would create: {payload.get('name')}")
                print(f"    Nodes: {len(payload.get('nodes', []))}")
                print()
                continue

            if data.get("name") in existing_names:
                existing_wf = existing_names[data["name"]]
                print(f"    Already exists (id={existing_wf['id']}), skipping creation")
                created[wf_id] = existing_wf["id"]
                # still try activate
                act_result, act_status = await activate_workflow(client, existing_wf["id"])
                if act_status == 200:
                    print("    Activated: OK")
                else:
                    print(f"    Activate: {act_status} - {act_result}")
                print()
                continue

            try:
                result, status = await import_workflow(client, payload)
                if status in (200, 201):
                    n8n_id = result.get("id", "")
                    print(f"    Created: id={n8n_id}")
                    created[wf_id] = n8n_id
                    act_result, act_status = await activate_workflow(client, n8n_id)
                    if act_status == 200:
                        print("    Activated: OK")
                    else:
                        print(f"    Activate failed: {act_status} - {act_result}")
                        print("    Tip: open workflow in UI → Publish, or CLI: n8n publish:workflow --id=...")
                else:
                    print(f"    Create failed: {status} - {result}")
            except Exception as e:
                print(f"    Error: {e}")

            print()

        if not dry_run and created:
            print("=" * 60)
            print("SUMMARY — Imported Workflows")
            print("=" * 60)
            print(f"{'WF':<5} {'n8n ID':<16} {'Webhook URL'}")
            print("-" * 60)
            for wf_id, n8n_id in sorted(created.items()):
                webhook_path = _get_webhook_path(WORKFLOW_DIR / WORKFLOW_FILES[wf_id])
                if webhook_path.startswith("("):
                    webhook_url = webhook_path
                else:
                    webhook_url = f"{N8N_WEBHOOK_BASE}/webhook/{webhook_path}"
                print(f"WF-{wf_id:<3} {n8n_id:<16} {webhook_url}")
            print()
            print("NEXT (required before e2e email tests):")
            print("  1. Open each workflow in http://localhost:5678")
            print("  2. Set Gmail node To = your ops address (repo has empty sendTo by design)")
            print("  3. WF-5: edit Code node, replace OPS_EMAIL_PLACEHOLDER")
            print("  4. Save + Publish each workflow")
            print("  5. Confirm Header Auth value is: Bearer <N8N_API_KEY from .env>")
        elif dry_run:
            print("DRY RUN complete. No workflows were created.")


async def _list_only():
    if not N8N_MANAGEMENT_API_KEY:
        _print_missing_mgmt_key()
        sys.exit(1)
    async with httpx.AsyncClient(timeout=10.0) as client:
        existing = await list_workflows(client)
        probe = await client.get(f"{N8N_BASE_URL}/api/v1/workflows", headers=api_headers())
        if probe.status_code == 401:
            sys.exit(1)
        print(f"Workflows in n8n ({len(existing)}):")
        for wf in existing:
            status = "ACTIVE" if wf.get("active") else "inactive"
            print(f"  [{status}] id={wf['id']} name={wf.get('name')}")


def main():
    parser = argparse.ArgumentParser(description="Import IREIOS n8n workflows")
    parser.add_argument("--workflow", "-w", type=int, help="Import single workflow by ID (1-6)")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be created without creating")
    parser.add_argument("--deactivate-all", "-d", action="store_true", help="Deactivate all active workflows")
    parser.add_argument("--list", "-l", action="store_true", help="List existing workflows")
    args = parser.parse_args()

    if args.list:
        asyncio.run(_list_only())
    else:
        asyncio.run(
            run_import(
                workflow_filter=args.workflow,
                dry_run=args.dry_run,
                deactivate=args.deactivate_all,
            )
        )


if __name__ == "__main__":
    main()
