import os
import random
import subprocess
import sys
from pathlib import Path

from kvevac.measure.console_channel import GAP_MARKER, decode, encode, merge, send

MODULE = Path(__file__).resolve().parents[1] / "kvevac" / "measure" / "console_channel.py"


def _payload(size: int = 5000) -> bytes:
    return random.Random(7).randbytes(size)


def _snapshots(text: str, window: int, step: int) -> list[str]:
    """`--latest`-style views: the last `window` characters at each point in time."""
    return [text[max(0, end - window):end] for end in range(step, len(text) + step, step)]


def test_roundtrip_with_console_noise() -> None:
    payload = _payload()
    lines = encode(payload, "run1")
    noise = [f"[ {i}.000] kernel: something" for i in range(len(lines))]
    text = "\n".join(x for pair in zip(noise, lines, strict=True) for x in pair)
    status = decode(text)
    assert status["complete"] and status["payload"] == payload and status["name"] == "run1"


def test_merge_of_overlapping_windows_reconstructs_the_stream() -> None:
    payload = _payload(20_000)
    stream = "\n".join(["boot noise"] * 50 + encode(payload, "run1") + ["after"] * 10)
    transcript = ""
    for snapshot in _snapshots(stream, window=4096, step=1500):
        transcript, gap = merge(transcript, snapshot)
        assert not gap
    assert transcript == stream
    assert decode(transcript)["payload"] == payload


def test_repeated_identical_snapshot_is_a_no_op() -> None:
    once, gap = merge("", "abc\ndef\n")
    twice, gap2 = merge(once, "abc\ndef\n")
    assert once == twice == "abc\ndef\n" and not gap and not gap2
    # An older, shorter window (e.g. buffered output after termination) adds nothing.
    assert merge(twice, "def\n") == (twice, False)


def test_short_transcript_that_is_a_prefix_of_the_snapshot() -> None:
    assert merge("abc", "abcdef") == ("abcdef", False)


def test_gap_is_reported_and_later_copy_fills_missing_chunks() -> None:
    payload = _payload(8000)
    lines = encode(payload, "run1")
    first = "\n".join(lines[:5]) + "\n"
    transcript, _ = merge("", first)
    # Polling missed the rest of the first copy; the next window starts elsewhere.
    late = "\n".join(lines) + "\n"
    transcript, gap = merge(transcript, "unrelated line\n" + late)
    assert gap and GAP_MARKER in transcript
    assert decode(transcript)["payload"] == payload


def test_corrupted_chunk_is_dropped_then_recovered_from_resend() -> None:
    payload = _payload()
    lines = encode(payload, "run1")
    bad = list(lines)
    data = bad[3].rsplit(" ", 1)
    bad[3] = data[0] + " " + data[1][:100] + "[ 9.9] kernel msg" + data[1][100:]
    status = decode("\n".join(bad))
    assert not status["complete"] and status["missing"] == [2]
    assert decode("\n".join(bad + lines))["payload"] == payload


def test_newest_result_wins() -> None:
    old, new = _payload(1000), _payload(1200)
    text = "\n".join(encode(old, "a") + encode(new, "b"))
    status = decode(text)
    assert status["name"] == "b" and status["payload"] == new


def test_truncated_tail_line_is_ignored() -> None:
    payload = _payload()
    lines = encode(payload, "run1")
    text = "\n".join(lines[:-2]) + "\n" + lines[-2][:40]
    status = decode(text)
    assert not status["complete"] and status["missing"] == [len(lines) - 3]


def test_send_writes_to_console_file(tmp_path: Path) -> None:
    console = tmp_path / "console"
    send(b"hello", "x", str(console))
    assert decode(console.read_text())["payload"] == b"hello"


def test_cli_roundtrip(tmp_path: Path) -> None:
    payload = _payload(3000)
    (tmp_path / "in.bin").write_bytes(payload)
    console, transcript = tmp_path / "console", tmp_path / "transcript"
    run = [sys.executable, str(MODULE)]
    env = {**os.environ, "PYTHONPATH": ""}
    subprocess.run(run + ["send", "--file", str(tmp_path / "in.bin"), "--name", "r",
                          "--console", str(console)], check=True, env=env)
    text = console.read_text()
    for i, snapshot in enumerate(_snapshots(text, window=2000, step=700)):
        # As printed by `aws ... --output text`, which appends a newline.
        (tmp_path / f"s{i}").write_text(snapshot + "\n")
        subprocess.run(run + ["merge", str(transcript), str(tmp_path / f"s{i}"), "--cli-text"],
                       check=True, env=env, capture_output=True)
    done = subprocess.run(run + ["decode", str(transcript), "--out", str(tmp_path / "out")],
                          env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
    assert (tmp_path / "out").read_bytes() == payload
    assert transcript.read_text() == text
