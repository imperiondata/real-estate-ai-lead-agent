"""IREIOS 3.0 — n8n Workflow Import Script

Creates and activates 6 n8n workflows from JSON definitions in n8n_workflows/.
Requires N8N_BASE_URL and N8N_API_KEY in .env or environment.

Usage:
    python import_n8n_workflows.py                   # import all
    python import_n8n_workflows.py --workflow 1       # import WF-1 only
    python import_n8n_workflows.py --dry-run          # show what would be created
    python import_n8n_workflows.py --deactivate-all   # deactivate all active workflows
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os

N8N_BASE_URL = (os.getenv("N8N_BASE_URL", "http://localhost:5678")).rstrip("/")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_WEBHOOK_BASE = os.getenv("N8N_WEBHOOK_BASE", "http://localhost:5678")

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
    1: "Hot Lead Alert -> Gmail (IF handoff -> [HANDOFF] prefix, ELSE [HOT] prefix)",
    2: "Site Visit Fan-out -> Gmail (IF google_calendar -> event, ELSE -> stub)",
    3: "HITL Manager Notify -> Gmail (approval request with approve/reject links)",
    4: "CRM Note -> Google Sheets (append/update row on lead.qualified)",
    5: "Marketing Report -> Gmail (cron weekly, convert to CSV, email)",
    6: "DLQ Depth Monitor -> Gmail (cron every 15min, alert if pending > 0)",
}


def api_headers() -> dict:
    return {
        "X-N8N-API-KEY": N8N_API_KEY,
        "Content-Type": "application/json",
    }


async def import_workflow(client: httpx.AsyncClient, wf_id: int, data: dict) -> dict:
    """POST workflow JSON to n8n, return response."""
    url = f"{N8N_BASE_URL}/api/v1/workflows"
    resp = await client.post(url, json=data, headers=api_headers())
    return resp.json(), resp.status_code


async def activate_workflow(client: httpx.AsyncClient, workflow_n8n_id: str) -> dict:
    """Activate workflow via POST /api/v1/workflows/{id}/activate."""
    url = f"{N8N_BASE_URL}/api/v1/workflows/{workflow_n8n_id}/activate"
    resp = await client.post(url, headers=api_headers())
    return resp.json(), resp.status_code


async def list_workflows(client: httpx.AsyncClient) -> list:
    """GET all workflows."""
    url = f"{N8N_BASE_URL}/api/v1/workflows"
    resp = await client.get(url, headers=api_headers())
    if resp.status_code == 200:
        return resp.json().get("data", [])
    return []


async def deactivate_workflow(client: httpx.AsyncClient, workflow_n8n_id: str) -> dict:
    """Deactivate workflow via POST /api/v1/workflows/{id}/deactivate."""
    url = f"{N8N_BASE_URL}/api/v1/workflows/{workflow_n8n_id}/deactivate"
    resp = await client.post(url, headers=api_headers())
    return resp.json(), resp.status_code


async def run_import(workflow_filter: int | None = None, dry_run: bool = False, deactivate: bool = False):
    if not N8N_API_KEY:
        print("ERROR: N8N_API_KEY not set. Set it in .env or environment.")
        print("  Get your API key from: http://localhost:5678/settings/api")
        sys.exit(1)

    print(f"n8n base URL: {N8N_BASE_URL}")
    print(f"API key: {N8N_API_KEY[:8]}...")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Health check
        try:
            health = await client.get(f"{N8N_BASE_URL}/healthz")
            if health.status_code != 200:
                print(f"WARNING: n8n health check returned {health.status_code}")
            else:
                print("n8n health check: OK")
        except Exception as e:
            print(f"ERROR: Cannot reach n8n at {N8N_BASE_URL}: {e}")
            sys.exit(1)

        # Deactivate all
        if deactivate:
            existing = await list_workflows(client)
            print(f"\nDeactivating {len(existing)} workflows...")
            for wf in existing:
                if wf.get("active"):
                    await deactivate_workflow(client, wf["id"])
                    print(f"  Deactivated: {wf.get('name', wf['id'])}")
            print("Done.")
            return

        # List existing
        existing = await list_workflows(client)
        existing_names = {wf.get("name"): wf for wf in existing}
        print(f"Existing workflows: {len(existing)}")
        for wf in existing:
            status = "ACTIVE" if wf.get("active") else "inactive"
            print(f"  [{status}] {wf.get('name', wf['id'])}")
        print()

        # Import each workflow
        ids_to_import = [workflow_filter] if workflow_filter else list(WORKFLOW_FILES.keys())
        created = {}

        for wf_id in ids_to_import:
            fname = WORKFLOW_FILES.get(wf_id)
            if not fname:
                print(f"WARNING: Unknown workflow ID {wf_id}, skipping")
                continue

            fpath = WORKFLOW_DIR / fname
            if not fpath.exists():
                print(f"ERROR: {fpath} not found")
                continue

            with open(fpath) as f:
                data = json.load(f)

            # Tags are read-only in n8n API — strip before POST
            data.pop("tags", None)

            desc = WORKFLOW_DESCRIPTIONS.get(wf_id, "")
            print(f"--- WF-{wf_id}: {desc}")
            print(f"    File: {fname}")

            if dry_run:
                print(f"    [DRY RUN] Would create workflow: {data.get('name')}")
                print(f"    Nodes: {len(data.get('nodes', []))}")
                print()
                continue

            # Check if already exists
            if data.get("name") in existing_names:
                existing_wf = existing_names[data["name"]]
                print(f"    Already exists (id={existing_wf['id']}), skipping creation")
                created[wf_id] = existing_wf["id"]
                continue

            try:
                result, status = await import_workflow(client, wf_id, data)
                if status in (200, 201):
                    n8n_id = result.get("id", "")
                    print(f"    Created: id={n8n_id}")
                    created[wf_id] = n8n_id

                    # Activate
                    act_result, act_status = await activate_workflow(client, n8n_id)
                    if act_status == 200:
                        print(f"    Activated: OK")
                    else:
                        print(f"    Activate failed: {act_status} - {act_result}")
                else:
                    print(f"    Create failed: {status} - {result}")
            except Exception as e:
                print(f"    Error: {e}")

            print()

        # Summary
        if not dry_run and created:
            print("=" * 60)
            print("SUMMARY — Imported Workflows")
            print("=" * 60)
            print(f"{'WF':<5} {'n8n ID':<12} {'Webhook URL'}")
            print("-" * 60)
            for wf_id, n8n_id in sorted(created.items()):
                webhook_path = _get_webhook_path(WORKFLOW_DIR / WORKFLOW_FILES[wf_id])
                webhook_url = f"{N8N_WEBHOOK_BASE}/webhook/{webhook_path}"
                print(f"WF-{wf_id:<3} {n8n_id:<12} {webhook_url}")
            print()
            print("WEBHOOK_URLS = {")
            for wf_id, n8n_id in sorted(created.items()):
                webhook_path = _get_webhook_path(WORKFLOW_DIR / WORKFLOW_FILES[wf_id])
                webhook_url = f"{N8N_WEBHOOK_BASE}/webhook/{webhook_path}"
                print(f'  "{wf_id}": "{webhook_url}",')
            print("}")

        elif dry_run:
            print("DRY RUN complete. No workflows were created.")


def _get_webhook_path(fpath: Path) -> str:
    """Extract webhook path from workflow JSON."""
    with open(fpath) as f:
        data = json.load(f)
    for node in data.get("nodes", []):
        if node.get("type") == "n8n-nodes-base.webhook":
            return node.get("parameters", {}).get("path", "unknown")
    return "unknown"


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
        asyncio.run(run_import(
            workflow_filter=args.workflow,
            dry_run=args.dry_run,
            deactivate=args.deactivate_all,
        ))


async def _list_only():
    if not N8N_API_KEY:
        print("ERROR: N8N_API_KEY not set")
        sys.exit(1)
    async with httpx.AsyncClient(timeout=10.0) as client:
        existing = await list_workflows(client)
        print(f"Workflows in n8n ({len(existing)}):")
        for wf in existing:
            status = "ACTIVE" if wf.get("active") else "inactive"
            print(f"  [{status}] id={wf['id']} name={wf.get('name')}")


if __name__ == "__main__":
    main()
