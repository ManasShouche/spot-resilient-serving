#!/usr/bin/env bash
# Run kvevac-aws.sh end to end without AWS or a GPU, to check the plumbing before paying.
#
# Fakes: the `aws` CLI (jobs/aws/fake_aws.py, which runs the user-data locally as the
# "instance"), a mock IMDS that turns the FIS call into a spot notice and a termination,
# vLLM (jobs/vast/fake_vllm.py) and nvidia-smi. Real: the runner script, the user-data
# exactly as built, the instance job, the measurement modules, the console channel
# (64 KB windows, merged and checksum-verified) and the notice-timing analysis.
#
# Not covered: the real AWS API, the AMI, uv/vLLM installs, CUDA and the model download.
# Needs: python3 with this repo's dev environment (pytest is not needed) plus jmespath.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-python3}"
"$PY" -c "import jmespath" 2>/dev/null || { echo "pip install jmespath first"; exit 1; }
TMP="$(mktemp -d)"
cleanup() {
  [ -n "${IMDS_PID:-}" ] && kill "$IMDS_PID" 2>/dev/null
  pkill -9 -f "$TMP/state/user-data.sh" 2>/dev/null || true
  pkill -9 -f "fake_vllm.py --port 8000" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT

"$PY" "$ROOT/jobs/aws/build.py" --check

mkdir -p "$TMP/bin" "$TMP/state" "$TMP/instance"
cat >"$TMP/bin/aws" <<SH
#!/usr/bin/env bash
exec "$PY" "$ROOT/jobs/aws/fake_aws.py" "\$@"
SH
cat >"$TMP/bin/nvidia-smi" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *query-gpu* ]]; then echo "NVIDIA L40S"; else echo "fake nvidia-smi"; fi
SH
chmod +x "$TMP/bin/aws" "$TMP/bin/nvidia-smi"

export FAKE_AWS_STATE="$TMP/state" FAKE_AWS_NO_CAPACITY=us-east-1a FAKE_AWS_NOTICE_S=20
PYTHONPATH="$ROOT" "$PY" "$ROOT/jobs/aws/fake_aws.py" imds &
IMDS_PID=$!
for _ in $(seq 1 50); do [ -f "$TMP/state/imds-url" ] && break; sleep 0.2; done

# Instance-side test hooks; the fake run-instances passes its environment through.
export PATH="$TMP/bin:$PATH" KVEVAC_ROOT="$TMP/instance" KVEVAC_CONSOLE="$TMP/state/console" \
  KVEVAC_IMDS="$(cat "$TMP/state/imds-url")" KVEVAC_DRY_RUN=1 SKIP_INSTALL=1 PYTHON="$PY" \
  VLLM_CMD="$PY $ROOT/jobs/vast/fake_vllm.py --port 8000"
# Runner settings, shrunk so the dry run takes a couple of minutes.
export KVEVAC_RUNS="$TMP/runs" POLL_S=2 NOTICE_WAIT_S=90 MODEL=fake-model \
  PREFILL_REPEATS=2 INTERFERENCE_REPEATS=2 KVEVAC_RESEND_S=10

# Start a run, lose the "CloudShell session" (SIGHUP) while the instance is measuring,
# check the instance survived, then finish with `resume`.
bash "$ROOT/jobs/aws/kvevac-aws.sh" run >"$TMP/runner.log" 2>&1 &
RUNNER=$!
for _ in $(seq 1 120); do
  grep -qs '"stage": "prefill"' "$TMP/state/console" && break
  sleep 0.5
done
kill -HUP "$RUNNER"
wait "$RUNNER" || true
cat "$TMP/runner.log"
grep -q "kvevac-aws.sh resume" "$TMP/runner.log" || { echo "DRY RUN FAILED: no resume hint"; exit 1; }
bash "$ROOT/jobs/aws/kvevac-aws.sh" resume | tee -a "$TMP/runner.log"

RUN="$TMP/runs/$(readlink "$TMP/runs/latest")"
fail() { echo "DRY RUN FAILED: $*"; exit 1; }
# MARKET=on-demand (and FAKE_AWS_FULL_CALLS / RETRY_MIN) exercise the fallback paths;
# an on-demand run has no FIS notice to time.
MARKET="${MARKET:-spot}"
for f in results/prefill.json results/fit.json results/env.json results/interference-host.json \
    results/interference-h2d.json results/job.tail.log; do
  [ -s "$RUN/$f" ] || fail "missing $f"
done
[ "$(cat "$RUN/results/exit_status")" = 0 ] || fail "instance job exit status $(cat "$RUN/results/exit_status")"
grep -q "no $MARKET capacity in us-east-1a" "$TMP/runner.log" || fail "no zone fallback"
if [ "${FAKE_AWS_FULL_CALLS:-0}" -gt 0 ]; then
  grep -q "retrying in" "$TMP/runner.log" || fail "no retry after a full pass"
fi
if [ "$MARKET" = spot ]; then
  [ -s "$RUN/notice.json" ] || fail "missing notice.json"
  grep -Eq '"announced_notice_s": (1[89]|2[01])' "$RUN/notice.json" \
    || fail "bad notice timing: $(cat "$RUN/notice.json")"
else
  grep -q "skipping the FIS spot interruption" "$TMP/runner.log" || fail "FIS not skipped"
fi
[ ! -f "$TMP/state/fis-template.json" ] || fail "FIS template not deleted"
[ "$("$PY" "$ROOT/jobs/aws/fake_aws.py" ec2 describe-instances --query \
  'Reservations[0].Instances[0].State.Name' --output text)" = terminated ] || fail "instance alive"
[ -s "$TMP/runs/$(readlink "$TMP/runs/latest").tar.gz" ] || fail "no run tarball"
echo "DRY RUN OK"
