"""Spot-notice handler: log the signal timeline, pause vLLM admission, start evacuation.

On a rebalance recommendation it only logs (the signal is best-effort and often not
followed by a reclaim). On an interruption notice it:

1. pauses the vLLM engine with ``POST /pause?mode=wait&clear_cache=false``. "wait"
   keeps in-flight requests decoding while new ones queue, and ``clear_cache=false``
   is essential: the endpoint's default clears the KV/prefix cache, which is the
   state we are about to evacuate. The endpoint is under vLLM's dev routes
   (``vllm/entrypoints/serve/dev/rlhf/api_router.py``), so the server must run with
   development endpoints enabled;
2. calls the evacuation hook with the termination deadline (Phase 3 wires this to
   ``kvevac.planner`` + ``kvevac.flush`` + the tiering manager).

Every step is appended to a JSONL timeline. Run without a vLLM URL, this is the
notice-timing logger for FIS experiments (docs/calibration.md).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from kvevac.notice.imds import REAL_IMDS, Interruption, NoticeWatcher

PAUSE_PATH = "/pause?mode=wait&clear_cache=false"
EvacuationHook = Callable[[datetime], None]


class SpotNoticeHandler:
    def __init__(self, *, imds_url: str = REAL_IMDS, vllm_url: str | None = None,
                 on_evacuate: EvacuationHook | None = None, log_path: Path | None = None,
                 poll_s: float = 1.0, timeout_s: float = 5.0) -> None:
        self.vllm_url = vllm_url.rstrip("/") if vllm_url else None
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
    args = parser.parse_args()
    handler = SpotNoticeHandler(imds_url=args.imds_url, vllm_url=args.vllm_url,
                                log_path=args.log, poll_s=args.poll_s).start()
    handler.interrupted.wait()
    handler.stop()


if __name__ == "__main__":
    main()
