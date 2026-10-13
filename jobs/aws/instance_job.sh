#!/usr/bin/env bash
# Phase 2 calibration job that runs on the g6e.xlarge spot instance (via user-data).
#
# build.py embeds this file, the kvevac measurement modules and the notice logger in
# the instance user-data; kvevac-aws.sh launches the instance and reads everything back
# from the serial console. The instance has no credentials, no SSH and no IAM role.
#
# What it does: arms a self-terminate timer, starts the spot-notice logger, installs
# vLLM with uv, serves the model with prefix caching off, runs the prefill/decode sweep
# and the receiver-slowdown measurement, fits the prefill model, then sends a results
# tarball over the console. It re-sends that tarball every KVEVAC_RESEND_S seconds until
# a spot interruption notice arrives, so a missed console poll is recoverable.
#
# Only progress lines (`KVEVAC {...}`) and result chunks go to the console; all other
# output goes to $ROOT/job.log and $ROOT/vllm.log, which ride along in the tarball.
#
# Tunables (kvevac-aws.sh can prepend them to user-data):
#   MODEL, MAX_MODEL_LEN, VLLM_SPEC (pip spec, default "vllm"), KVEVAC_MAX_MIN (90),
#   PREFILL_CONTEXTS, PREFILL_REPEATS, INTERFERENCE_REPEATS, INTERFERENCE_CONTEXT (32000)
# Test hooks (jobs/aws/dry_run.sh; leave unset on AWS):
#   KVEVAC_ROOT, KVEVAC_CONSOLE, KVEVAC_IMDS, KVEVAC_DRY_RUN=1 (no shutdown timer),
#   SKIP_INSTALL=1 + PYTHON, VLLM_CMD, KVEVAC_RESEND_S
set -uo pipefail

ROOT="${KVEVAC_ROOT:-/opt/kvevac}"
MODEL="${MODEL:-NousResearch/Meta-Llama-3.1-8B-Instruct}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-131072}"
MAX_MIN="${KVEVAC_MAX_MIN:-90}"
PREFILL_CONTEXTS="${PREFILL_CONTEXTS:-1000 4000 16000 32000 64000 96000 120000}"
PREFILL_REPEATS="${PREFILL_REPEATS:-3}"
INTERFERENCE_REPEATS="${INTERFERENCE_REPEATS:-5}"
INTERFERENCE_CONTEXT="${INTERFERENCE_CONTEXT:-32000}"
RESEND_S="${KVEVAC_RESEND_S:-120}"
IMDS="${KVEVAC_IMDS:-http://169.254.169.254}"
if [ -z "${KVEVAC_CONSOLE:-}" ]; then
  # Nitro instances expose the serial console that get-console-output reads as ttyS0.
  if [ -w /dev/ttyS0 ]; then KVEVAC_CONSOLE=/dev/ttyS0; else KVEVAC_CONSOLE=/dev/console; fi
fi
export KVEVAC_CONSOLE KVEVAC_IMDS="$IMDS" HOME="${HOME:-/root}"
OUT="$ROOT/results"
mkdir -p "$OUT"
exec >>"$ROOT/job.log" 2>&1

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
# One progress line on the console (and in job.log). Messages must not contain quotes.
event() {
  local line
  line="KVEVAC {\"event\": \"job\", \"at\": \"$(date -u +%Y-%m-%dT%H:%M:%S+00:00)\", \"stage\": \"$1\", \"msg\": \"${2:-}\"}"
  echo "$line"
  echo "$line" >>"$KVEVAC_CONSOLE" 2>/dev/null || true
}

if [ "${KVEVAC_DRY_RUN:-0}" != 1 ]; then
  # Spending cap: the instance powers off (and, with shutdown behaviour "terminate",
  # is deleted) after MAX_MIN minutes whatever else happens.
  shutdown -h "+$MAX_MIN" "kvevac spending cap" || log "could not arm shutdown timer"
