"""Spot-notice handler: log the signal timeline, pause vLLM admission, start evacuation.

On a rebalance recommendation it only logs (the signal is best-effort and often not
followed by a reclaim). On an interruption notice it:

1. pauses the vLLM engine with ``POST /pause?mode=wait&clear_cache=false``. "wait"
   keeps in-flight requests decoding while new ones queue, and ``clear_cache=false``
   is essential: the endpoint's default clears the KV/prefix cache, which is the
   state we are about to evacuate. The endpoint is under vLLM's dev routes
   (``vllm/entrypoints/serve/dev/rlhf/api_router.py``), so the server must run with
   development endpoints enabled;
2. calls the evacuation hook with the termination deadline.

With ``flush_control`` set (Phase 3), it first asks the vLLM plugin
(``kvevac.vllm_plugin``) to flush: it atomically writes a flush request to the
plugin's control file, optionally sends a one-token ``wake_model`` request so an
idle scheduler takes a step and sees it, and only then pauses admission. The plugin
answers in ``<control>.status``, which is copied into the timeline.

Every step is appended to a JSONL timeline. Run without a vLLM URL, this is the
notice-timing logger for FIS experiments (docs/calibration.md).
"""

from __future__ import annotations

import itertools
import json
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from kvevac.notice.imds import REAL_IMDS, Interruption, NoticeWatcher
from kvevac.vllm_plugin.core import FlushRequest, write_flush_request

PAUSE_PATH = "/pause?mode=wait&clear_cache=false"
EvacuationHook = Callable[[datetime], None]


class SpotNoticeHandler:
    def __init__(self, *, imds_url: str = REAL_IMDS, vllm_url: str | None = None,
                 on_evacuate: EvacuationHook | None = None, log_path: Path | None = None,
                 poll_s: float = 1.0, timeout_s: float = 5.0,
                 flush_control: Path | None = None, wake_model: str | None = None) -> None:
        self.vllm_url = vllm_url.rstrip("/") if vllm_url else None
        self.flush_control = flush_control
        self.wake_model = wake_model
        self._flush_seq = itertools.count(int(time.time()))
        self.on_evacuate = on_evacuate
        self.log_path = log_path
        self.timeout_s = timeout_s
        self.timeline: list[dict] = []
        self.interrupted = threading.Event()
        self._lock = threading.Lock()
        self.watcher = NoticeWatcher(imds_url, poll_s=poll_s, on_rebalance=self._rebalance,
                                     on_interruption=self._interruption)

    def _log(self, event: str, **fields: object) -> None:
        record = {"event": event, "at": datetime.now(UTC).isoformat(),
                  "monotonic": time.monotonic(), **fields}
        with self._lock:
            self.timeline.append(record)
            if self.log_path:
                with self.log_path.open("a") as handle:
                    handle.write(json.dumps(record, default=str) + "\n")

    def _rebalance(self, notice_time: datetime) -> None:
        self._log("rebalance_recommendation", notice_time=notice_time.isoformat())

    def _interruption(self, interruption: Interruption) -> None:
        self._log("interruption_notice", action=interruption.action,
                  terminate_at=interruption.terminate_at.isoformat(),
                  notice_s=round(interruption.notice_s, 3))
        if self.flush_control:
            self._request_flush(interruption.terminate_at)
        if self.vllm_url:
            started = time.monotonic()
            try:
                request = urllib.request.Request(self.vllm_url + PAUSE_PATH, data=b"",
                                                 method="POST")
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    status = response.status
                self._log("vllm_paused", status=status,
                          latency_s=round(time.monotonic() - started, 4))
            except OSError as error:  # keep going: evacuation may still help
                self._log("vllm_pause_failed", error=str(error))
        if self.on_evacuate:
            self._log("evacuation_started")
            self.on_evacuate(interruption.terminate_at)
            self._log("evacuation_returned")
        self.interrupted.set()

    def _request_flush(self, terminate_at: datetime) -> None:
        request = FlushRequest(seq=next(self._flush_seq),
                               deadline_unix=terminate_at.timestamp())
        assert self.flush_control is not None
        write_flush_request(self.flush_control, request)
        self._log("flush_requested", seq=request.seq, control=str(self.flush_control))
        if self.vllm_url and self.wake_model:
            body = json.dumps({"model": self.wake_model, "prompt": "w", "max_tokens": 1})
            try:
                wake = urllib.request.Request(self.vllm_url + "/v1/completions",
                                              data=body.encode(), method="POST",
                                              headers={"Content-Type": "application/json"})
                urllib.request.urlopen(wake, timeout=self.timeout_s).close()
                self._log("scheduler_woken")
            except OSError as error:
                self._log("scheduler_wake_failed", error=str(error))

    def flush_status(self) -> dict | None:
        """The plugin's latest report, if it has written one."""
        if not self.flush_control:
            return None
        try:
            return json.loads(self.flush_control.with_suffix(
                self.flush_control.suffix + ".status").read_text())
        except (OSError, ValueError):
            return None

    def start(self) -> SpotNoticeHandler:
        self._log("watching")
        self.watcher.start()
        return self

    def stop(self) -> None:
        self.watcher.stop()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--imds-url", default=REAL_IMDS)
    parser.add_argument("--vllm-url")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--poll-s", type=float, default=1.0)
    parser.add_argument("--flush-control", type=Path,
                        help="control file of the kvevac vLLM plugin (Phase 3)")
    parser.add_argument("--wake-model", help="model name for a 1-token wake-up request")
    args = parser.parse_args()
    handler = SpotNoticeHandler(imds_url=args.imds_url, vllm_url=args.vllm_url,
                                log_path=args.log, poll_s=args.poll_s,
                                flush_control=args.flush_control,
                                wake_model=args.wake_model).start()
    handler.interrupted.wait()
    # Record what the plugin reports until the node goes away.
    last = None
    while handler.flush_control:
        status = handler.flush_status()
        if status and status != last:
            handler._log("flush_status", **status)
            last = status
            if status.get("finished_unix"):
                break
        time.sleep(1.0)
    handler.stop()


if __name__ == "__main__":
    main()
