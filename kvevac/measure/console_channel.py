"""Move a results file off an EC2 instance through its serial console.

The instance has no credentials, SSH, or S3 access, so results travel the same way the
spot-notice log does: as text lines on the serial console, read back with
`aws ec2 get-console-output --latest`. That call returns only the most recent 64 KB, so
the reader polls, merges overlapping snapshots into one transcript, and reassembles the
file from numbered chunks that each carry a checksum.

Wire format (one line each, anywhere in the console text):

    KVEVAC-RESULT <id> <name> <chunks> <bytes> <sha256>
    KVEVAC-CHUNK <id> <index> <chunks> <sha256[:12] of data> <base64 data>
    KVEVAC-END <id>

`<id>` is the first 12 hex digits of the file's SHA-256, so a re-sent copy of the same
file reuses chunks from earlier copies, and corrupted lines (the kernel can interleave
its own messages mid-line) are dropped and recovered from a later copy.

Instance side:
    python3 console_channel.py send --file results.tgz --name run1 --console /dev/ttyS0
Reader side:
    aws ec2 get-console-output --latest --instance-id i-... --query Output \
        --output text > snapshot.txt
    python3 console_channel.py merge console.txt snapshot.txt --cli-text
    python3 console_channel.py decode console.txt --out results.tgz

Stdlib only, and Python 3.9 compatible (AWS CloudShell runs this).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

CHUNK_CHARS = 512
GAP_MARKER = "\n[kvevac: console gap, output was lost here]\n"
_PROBE = 256  # characters of a new snapshot used to locate it in the transcript

_RESULT = re.compile(r"KVEVAC-RESULT ([0-9a-f]{12}) (\S+) (\d+) (\d+) ([0-9a-f]{64})")
_CHUNK = re.compile(r"KVEVAC-CHUNK ([0-9a-f]{12}) (\d+) (\d+) ([0-9a-f]{12}) ([A-Za-z0-9+/=]+)")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(payload: bytes, name: str, width: int = CHUNK_CHARS) -> list[str]:
    """Lines that carry `payload` over the console (header, chunks, end marker)."""
    digest = _sha(payload)
    ident = digest[:12]
    text = base64.b64encode(payload).decode()
    parts = [text[i:i + width] for i in range(0, len(text), width)] or [""]
    lines = [f"KVEVAC-RESULT {ident} {name} {len(parts)} {len(payload)} {digest}"]
    for index, part in enumerate(parts):
        lines.append(f"KVEVAC-CHUNK {ident} {index} {len(parts)} "
                     f"{_sha(part.encode())[:12]} {part}")
    lines.append(f"KVEVAC-END {ident}")
    return lines


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def merge(transcript: str, snapshot: str) -> tuple[str, bool]:
    """Append the part of `snapshot` that `transcript` does not have yet.

    A `--latest` snapshot is a window ending at the newest output, so it normally starts
    somewhere inside the transcript's tail. Returns (new transcript, gap), where gap
    means the snapshot did not overlap at all and output between them was lost.
    """
    snapshot = _normalize(snapshot)
    if not snapshot or snapshot in transcript:
        return transcript, False
    if not transcript:
        return snapshot, False
    # Find the earliest start position p in the transcript's tail such that the
    # transcript from p on is a prefix of the snapshot (largest overlap wins).
    start = max(0, len(transcript) - len(snapshot))
    probe = snapshot[:_PROBE]
    position = transcript.find(probe, start)
    while position >= 0:
        if snapshot.startswith(transcript[position:]):
            return transcript + snapshot[len(transcript) - position:], False
        position = transcript.find(probe, position + 1)
    # Overlap shorter than the probe: check suffix/prefix lengths directly.
    for size in range(min(len(probe), len(transcript)), 0, -1):
        if transcript.endswith(snapshot[:size]):
            # A few characters in common is coincidence, not overlap.
            gap = size < min(32, len(transcript))
            return (transcript + (GAP_MARKER if gap else "") + snapshot[size:]), gap
    return transcript + GAP_MARKER + snapshot, True


def decode(text: str) -> dict:
    """Reassemble the newest announced file. Keys: complete, name, chunks, have, bytes,
    sha256, missing (indices), payload (bytes or None)."""
    headers = _RESULT.findall(text)
    if not headers:
        return {"complete": False, "name": None, "chunks": 0, "have": 0, "missing": [],
                "payload": None}
    ident, name, chunks, size, digest = headers[-1]
    chunks = int(chunks)
    parts: dict[int, str] = {}
    for c_id, index, total, check, data in _CHUNK.findall(text):
        index = int(index)
        if (c_id != ident or int(total) != chunks or index in parts or index >= chunks
                or _sha(data.encode())[:12] != check):
            continue
        parts[index] = data
    missing = [i for i in range(chunks) if i not in parts]
    payload = None
    if not missing:
        candidate = base64.b64decode("".join(parts[i] for i in range(chunks)))
        if _sha(candidate) == digest and len(candidate) == int(size):
            payload = candidate
    return {"complete": payload is not None, "name": name, "chunks": chunks,
            "have": len(parts), "bytes": int(size), "sha256": digest, "missing": missing,
            "payload": payload}


def send(payload: bytes, name: str, console: str) -> int:
    lines = encode(payload, name)
    with open(console, "a") as handle:
        for line in lines:
            handle.write(line + "\n")  # one write per line keeps lines whole on a tty
            handle.flush()
    return len(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_send = sub.add_parser("send", help="write a file to the console as chunks")
    p_send.add_argument("--file", type=Path, required=True)
    p_send.add_argument("--name", required=True)
    p_send.add_argument("--console", default="/dev/console")
    p_merge = sub.add_parser("merge", help="merge a console snapshot into a transcript")
    p_merge.add_argument("transcript", type=Path)
    p_merge.add_argument("snapshot", type=Path)
    p_merge.add_argument("--cli-text", action="store_true",
                         help="snapshot was printed by `aws ... --output text`, which adds "
                              "one newline that is not console output")
    p_decode = sub.add_parser("decode", help="reassemble the file from a transcript")
    p_decode.add_argument("transcript", type=Path)
    p_decode.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.cmd == "send":
        count = send(args.file.read_bytes(), args.name, args.console)
        print(f"sent {args.file} as {count} lines")
        return 0
    if args.cmd == "merge":
        before = args.transcript.read_text(errors="replace") if args.transcript.exists() else ""
        snapshot = args.snapshot.read_text(errors="replace")
        if args.cli_text and snapshot.endswith("\n"):
            snapshot = snapshot[:-1]
        after, gap = merge(before, snapshot)
        if after != before:
            args.transcript.write_text(after)
        print(json.dumps({"appended": len(after) - len(before), "gap": gap}))
        return 0
    status = decode(args.transcript.read_text(errors="replace"))
    payload = status.pop("payload")
    if payload is not None:
        args.out.write_bytes(payload)
    status["missing"] = status["missing"][:20]
    print(json.dumps(status))
    return 0 if payload is not None else 1


if __name__ == "__main__":
    sys.exit(main())
