"""WIDGET_API_KEY stays on the server. No database. No secret values printed."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"
ROUTE = FRONTEND_SRC / "app" / "api" / "chat" / "route.ts"
KEY_NAME = "WIDGET_API_KEY"
PUBLIC_KEY_NAME = "NEXT_PUBLIC_WIDGET_API_KEY"


def _source_files():
    return [
        path
        for path in FRONTEND_SRC.rglob("*")
        if path.suffix in {".ts", ".tsx", ".js", ".jsx"} and path.is_file()
    ]


def test_widget_api_key_is_server_only():
    assert ROUTE.is_file()
    route_text = ROUTE.read_text(encoding="utf-8")
    assert "use client" not in route_text
    assert f"process.env.{KEY_NAME}" in route_text
    assert PUBLIC_KEY_NAME not in route_text
    assert f"NEXT_PUBLIC_{KEY_NAME}" not in route_text

    offenders = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        if PUBLIC_KEY_NAME in text or f"NEXT_PUBLIC_{KEY_NAME}" in text:
            offenders.append(path.relative_to(ROOT).as_posix())
            continue
        if KEY_NAME in text and path.resolve() != ROUTE.resolve():
            offenders.append(path.relative_to(ROOT).as_posix())
        if KEY_NAME in text and "use client" in text:
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []
