"""Drive the measurement client against a fake OpenAI-compatible streaming server."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from kvevac.calibration import fit_prefill
from kvevac.measure.prefill import measure

PREFILL_TOK_S = 200_000.0  # fast fake so the test stays quick


class FakeVLLM(BaseHTTPRequestHandler):
    seen_prompts: list[str] = []

    def log_message(self, *_: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeVLLM.seen_prompts.append(body["prompt"])
        tokens = len(body["prompt"].split())
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        time.sleep(tokens / PREFILL_TOK_S)
        for _ in range(body["max_tokens"]):
            chunk = {"choices": [{"text": " x"}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.002)
        usage = {"choices": [], "usage": {"prompt_tokens": tokens}}
        self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeVLLM)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_measure_produces_fittable_points_with_server_token_counts(server) -> None:
    result = measure(server, "fake", [2_000, 8_000, 32_000], repeats=1, decode_tokens=8)
    contexts = [c for c, _ in result["prefill"]]
    assert contexts == sorted(contexts) and contexts[0] > 1_000
    fit = fit_prefill([tuple(p) for p in result["prefill"]])
    assert fit.tokens_per_s > 0
    assert result["decode_tokens_per_s"] > 0


def test_every_prompt_is_unique_so_prefix_cache_cannot_hit(server) -> None:
    FakeVLLM.seen_prompts.clear()
    measure(server, "fake", [1_000], repeats=3, decode_tokens=2)
    heads = [p[:20] for p in FakeVLLM.seen_prompts]
    assert len(set(heads)) == len(heads)
