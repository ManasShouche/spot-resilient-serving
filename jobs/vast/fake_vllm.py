"""Minimal OpenAI-compatible streaming server for dry-running the calibration job.

Prefill delay grows with prompt length (so fits are well-posed); no GPU needed.
Usage: python jobs/vast/fake_vllm.py --port 8000
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOK_PER_S = 400_000.0
KNEE = 64_000.0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200 if self.path == "/health" else 404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        tokens = len(body["prompt"].split())
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        time.sleep(0.01 + tokens / TOK_PER_S * (1 + tokens / (2 * KNEE)))
        for _ in range(body.get("max_tokens", 1)):
            self.wfile.write(f"data: {json.dumps({'choices': [{'text': ' x'}]})}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.003)
        usage = {"choices": [], "usage": {"prompt_tokens": tokens}}
        self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    ThreadingHTTPServer(("127.0.0.1", parser.parse_args().port), Handler).serve_forever()
