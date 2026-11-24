"""Local SMTP and HTTP receipt proof for tenant delivery.

Binds listeners on 127.0.0.1 only. Creates and deletes its own rows. Does not
read LIVE_DATABASE_URL, does not open Render, and does not print WIDGET_API_KEY
or frontend/.env.local.

TEST_MODE is forced false for this process. A recorded event_logs row is not
this proof.
"""

from __future__ import annotations

import hashlib
import socket
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Client, EventLog, Lead  # noqa: E402
from models import Session as SessionModel  # noqa: E402

LOG_PATH = ROOT / "plans" / "evidence" / "TENANT_DELIVERY_LOCAL.log"
FRONTEND_SRC = ROOT / "frontend" / "src"
ROUTE = FRONTEND_SRC / "app" / "api" / "chat" / "route.ts"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class ProofError(RuntimeError):
    pass


class ReceiptSink:
    def __init__(self) -> None:
        self.smtp: list[dict] = []
        self.http: list[dict] = []
        self.lock = threading.Lock()

    def add_smtp(self, code: int, body: bytes) -> None:
        with self.lock:
            self.smtp.append(
                {
                    "attempt": len(self.smtp) + 1,
                    "code": code,
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )

    def add_http(self, status: int, body: bytes) -> None:
        with self.lock:
            self.http.append(
                {
                    "attempt": len(self.http) + 1,
                    "status": status,
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )


def _refuse_nonlocal(host: str) -> None:
    if host not in LOOPBACK:
        raise ProofError(f"refusing non-loopback host {host or 'unknown'}")


def _widget_key_absent() -> bool:
    """True when the key name is only in the server route. Does not read .env.local."""
    if not ROUTE.is_file():
        return False
    route_text = ROUTE.read_text(encoding="utf-8")
    if "use client" in route_text or "NEXT_PUBLIC_WIDGET_API_KEY" in route_text:
        return False
    if "process.env.WIDGET_API_KEY" not in route_text:
        return False
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "NEXT_PUBLIC_WIDGET_API_KEY" in text:
            return False
        if "WIDGET_API_KEY" in text and path.resolve() != ROUTE.resolve():
            return False
        if "WIDGET_API_KEY" in text and "use client" in text:
            return False
    return True


def _handle_smtp(conn: socket.socket, sink: ReceiptSink) -> None:
    peer = conn.getpeername()[0]
    _refuse_nonlocal(peer)
    conn.sendall(b"220 localhost proof\r\n")
    while True:
        line = _readline(conn)
        if not line:
            return
        command = line.decode("utf-8", "replace").strip().upper()
        if command.startswith("EHLO") or command.startswith("HELO"):
            conn.sendall(b"250 localhost\r\n")
        elif command.startswith("MAIL FROM") or command.startswith("RCPT TO"):
            conn.sendall(b"250 OK\r\n")
        elif command == "DATA":
            conn.sendall(b"354 end data with <CR><LF>.<CR><LF>\r\n")
            body = _read_data(conn)
            with sink.lock:
                attempt = len(sink.smtp) + 1
            code = 451 if attempt == 1 else 250
            sink.add_smtp(code, body)
            if code == 451:
                conn.sendall(b"451 4.3.0 transient\r\n")
            else:
                conn.sendall(b"250 queued\r\n")
        elif command == "RSET":
            conn.sendall(b"250 OK\r\n")
        elif command == "QUIT":
            conn.sendall(b"221 bye\r\n")
            return
        elif command == "NOOP":
            conn.sendall(b"250 OK\r\n")
        else:
            conn.sendall(b"502 command not implemented\r\n")


def _readline(conn: socket.socket) -> bytes:
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(1)
        if not chunk:
            break
        data += chunk
    return data


def _read_data(conn: socket.socket) -> bytes:
    body = b""
    while True:
        line = _readline(conn)
        if not line or line in (b".\r\n", b".\n"):
            break
        body += line
    return body


def _serve_smtp(sock: socket.socket, sink: ReceiptSink, stop: threading.Event) -> None:
    sock.settimeout(0.2)
    while not stop.is_set():
        try:
            conn, _addr = sock.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        try:
            _handle_smtp(conn, sink)
        except ProofError:
            pass
        finally:
            conn.close()


class _WebhookHandler(BaseHTTPRequestHandler):
    sink: ReceiptSink

    def do_POST(self) -> None:  # noqa: N802
        peer = self.client_address[0]
        if peer not in LOOPBACK:
            self.send_response(403)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        with self.sink.lock:
            attempt = len(self.sink.http) + 1
        status = 503 if attempt == 1 else 200
        self.sink.add_http(status, body)
        payload = b"transient" if status == 503 else b"ok"
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args) -> None:
        return


def _start_listeners(sink: ReceiptSink):
    smtp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    smtp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    smtp_sock.bind(("127.0.0.1", 0))
    smtp_sock.listen(8)
    smtp_host, smtp_port = smtp_sock.getsockname()
    _refuse_nonlocal(smtp_host)
    stop = threading.Event()
    smtp_thread = threading.Thread(
        target=_serve_smtp, args=(smtp_sock, sink, stop), daemon=True
    )
    smtp_thread.start()

    _WebhookHandler.sink = sink
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _WebhookHandler)
    http_host, http_port = httpd.server_address
    _refuse_nonlocal(http_host)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()
    return smtp_sock, smtp_port, stop, httpd, http_port


