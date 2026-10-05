"""EC2 Instance Metadata Service (IMDSv2) mock and a spot-notice watcher.

The watcher reads exactly the endpoints a production handler reads on EC2, so the
same code runs against this mock locally and against the real IMDS when AWS FIS
(`aws:ec2:send-spot-instance-interruptions`) triggers a reclaim:

    PUT /latest/api/token                         (X-aws-ec2-metadata-token-ttl-seconds)
    GET /latest/meta-data/events/recommendations/rebalance   -> {"noticeTime": ...}
    GET /latest/meta-data/spot/instance-action               -> {"action", "time"}

Both GET paths return 404 until a signal exists, and 401 without a valid token.
Formats follow the EC2 user guide ("Spot Instance interruption notices", "EC2
instance rebalance recommendations").
"""

from __future__ import annotations

import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REAL_IMDS = "http://169.254.169.254"
TOKEN_PATH = "/latest/api/token"
REBALANCE_PATH = "/latest/meta-data/events/recommendations/rebalance"
ACTION_PATH = "/latest/meta-data/spot/instance-action"
TTL_HEADER = "X-aws-ec2-metadata-token-ttl-seconds"
TOKEN_HEADER = "X-aws-ec2-metadata-token"


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class MockIMDS:
    """In-process IMDSv2 mock. Schedule a reclaim, point a watcher at `base_url`."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self._tokens: dict[str, float] = {}
        self._rebalance_at: datetime | None = None
        self._action_at: datetime | None = None
        self._terminate_at: datetime | None = None
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> MockIMDS:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> MockIMDS:
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()

    def schedule_interruption(self, *, notice_s: float = 120.0, rebalance_lead_s: float = 0.0,
                              after_s: float = 0.0) -> datetime:
        """Emit a rebalance recommendation, then a terminate action `notice_s` before
        termination. Returns the termination time. AWS's notice is best-effort:
        notice_s=0 models a hard kill."""
        now = self.clock()
        with self._lock:
            self._action_at = now + timedelta(seconds=after_s + rebalance_lead_s)
            self._rebalance_at = now + timedelta(seconds=after_s) if rebalance_lead_s else None
            self._terminate_at = self._action_at + timedelta(seconds=notice_s)
        return self._terminate_at

    def _response(self, path: str) -> dict[str, str] | None:
        now = self.clock()
        with self._lock:
            if path == REBALANCE_PATH:
                rebalance = self._rebalance_at or self._action_at
                if rebalance and now >= rebalance:
                    return {"noticeTime": _iso(rebalance)}
            if path == ACTION_PATH and self._action_at and now >= self._action_at:
                return {"action": "terminate", "time": _iso(self._terminate_at)}
        return None

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def _send(self, status: int, body: str = "") -> None:
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_PUT(self) -> None:  # noqa: N802
                ttl = self.headers.get(TTL_HEADER)
                if self.path != TOKEN_PATH or not ttl or not ttl.isdigit():
                    self._send(400)
                    return
                token = secrets.token_urlsafe(24)
                mock._tokens[token] = time.monotonic() + int(ttl)
                self._send(200, token)

            def do_GET(self) -> None:  # noqa: N802
                token = self.headers.get(TOKEN_HEADER)
                if not token or mock._tokens.get(token, 0) < time.monotonic():
                    self._send(401)
                    return
                body = mock._response(self.path)
                if body is None:
                    self._send(404)
                else:
                    self._send(200, json.dumps(body))

        return Handler


@dataclass(frozen=True)
class Interruption:
    action: str
    terminate_at: datetime
    observed_at: datetime

    @property
    def notice_s(self) -> float:
        return (self.terminate_at - self.observed_at).total_seconds()


class NoticeWatcher:
    """Polls IMDS and fires callbacks once per signal. AWS suggests polling every 5 s;
    a shorter interval recovers more of the notice window."""

    def __init__(self, base_url: str = REAL_IMDS, *, poll_s: float = 1.0,
                 on_rebalance: Callable[[datetime], None] | None = None,
                 on_interruption: Callable[[Interruption], None] | None = None,
                 token_ttl_s: int = 21_600, timeout_s: float = 1.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.poll_s = poll_s
        self.on_rebalance = on_rebalance
        self.on_interruption = on_interruption
        self.token_ttl_s = token_ttl_s
        self.timeout_s = timeout_s
        self._token: str | None = None
        self._token_expiry = 0.0
        self._seen_rebalance = False
        self._seen_action = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _fetch_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry - 60:
            return self._token
        request = urllib.request.Request(self.base_url + TOKEN_PATH, method="PUT",
                                         headers={TTL_HEADER: str(self.token_ttl_s)})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            self._token = response.read().decode()
        self._token_expiry = time.monotonic() + self.token_ttl_s
        return self._token

    def _get(self, path: str) -> dict | None:
        request = urllib.request.Request(self.base_url + path,
                                         headers={TOKEN_HEADER: self._fetch_token()})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code == 401:
                self._token = None  # expired or rotated: fetch a new token next poll
                return None
            raise

    def poll_once(self) -> None:
        if not self._seen_rebalance:
            body = self._get(REBALANCE_PATH)
            if body:
                self._seen_rebalance = True
                if self.on_rebalance:
                    self.on_rebalance(parse_iso(body["noticeTime"]))
        if not self._seen_action:
            body = self._get(ACTION_PATH)
            if body:
                self._seen_action = True
                if self.on_interruption:
                    self.on_interruption(Interruption(body["action"], parse_iso(body["time"]),
                                                      datetime.now(UTC)))

    def start(self) -> NoticeWatcher:
        def loop() -> None:
            while not self._stop.is_set() and not self._seen_action:
                try:
                    self.poll_once()
                except (urllib.error.URLError, TimeoutError, OSError):
                    pass  # IMDS hiccup: keep polling
                self._stop.wait(self.poll_s)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
