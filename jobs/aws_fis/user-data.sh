#!/bin/bash
# EC2 user-data: install and start the kvevac spot-notice logger.
cat > /usr/local/bin/kvevac-notice-logger <<'PYEOF'
#!/usr/bin/env python3
"""Standalone spot-notice logger for an EC2 test instance (stdlib only, IMDSv2).

Writes one line per event to the serial console, prefixed `KVEVAC `, so results can be
read with `aws ec2 get-console-output` without giving the instance any credentials.
IMDS is polled every second. Heartbeats go out every 60 s while nothing has happened,
then every second once a spot signal (rebalance or interruption) arrives, so the last
heartbeat before the instance disappears brackets the real termination time without
flooding the console during the wait.
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

IMDS = os.environ.get("KVEVAC_IMDS", "http://169.254.169.254")  # override only for tests
PATHS = {"rebalance": "/latest/meta-data/events/recommendations/rebalance",
         "interruption": "/latest/meta-data/spot/instance-action"}
POLL_S = 1.0
IDLE_BEAT_S = 60.0  # heartbeat interval before any spot signal
ALERT_BEAT_S = 1.0  # heartbeat interval once a signal has arrived


def emit(event, **fields):
    line = "KVEVAC " + json.dumps({"event": event,
                                   "at": datetime.now(timezone.utc).isoformat(), **fields})
    print(line, flush=True)
    for target in ("/dev/console", "/var/log/kvevac-notice.log"):
        try:
            with open(target, "a") as handle:
                handle.write(line + "\n")
        except OSError:
            pass


def token():
    request = urllib.request.Request(IMDS + "/latest/api/token", method="PUT",
                                     headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"})
    return urllib.request.urlopen(request, timeout=2).read().decode()


def get(path, tok):
    request = urllib.request.Request(IMDS + path, headers={"X-aws-ec2-metadata-token": tok})
    try:
        return json.loads(urllib.request.urlopen(request, timeout=2).read().decode())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main():
    emit("watching")
    tok, tok_at, seen, beat, beat_at = token(), time.monotonic(), set(), 0, None
    while True:
        if time.monotonic() - tok_at > 3600:
            tok, tok_at = token(), time.monotonic()
        for name, path in PATHS.items():
            if name in seen:
                continue
            try:
                body = get(path, tok)
            except Exception as error:  # keep polling through IMDS hiccups
                emit("poll_error", path=name, error=str(error))
                continue
            if body:
                seen.add(name)
                emit(name, body=body)
        interval = ALERT_BEAT_S if seen else IDLE_BEAT_S
        if beat_at is None or time.monotonic() - beat_at >= interval:
            beat, beat_at = beat + 1, time.monotonic()
            emit("heartbeat", n=beat)
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
PYEOF
chmod +x /usr/local/bin/kvevac-notice-logger
cat > /etc/systemd/system/kvevac-notice.service <<'SVC'
[Unit]
Description=kvevac spot notice logger
After=network-online.target
[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/kvevac-notice-logger
Restart=always
[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload
systemctl enable --now kvevac-notice.service