def _client(db, webhook_url: str) -> Client:
    suffix = uuid.uuid4().hex
    client = Client(
        company_name=f"Delivery proof {suffix[:8]}",
        email=f"proof-{suffix}@delivery.test",
        hashed_password="not-used",
        api_key=f"delivery-proof-{suffix}",
        is_api_key_hashed=True,
        is_active=True,
        settings={
            "notify_email": "proof-inbox@delivery.test",
            "webhook_url": webhook_url,
        },
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def _wipe(db, client_id: int | None) -> None:
    try:
        db.rollback()
        if client_id is not None:
            db.query(EventLog).filter(EventLog.client_id == client_id).delete(
                synchronize_session=False
            )
            db.query(Lead).filter(Lead.client_id == client_id).delete(
                synchronize_session=False
            )
            db.query(SessionModel).filter(SessionModel.client_id == client_id).delete(
                synchronize_session=False
            )
            db.query(Client).filter(Client.id == client_id).delete(
                synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


def _write_log(lines: list[str]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parsed = urlparse(settings.DATABASE_URL or "")
    if (parsed.hostname or "").lower() not in LOOPBACK:
        raise ProofError("refusing a non-loopback DATABASE_URL")
    if "render" in (parsed.hostname or "").lower():
        raise ProofError("refusing Render")

    sink = ReceiptSink()
    smtp_sock, smtp_port, stop, httpd, http_port = _start_listeners(sink)
    previous = {
        "TEST_MODE": settings.TEST_MODE,
        "SMTP_HOST": settings.SMTP_HOST,
        "SMTP_PORT": settings.SMTP_PORT,
        "SMTP_USER": settings.SMTP_USER,
        "SMTP_PASS": settings.SMTP_PASS,
    }
    settings.TEST_MODE = False
    settings.SMTP_HOST = "127.0.0.1"
    settings.SMTP_PORT = smtp_port
    settings.SMTP_USER = "proof@localhost"
    settings.SMTP_PASS = "local-proof-not-a-secret"

    db = None
    client_id = None
    lines = [
        "TENANT_DELIVERY_LOCAL_START",
        "staging_claim=false",
        "render_used=false",
        "live_database_used=false",
        "test_mode=false",
        f"smtp_bind=127.0.0.1:{smtp_port}",
        f"http_bind=127.0.0.1:{http_port}",
    ]
    try:
        db = SessionLocal()
        from app.services.tenant_delivery import deliver_tenant_lead

        webhook_url = f"http://127.0.0.1:{http_port}/hook"
        _refuse_nonlocal(urlparse(webhook_url).hostname or "")
        client = _client(db, webhook_url)
        client_id = client.id
        session = SessionModel(
            id=f"{client.id}_delivery-proof-{uuid.uuid4().hex}",
            client_id=client.id,
        )
        db.add(session)
        db.commit()
        lead = Lead(
            session_id=session.id,
            client_id=client.id,
            name="Proof Lead",
            phone="9000000001",
            location="Baner",
            budget="50L",
        )
        db.add(lead)
        db.commit()

        first = deliver_tenant_lead(db, client, lead, session.id)
        if first != ["tenant_email", "tenant_webhook"]:
            raise ProofError(f"first delivery returned {first}")
        if [item["code"] for item in sink.smtp] != [451, 250]:
            raise ProofError(f"smtp receipts {sink.smtp}")
        if [item["status"] for item in sink.http] != [503, 200]:
            raise ProofError(f"http receipts {sink.http}")
        if not sink.smtp[1]["sha256"] or not sink.http[1]["sha256"]:
            raise ProofError("listener did not capture a body")

        smtp_before = len(sink.smtp)
        http_before = len(sink.http)
        second = deliver_tenant_lead(db, client, lead, session.id)
        replay_smtp = len(sink.smtp) - smtp_before
        replay_http = len(sink.http) - http_before
        if second != [] or replay_smtp or replay_http:
            raise ProofError(
                f"replay sent again second={second} smtp={replay_smtp} http={replay_http}"
            )

        key_absent = _widget_key_absent()
        if not key_absent:
            raise ProofError("WIDGET_API_KEY is not server-only")

        for item in sink.smtp:
            lines.append(f"SMTP_RECEIPT attempt={item['attempt']} code={item['code']}")
        for item in sink.http:
            lines.append(
                f"HTTP_RECEIPT attempt={item['attempt']} status={item['status']}"
            )
        lines.extend(
            [
                f"replay_smtp_receipts={replay_smtp}",
                f"replay_http_receipts={replay_http}",
                "replay_receipts=0",
                "key_absent_from_client=true",
                "TENANT_DELIVERY_LOCAL_PASS",
            ]
        )
        _write_log(lines)
        print("\n".join(lines))
        return 0
    except Exception as exc:
        lines.append(f"TENANT_DELIVERY_LOCAL_FAIL error={type(exc).__name__}")
        _write_log(lines)
        print("\n".join(lines), file=sys.stderr)
        return 1
    finally:
        settings.TEST_MODE = previous["TEST_MODE"]
        settings.SMTP_HOST = previous["SMTP_HOST"]
        settings.SMTP_PORT = previous["SMTP_PORT"]
        settings.SMTP_USER = previous["SMTP_USER"]
        settings.SMTP_PASS = previous["SMTP_PASS"]
        if db is not None:
            _wipe(db, client_id)
        stop.set()
        httpd.shutdown()
        smtp_sock.close()


if __name__ == "__main__":
    sys.exit(main())
