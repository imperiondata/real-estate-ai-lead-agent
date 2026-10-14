"""P1 MIG01 — migrate_db is one transaction and never prints the URL."""
from pathlib import Path

import migrate_db

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "migrate_db.py").read_text(encoding="utf-8")


class FakeCursor:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.n = 0

    def execute(self, query):
        self.n += 1
        if self.fail_on and self.n == self.fail_on:
            raise RuntimeError("boom")

    def close(self):
        pass


class FakeConn:
    def __init__(self, fail_on=None):
        self.autocommit = True
        self.committed = False
        self.rolled_back = False
        self.cursor_obj = FakeCursor(fail_on)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_failure_rolls_back_and_does_not_commit():
    conn = FakeConn(fail_on=2)
    assert migrate_db.run_migration(conn) == 1
    assert conn.committed is False
    assert conn.rolled_back is True
    assert conn.autocommit is False


def test_success_commits():
    conn = FakeConn()
    assert migrate_db.run_migration(conn) == 0
    assert conn.committed is True
    assert conn.rolled_back is False
    assert conn.cursor_obj.n == len(migrate_db.MIGRATIONS)


def test_source_is_transactional_and_does_not_print_url():
    assert "autocommit = True" not in SRC
    assert "sys.exit(run_migration())" in SRC
    for line in SRC.splitlines():
        if "print(" in line:
            assert "settings.DATABASE_URL" not in line
