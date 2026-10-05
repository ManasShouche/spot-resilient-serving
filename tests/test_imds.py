import json
import threading
import urllib.error
import urllib.request

import pytest

from kvevac.notice.imds import (
    ACTION_PATH,
    REBALANCE_PATH,
    TOKEN_HEADER,
    TOKEN_PATH,
    TTL_HEADER,
    MockIMDS,
    NoticeWatcher,
)


@pytest.fixture
def imds():
    with MockIMDS() as mock:
        yield mock


def token(base: str) -> str:
    request = urllib.request.Request(base + TOKEN_PATH, method="PUT",
                                     headers={TTL_HEADER: "60"})
    return urllib.request.urlopen(request).read().decode()


def get(base: str, path: str, tok: str | None):
    headers = {TOKEN_HEADER: tok} if tok else {}
    return urllib.request.urlopen(urllib.request.Request(base + path, headers=headers))


def test_imdsv1_requests_without_token_are_rejected(imds) -> None:
    with pytest.raises(urllib.error.HTTPError) as error:
        get(imds.base_url, ACTION_PATH, None)
    assert error.value.code == 401


def test_endpoints_return_404_until_a_signal_exists(imds) -> None:
    tok = token(imds.base_url)
    for path in (ACTION_PATH, REBALANCE_PATH):
        with pytest.raises(urllib.error.HTTPError) as error:
            get(imds.base_url, path, tok)
        assert error.value.code == 404


def test_scheduled_interruption_matches_ec2_formats(imds) -> None:
    terminate_at = imds.schedule_interruption(notice_s=120)
    tok = token(imds.base_url)
    action = json.loads(get(imds.base_url, ACTION_PATH, tok).read())
    rebalance = json.loads(get(imds.base_url, REBALANCE_PATH, tok).read())
    assert action == {"action": "terminate", "time": terminate_at.strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert set(rebalance) == {"noticeTime"}


def test_watcher_fires_rebalance_then_interruption_once(imds) -> None:
    events: list[str] = []
    done = threading.Event()

    def on_interruption(interruption) -> None:
        events.append(f"interruption:{interruption.action}")
        assert 100 < interruption.notice_s <= 121
        done.set()

    watcher = NoticeWatcher(imds.base_url, poll_s=0.05,
                            on_rebalance=lambda _: events.append("rebalance"),
                            on_interruption=on_interruption).start()
    imds.schedule_interruption(notice_s=120, after_s=0.1)
    assert done.wait(5)
    watcher.stop()
    assert events == ["rebalance", "interruption:terminate"]
