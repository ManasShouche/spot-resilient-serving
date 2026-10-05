import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kvevac.measure.notice_timing import parse, timing
from kvevac.notice.imds import MockIMDS

LOGGER = Path(__file__).resolve().parents[1] / "jobs" / "aws_fis" / "notice_logger.py"


def test_timing_from_console_text_with_noise() -> None:
    text = "\n".join([
        "[   12.3] cloud-init: boot",
        'KVEVAC {"event": "watching", "at": "2026-10-05T10:00:00+00:00"}',
        'KVEVAC {"event": "rebalance", "at": "2026-10-05T10:00:10+00:00", '
        '"body": {"noticeTime": "2026-10-05T10:00:09Z"}}',
        'KVEVAC {"event": "interruption", "at": "2026-10-05T10:00:40+00:00", '
        '"body": {"action": "terminate", "time": "2026-10-05T10:02:40Z"}}',
        'KVEVAC {"event": "heartbeat", "at": "2026-10-05T10:02:37+00:00", "n": 1}',
        'KVEVAC {"event": "heartb',  # truncated line
    ])
    result = timing(parse(text))
    assert result["rebalance_lead_s"] == 30.0
    assert result["announced_notice_s"] == 120.0
    assert result["observed_lifetime_after_notice_s"] == 117.0
    assert result["termination_vs_announced_s"] == -3.0


def test_timing_requires_an_interruption() -> None:
    with pytest.raises(ValueError):
        timing(parse('KVEVAC {"event": "watching", "at": "2026-10-05T10:00:00+00:00"}'))


def test_standalone_logger_against_imds_mock() -> None:
    with MockIMDS() as imds:
        proc = subprocess.Popen([sys.executable, str(LOGGER)], stdout=subprocess.PIPE,
                                text=True, env={**os.environ, "KVEVAC_IMDS": imds.base_url})
        imds.schedule_interruption(notice_s=120, rebalance_lead_s=1.0, after_s=0.5)
        time.sleep(4.0)
        proc.terminate()
        out, _ = proc.communicate(timeout=10)
    result = timing(parse(out))
    assert result["action"] == "terminate"
    assert 0.0 <= result["rebalance_lead_s"] <= 2.5
    assert 115 <= result["announced_notice_s"] <= 121
    assert result["heartbeats"] >= 2
