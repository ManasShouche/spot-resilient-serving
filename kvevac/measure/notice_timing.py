"""Turn spot-notice logger output (EC2 console text) into timing measurements.

Input: text containing lines `KVEVAC {json}` from jobs/aws_fis/notice_logger.py, e.g.
`aws ec2 get-console-output --latest --instance-id i-... --output text`.

Reported per run:
- rebalance_lead_s: rebalance recommendation observed -> interruption notice observed
- announced_notice_s: interruption notice observed -> termination time it announced
- observed_lifetime_after_notice_s: notice observed -> last heartbeat (a lower bound on
  how long the instance really kept running)
- termination_vs_announced_s: last heartbeat - announced termination (negative means
  the instance died earlier than announced, which the hard-kill column of the regime map
  cares about)

    python -m kvevac.measure.notice_timing console.txt [more.txt ...]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def parse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        index = line.find("KVEVAC {")
        if index < 0:
            continue
        try:
            events.append(json.loads(line[index + len("KVEVAC "):]))
        except json.JSONDecodeError:
            continue  # console lines can be truncated or interleaved
    return events


def timing(events: list[dict]) -> dict:
    first = {}
    for event in events:
        first.setdefault(event["event"], event)
    beats = [e for e in events if e["event"] == "heartbeat"]
    if "interruption" not in first:
        raise ValueError("no interruption notice in the log")
    notice_at = _ts(first["interruption"]["at"])
    announced = _ts(first["interruption"]["body"]["time"])
    result = {
        "action": first["interruption"]["body"].get("action"),
        "announced_notice_s": round((announced - notice_at).total_seconds(), 2),
        "rebalance_lead_s": None,
        "observed_lifetime_after_notice_s": None,
        "termination_vs_announced_s": None,
        "heartbeats": len(beats),
    }
    if "rebalance" in first:
        result["rebalance_lead_s"] = round(
            (notice_at - _ts(first["rebalance"]["at"])).total_seconds(), 2)
    if beats:
        last = _ts(beats[-1]["at"])
        result["observed_lifetime_after_notice_s"] = round((last - notice_at).total_seconds(), 2)
        result["termination_vs_announced_s"] = round((last - announced).total_seconds(), 2)
    return result


def main() -> None:
    rows = [{"file": path, **timing(parse(Path(path).read_text()))} for path in sys.argv[1:]]
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
