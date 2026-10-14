"""P1 REL02 — one Redis lease per scheduler job. No live Redis."""
from pathlib import Path

from app.scheduler_lease import leased, run_with_lease

REPO = Path(__file__).resolve().parent.parent
MAIN = (REPO / "main.py").read_text(encoding="utf-8")

JOBS = {
    "follow_up_checker": 50,
    "escalation_checker": 50,
    "crm_resync": 240,
    "expire_approvals": 840,
    "competitor_monitor": 3600,
    "nightly_backup": 3600,
    "nightly_cleanup": 3600,
    "weekly_marketing_report": 3600,
}


class FakeRedis:
    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def set(self, key, value, nx=False, ex=None):
        self.calls.append((key, value, nx, ex))
        if self.error:
            raise self.error
        return self.result


def test_lease_held_skips_job():
    called = []
    client = FakeRedis(result=None)
    assert run_with_lease("follow_up_checker", 50, lambda: called.append(1), client=client) is None
    assert called == []
    assert client.calls[0][0] == "scheduler_lease:follow_up_checker"
    assert client.calls[0][2] is True
    assert client.calls[0][3] == 50


def test_lease_won_runs_job():
    client = FakeRedis(result=True)
    assert run_with_lease("crm_resync", 240, lambda: "ok", client=client) == "ok"


def test_redis_error_skips_job():
    called = []
    client = FakeRedis(error=ConnectionError("down"))
    assert run_with_lease("nightly_backup", 3600, lambda: called.append(1), client=client) is None
    assert called == []


def test_missing_url_skips_job(monkeypatch):
    called = []
    monkeypatch.setattr("app.scheduler_lease.settings.REDIS_URL", "")
    assert run_with_lease("escalation_checker", 50, lambda: called.append(1)) is None
    assert called == []


def test_leased_wrapper_passes_args():
    seen = {}

    def job(hours):
        seen["hours"] = hours
        return hours

    client = FakeRedis(result=True)
    wrapped = leased("expire_approvals", 840, job)

    def run(fn):
        return fn()

    original = run_with_lease

    def fake(job_id, lease_seconds, fn, client=None):
        seen["job_id"] = job_id
        seen["lease"] = lease_seconds
        return fn()

    import app.scheduler_lease as mod
    mod.run_with_lease = fake
    try:
        assert wrapped(24) == 24
    finally:
        mod.run_with_lease = original
    assert seen == {"job_id": "expire_approvals", "lease": 840, "hours": 24}


def test_all_scheduler_jobs_are_leased():
    lines = [ln.strip() for ln in MAIN.splitlines() if "scheduler.add_job(" in ln]
    assert len(lines) == 8
    assert all(ln.startswith("scheduler.add_job(leased(") for ln in lines)
    for job_id, seconds in JOBS.items():
        assert f'leased("{job_id}", {seconds},' in MAIN
