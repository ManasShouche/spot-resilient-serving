import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kvevac.notice.handler import SpotNoticeHandler
from kvevac.notice.imds import MockIMDS


class FakeVLLM(BaseHTTPRequestHandler):
    paths: list[str] = []

    def log_message(self, *_: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        FakeVLLM.paths.append(self.path)
        body = json.dumps({"status": "paused"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_interruption_pauses_vllm_without_clearing_cache_then_evacuates(tmp_path) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeVLLM)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    deadlines = []
    log = tmp_path / "timeline.jsonl"
    with MockIMDS() as imds:
        handler = SpotNoticeHandler(imds_url=imds.base_url,
                                    vllm_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                                    on_evacuate=deadlines.append, log_path=log,
                                    poll_s=0.05).start()
        terminate_at = imds.schedule_interruption(notice_s=120, rebalance_lead_s=0.2,
                                                  after_s=0.05)
        assert handler.interrupted.wait(5)
        handler.stop()
    httpd.shutdown()

    assert FakeVLLM.paths == ["/pause?mode=wait&clear_cache=false"]
    assert deadlines == [terminate_at.replace(microsecond=0)]
    events = [json.loads(line)["event"] for line in log.read_text().splitlines()]
    assert events == ["watching", "rebalance_recommendation", "interruption_notice",
                      "vllm_paused", "evacuation_started", "evacuation_returned"]


def test_flush_request_is_written_before_admission_is_paused(tmp_path) -> None:
    from kvevac.vllm_plugin.core import read_flush_request
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeVLLM)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    FakeVLLM.paths = []
    control = tmp_path / "flush.json"
    log = tmp_path / "timeline.jsonl"
    with MockIMDS() as imds:
        handler = SpotNoticeHandler(imds_url=imds.base_url,
                                    vllm_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                                    log_path=log, poll_s=0.05, flush_control=control).start()
        terminate_at = imds.schedule_interruption(notice_s=120, rebalance_lead_s=0.2,
                                                  after_s=0.05)
        assert handler.interrupted.wait(5)
        handler.stop()
    httpd.shutdown()
    request = read_flush_request(control, last_seq=0)
    assert request is not None
    assert abs(request.deadline_unix - terminate_at.timestamp()) < 1.0
    events = [json.loads(line)["event"] for line in log.read_text().splitlines()]
    assert events.index("flush_requested") < events.index("vllm_paused")
