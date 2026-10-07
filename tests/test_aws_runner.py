import base64
import gzip
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from kvevac.notice.imds import MockIMDS

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "jobs" / "aws" / "kvevac-aws.sh"
LOGGER = ROOT / "jobs" / "aws_fis" / "notice_logger.py"

sys.path.insert(0, str(ROOT / "jobs" / "aws"))
import build  # noqa: E402


def _embedded(name: str) -> str:
    match = re.search(rf'^{name}=\$\(cat <<\'KVEVAC_B64\'\n(.*?)\nKVEVAC_B64\n\)',
                      RUNNER.read_text(), re.S | re.M)
    assert match, name
    return gzip.decompress(base64.b64decode(match.group(1))).decode()


def test_runner_is_up_to_date_with_its_sources() -> None:
    script, size = build.build()
    assert RUNNER.read_text() == script, "run: python jobs/aws/build.py"
    assert size < build.USER_DATA_LIMIT - 1024


def test_user_data_embeds_current_sources() -> None:
    user_data = _embedded("USERDATA_GZ_B64")
    for target, source in build.INSTANCE_FILES.items():
        text = (ROOT / source).read_text().rstrip("\n")
        assert f"cat > \"$ROOT/{target}\" <<'KVEVAC_EOF'\n{text}\nKVEVAC_EOF" in user_data
    assert user_data.rstrip().endswith('exec bash "$ROOT/job.sh"')
    assert _embedded("CONSOLE_CHANNEL_GZ_B64") == (
        ROOT / "kvevac/measure/console_channel.py").read_text()


def test_scripts_parse() -> None:
    for script in ("kvevac-aws.sh", "instance_job.sh", "dry_run.sh"):
        subprocess.run(["bash", "-n", str(ROOT / "jobs" / "aws" / script)], check=True)


def test_logger_writes_to_kvevac_console(tmp_path: Path) -> None:
    console = tmp_path / "console"
    with MockIMDS() as imds:
        proc = subprocess.Popen([sys.executable, str(LOGGER)], stdout=subprocess.DEVNULL,
                                env={**os.environ, "KVEVAC_IMDS": imds.base_url,
                                     "KVEVAC_CONSOLE": str(console)})
        time.sleep(1.5)
        proc.terminate()
        proc.communicate(timeout=10)
    lines = console.read_text().splitlines()
    assert lines[0].startswith('KVEVAC {"event": "watching"')
    assert any('"heartbeat"' in line for line in lines)
