"""Measure cold-prefill TTFT and decode rate on an OpenAI-compatible server (vLLM).

Every prompt starts with a random nonce, so the prefix cache cannot hit and each
request pays a full prefill (also start vLLM with --no-enable-prefix-caching to be
sure). TTFT is the time from sending the request to the first streamed token, and the
context length comes from the server's own usage report (`stream_options.include_usage`),
not from a local token estimate.

Usage:
    python -m kvevac.measure.prefill --base-url http://localhost:8000 --model <name> \\
        --gpu l40s-measured --contexts 1000 4000 16000 32000 64000 --repeats 3 \\
        --out results/calibration/l40s.json
"""

from __future__ import annotations

import argparse
import json
import secrets
import statistics
import time
import urllib.request
from pathlib import Path

FILLER = " the"  # one token per repetition for Llama-family tokenizers (approximate)


def _stream_completion(base_url: str, model: str, prompt: str, max_tokens: int,
                       timeout_s: float) -> tuple[float, list[float], int]:
    """Returns (ttft_s, token arrival times, prompt_tokens)."""
    body = json.dumps({
        "model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0,
        "stream": True, "stream_options": {"include_usage": True},
    }).encode()
    request = urllib.request.Request(base_url.rstrip("/") + "/v1/completions", data=body,
                                     headers={"Content-Type": "application/json"})
    sent = time.perf_counter()
    arrivals: list[float] = []
    prompt_tokens = 0
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            if chunk.get("usage"):
                prompt_tokens = chunk["usage"].get("prompt_tokens", 0)
            if any(choice.get("text") for choice in chunk.get("choices", [])):
                arrivals.append(time.perf_counter() - sent)
    if not arrivals:
        raise RuntimeError("server streamed no tokens")
    return arrivals[0], arrivals, prompt_tokens


def cold_prompt(target_tokens: int) -> str:
    return f"[{secrets.token_hex(8)}]" + FILLER * max(1, target_tokens - 8)


def measure(base_url: str, model: str, contexts: list[int], repeats: int,
            decode_tokens: int = 128, timeout_s: float = 600.0) -> dict:
    prefill = []
    for target in contexts:
        for _ in range(repeats):
            ttft, _, tokens = _stream_completion(base_url, model, cold_prompt(target), 1,
                                                 timeout_s)
            prefill.append([tokens or target, round(ttft, 6)])
    _, arrivals, _ = _stream_completion(base_url, model, cold_prompt(512), decode_tokens,
                                        timeout_s)
    gaps = [b - a for a, b in zip(arrivals, arrivals[1:], strict=False)]
    decode_rate = 1 / statistics.median(gaps) if gaps else 0.0
    return {"prefill": prefill, "decode_tokens_per_s": round(decode_rate, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--gpu", required=True, help="profile name to record")
    parser.add_argument("--contexts", type=int, nargs="+",
                        default=[1_000, 4_000, 16_000, 32_000, 64_000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = {"gpu": args.gpu, "model": args.model,
              **measure(args.base_url, args.model, args.contexts, args.repeats)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1))
    print(f"wrote {args.out}: {len(result['prefill'])} prefill points, "
          f"decode {result['decode_tokens_per_s']} tok/s")


if __name__ == "__main__":
    main()