fi
event boot "self-terminate in $MAX_MIN min; model $MODEL"

# The logger restarts if it dies, like the systemd unit in jobs/aws_fis/user-data.sh.
( while true; do python3 "$ROOT/notice_logger.py" >/dev/null 2>&1; sleep 1; done ) &
LOGGER_LOOP=$!

imds_action() {
  local tok
  tok="$(curl -sf -m 2 -X PUT "$IMDS/latest/api/token" \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')" || return 1
  curl -sf -m 2 -H "X-aws-ec2-metadata-token: $tok" \
    "$IMDS/latest/meta-data/spot/instance-action" >/dev/null
}

send_results() {
  local tarball="$ROOT/results.tgz"
  [ -f "$ROOT/vllm.log" ] && tail -n 150 "$ROOT/vllm.log" | cut -c1-300 >"$OUT/vllm.tail.log"
  tail -n 200 "$ROOT/job.log" | cut -c1-300 >"$OUT/job.tail.log"
  tar -C "$ROOT" -czf "$tarball" results
  python3 "$ROOT/src/kvevac/measure/console_channel.py" send --file "$tarball" \
    --name "$(hostname)" --console "$KVEVAC_CONSOLE"
}

finish() {
  local status=$?
  trap '' TERM INT
  [ -n "${VLLM_PID:-}" ] && kill "$VLLM_PID" 2>/dev/null
  event finished "status $status; sending results"
  echo "$status" >"$OUT/exit_status"
  send_results
  # Keep re-sending until a spot interruption notice arrives (the runner triggers one
  # with AWS FIS once it has the results), the shutdown timer fires, or 30 rounds pass.
  for _ in $(seq 1 30); do
    for _ in $(seq 1 $((RESEND_S / 5))); do
      if imds_action; then
        event stop "interruption notice seen; no more re-sends"
        wait "$LOGGER_LOOP"  # the logger keeps heartbeating until the instance dies
        return
      fi
      sleep 5
    done
    send_results
  done
}
trap finish EXIT
trap 'exit 143' TERM INT

if [ "${SKIP_INSTALL:-0}" != 1 ]; then
  event install "uv + ${VLLM_SPEC:-vllm}"
  if ! command -v uv >/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$ROOT/bin" sh \
      || python3 -m pip install -q uv
    export PATH="$ROOT/bin:$HOME/.local/bin:$PATH"
  fi
  uv venv -q -p 3.12 "$ROOT/venv" || { event error "uv venv failed"; exit 1; }
  # ninja: FlashInfer JIT-compiles kernels on first use and shells out to it (the
  # first real run, vLLM 0.31.0, died with "No such file or directory: 'ninja'").
  uv pip install -q -p "$ROOT/venv/bin/python" "${VLLM_SPEC:-vllm}" ninja \
    || { event error "vllm install failed"; exit 1; }
  PYTHON="$ROOT/venv/bin/python"
  export PATH="$ROOT/venv/bin:$PATH"
fi
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$ROOT/src"

GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
GPU_LABEL="$(echo "$GPU_NAME" | tr '[:upper:] ' '[:lower:]-' | sed 's/nvidia-//')"
"$PYTHON" - "$OUT/env.json" "$MODEL" "$GPU_NAME" <<'PY'
import json, platform, subprocess, sys
out, model, gpu = sys.argv[1:4]
info = {"model": model, "gpu": gpu, "python": platform.python_version()}
try:
    import vllm, torch
    info.update(vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
except Exception as e:  # recorded, not fatal
    info["import_error"] = repr(e)
try:
    from transformers import AutoConfig
    c = AutoConfig.from_pretrained(model)
    kv_heads = getattr(c, "num_key_value_heads", c.num_attention_heads)
    head_dim = getattr(c, "head_dim", None) or c.hidden_size // c.num_attention_heads
    info["kv_bytes_per_token_bf16"] = 2 * c.num_hidden_layers * kv_heads * head_dim * 2
except Exception as e:
    info["config_error"] = repr(e)
try:
    info["nvidia_smi"] = subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout
except OSError as e:
    info["nvidia_smi"] = repr(e)
json.dump(info, open(out, "w"), indent=1)
PY
event env "GPU $GPU_NAME"

if [ "${KVEVAC_JOB:-calibrate}" = phase3 ] || [ "${KVEVAC_JOB:-}" = planner ]; then
  # Phase 3: the vLLM plugin's first GPU test (kvevac.vllm_plugin.gpu_test). The tier
  # goes on the instance-store NVMe if there is one (DLAMIs mount it at /opt/dlami/nvme).
  TIER_BASE="$ROOT"
  # Memory on the console every 30 s, so a run that dies (run 3, 7 Oct) says why.
  ( while true; do
      event mem "$(free -g | awk '/Mem/{print "used " $3 "G avail " $7 "G"}') shm $(df -h /dev/shm | awk 'NR==2{print $3}')"
      sleep 30
    done ) &
  if [ "${PHASE3_TIER:-nvme}" = peer ]; then
    # The tier is a peer's RAM over NFS (jobs/aws/peer_node.sh): evacuation and
    # restore both cross the network, like a surviving node's DRAM tier.
    # The DLAMI has no NFS client. apt may be locked by boot-time unattended upgrades,
    # so wait for the lock (the first two-node run, 8 Oct, failed silently here).
    if [ ! -x /sbin/mount.nfs ]; then
      export DEBIAN_FRONTEND=noninteractive
      for _ in 1 2 3; do
        apt-get -o DPkg::Lock::Timeout=300 update -qq \
          && apt-get -o DPkg::Lock::Timeout=300 install -y -qq nfs-common && break
        sleep 15
      done
      [ -x /sbin/mount.nfs ] || { event error "nfs-common install failed"; exit 1; }
    fi
    event phase3 "nfs client ready; mounting ${PEER_IP}"
    mkdir -p /mnt/peer
    for _ in $(seq 1 60); do
      mount -t nfs -o vers=4.2,nconnect=8,rsize=1048576,wsize=1048576,hard \
        "${PEER_IP:?PEER_IP unset}:/export" /mnt/peer && break
      sleep 10
    done
    mountpoint -q /mnt/peer || { event error "could not mount ${PEER_IP}:/export"; exit 1; }
    TIER_BASE=/mnt/peer
  elif [ "${PHASE3_TIER:-nvme}" = ram ]; then
    mkdir -p /mnt/ram && mount -t tmpfs -o "size=${PHASE3_RAM_GB:-9}g" tmpfs /mnt/ram \
      && TIER_BASE=/mnt/ram
  elif mountpoint -q /opt/dlami/nvme 2>/dev/null; then
    TIER_BASE=/opt/dlami/nvme
  else
    DEV="$(lsblk -dpnP -o NAME,MOUNTPOINT,MODEL 2>/dev/null \
      | grep 'Instance Storage' | grep 'MOUNTPOINT=""' | head -1 | sed 's/NAME="\([^"]*\)".*/\1/')"
    if [ -n "$DEV" ] && mkfs.ext4 -q -F "$DEV" && mkdir -p /mnt/nvme && mount "$DEV" /mnt/nvme; then
      TIER_BASE=/mnt/nvme
    fi
  fi
  event phase3 "tier on $TIER_BASE"
  if [ "$KVEVAC_JOB" = planner ]; then
    # Code and trials ride on the memory node (user-data is full): jobs/aws/planner_job.sh
    tar -xzf /mnt/peer/code.tgz -C "$ROOT/src" && . "$ROOT/src/planner_job.sh"
    STATUS=$?
  else
  "$PYTHON" -m kvevac.vllm_plugin.gpu_test --model "$MODEL" --tier "$TIER_BASE/kvevac-tier" \
    --out "$OUT" --logs "$ROOT" --python "$PYTHON" \
    --cpu-gb "${PHASE3_CPU_GB:-14}" --scale "${PHASE3_SCALE:-1}" --cold-tier "$ROOT/cold-tier" \
    --notice-s "${PHASE3_NOTICE_S:-120}" ${PHASE3_SESSIONS:+--sessions "$PHASE3_SESSIONS"} \
    ${PHASE3_MAX_LEN:+--max-model-len "$PHASE3_MAX_LEN"} ${PHASE3_GPU_UTIL:+--gpu-util "$PHASE3_GPU_UTIL"} \
    ${PHASE3_RATE_MBIT:+--rate-mbit "$PHASE3_RATE_MBIT" --throttle-dev "$(ip route get "${PEER_IP:-1.1.1.1}" | awk '{for (i = 1; i < NF; i++) if ($i == "dev") print $(i + 1)}')"}
  STATUS=$?
  fi
  for f in "$ROOT"/vllm-*.log; do
    [ -f "$f" ] && tail -n 120 "$f" | cut -c1-300 >"$OUT/$(basename "$f" .log).tail.log"
  done
  rm -f "$OUT/flush.json"
  [ "$STATUS" = 0 ] || { event error "phase3 test failed"; exit 1; }
  event "done" "phase3 test complete"
  exit 0
fi
: kvevac-phase3-end  # build.py cuts the phase3 user-data here; the rest is calibration

event vllm "starting server; model download and compile take a while"
DEFAULT_VLLM_CMD="$PYTHON -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000 \
  --max-model-len $MAX_MODEL_LEN --no-enable-prefix-caching --gpu-memory-utilization 0.90"
# PyTorch sampling instead of FlashInfer's JIT-compiled sampler: nothing to compile at
# startup, and sampling is not what we measure. Override with VLLM_USE_FLASHINFER_SAMPLER=1.
VLLM_SERVER_DEV_MODE=1 VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}" \
  bash -c "exec ${VLLM_CMD:-$DEFAULT_VLLM_CMD}" >"$ROOT/vllm.log" 2>&1 &
VLLM_PID=$!
for i in $(seq 1 360); do
  curl -sf localhost:8000/health >/dev/null && break
  kill -0 "$VLLM_PID" 2>/dev/null || { event error "vLLM died during startup"; exit 1; }
  [ $((i % 24)) = 0 ] && event vllm "still starting after $((i * 5 / 60)) min"
  sleep 5
done
curl -sf localhost:8000/health >/dev/null || { event error "vLLM never became healthy"; exit 1; }
event vllm "healthy"

event prefill "contexts $PREFILL_CONTEXTS x $PREFILL_REPEATS"
# shellcheck disable=SC2086  # contexts are a word list on purpose
"$PYTHON" -m kvevac.measure.prefill --base-url http://localhost:8000 --model "$MODEL" \
  --gpu "${GPU_LABEL}-measured" --contexts $PREFILL_CONTEXTS --repeats "$PREFILL_REPEATS" \
  --out "$OUT/prefill.json" || { event error "prefill sweep failed"; exit 1; }

for mode in host h2d; do
  event interference "mode $mode"
  "$PYTHON" -m kvevac.measure.interference --base-url http://localhost:8000 \
    --model "$MODEL" --context "$INTERFERENCE_CONTEXT" --repeats "$INTERFERENCE_REPEATS" \
    --rates 1 2.5 10 0 --mode "$mode" --out "$OUT/interference-${mode}.json" \
    || event error "interference $mode failed"
done

event fit "fitting the prefill model"
"$PYTHON" - "$OUT" <<'PY' || event error "fit failed"
import json, sys
from pathlib import Path
from kvevac.calibration import fit_prefill
out = Path(sys.argv[1])
data = json.loads((out / "prefill.json").read_text())
fit = fit_prefill([tuple(p) for p in data["prefill"]])
(out / "fit.json").write_text(json.dumps(fit.__dict__, indent=1))
print("fit:", fit)
PY
event "done" "measurements complete"
