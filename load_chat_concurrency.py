"""PH-A.2 live load: concurrent POST /api/v1/chat against Render.

Reads LIVE_API_BASE_URL + LIVE_CLIENT_B_KEY from .env (never print secrets).
Usage:
  python load_chat_concurrency.py --leg 25
  python load_chat_concurrency.py --leg 50
  python load_chat_concurrency.py --leg 100
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

MSG = "Hi looking for 2BHK in Baner"


def _pct(sorted_ms: list[float], p: float) -> float:
    if not sorted_ms:
        return 0.0
    k = min(len(sorted_ms) - 1, max(0, int(round((p / 100.0) * (len(sorted_ms) - 1)))))
    return sorted_ms[k]


async def _one(client: httpx.AsyncClient, base: str, key: str, sid: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f"{base.rstrip('/')}/api/v1/chat",
            params={"session_id": sid, "message": MSG},
            headers={"X-API-Key": key},
        )
        ms = (time.perf_counter() - t0) * 1000
        return {
            "session_id": sid,
            "http": r.status_code,
            "ms": round(ms, 1),
            "ok": r.status_code == 200,
            "err": "" if r.status_code == 200 else r.text[:200],
        }
    except Exception as exc:  # noqa: BLE001
        ms = (time.perf_counter() - t0) * 1000
        return {
            "session_id": sid,
            "http": 0,
            "ms": round(ms, 1),
            "ok": False,
            "err": f"{type(exc).__name__}: {exc}"[:200],
        }


async def run_leg(n: int, base: str, key: str, stamp: str) -> dict:
    timeout = httpx.Timeout(60.0, connect=15.0)
    limits = httpx.Limits(max_connections=n, max_keepalive_connections=n)
    sids = [f"load-{n}-{stamp}-{i:03d}" for i in range(n)]
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        rows = await asyncio.gather(*[_one(client, base, key, sid) for sid in sids])
    ms = sorted(r["ms"] for r in rows)
    http_ok = sum(1 for r in rows if r["http"] == 200)
    http_5xx = sum(1 for r in rows if 500 <= r["http"] < 600)
    drops = sum(1 for r in rows if r["http"] in (0, 429, 502, 503, 504) or not r["ok"])
    return {
        "leg": n,
        "n": n,
        "http_200": http_ok,
        "http_5xx": http_5xx,
        "drops": drops,
        "p50_ms": round(_pct(ms, 50), 1),
        "p95_ms": round(_pct(ms, 95), 1),
        "mean_ms": round(statistics.mean(ms), 1) if ms else 0,
        "max_ms": round(max(ms), 1) if ms else 0,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leg", type=int, required=True, choices=(25, 50, 100))
    args = parser.parse_args()
    base = (os.getenv("LIVE_API_BASE_URL") or "").strip()
    key = (os.getenv("LIVE_CLIENT_B_KEY") or "").strip()
    if not base or not key:
        raise SystemExit("Set LIVE_API_BASE_URL and LIVE_CLIENT_B_KEY in .env")
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    print(f"leg={args.leg} base={base} stamp={stamp}", flush=True)
    summary = asyncio.run(run_leg(args.leg, base, key, stamp))
    out = {
        k: summary[k]
        for k in ("leg", "n", "http_200", "http_5xx", "drops", "p50_ms", "p95_ms", "mean_ms", "max_ms")
    }
    print(json.dumps(out), flush=True)
    os.makedirs("reports", exist_ok=True)
    path = os.path.join("reports", f"load_leg_{args.leg}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"summary": out, "rows": summary["rows"]}, f)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
