#!/usr/bin/env bash
# Build a self-contained user-data file that embeds notice_logger.py.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
{
  echo '#!/bin/bash'
  echo '# EC2 user-data: install and start the kvevac spot-notice logger.'
  echo "cat > /usr/local/bin/kvevac-notice-logger <<'PYEOF'"
  cat "$DIR/notice_logger.py"
  echo 'PYEOF'
  echo 'chmod +x /usr/local/bin/kvevac-notice-logger'
  cat <<'UNIT'
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
UNIT
} > "$DIR/user-data.sh"
echo "wrote $DIR/user-data.sh"
