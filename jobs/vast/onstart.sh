#!/usr/bin/env bash
# Phase 2 calibration job for a single-GPU Vast.ai instance.
#
# Paste this file into the instance's "on-start script". It installs vLLM if needed,
# serves the model with prefix caching OFF, runs the prefill/decode and
# receiver-slowdown measurements, and pushes everything to a new branch
# `calibration/<label>-<timestamp>` of the project repo. It then destroys the
# instance if VAST_API_KEY and CONTAINER_ID are available (best effort; verify in the
# Vast console that the instance is gone).
#
# Required environment variables (set them in the Vast template/instance env, never
# in this file):
#   HF_TOKEN   read token with access to the model (Llama 3.1 is gated)
#   GH_TOKEN   fine-grained GitHub token: contents read/write on this repo only
# Optional:
#   MODEL            default meta-llama/Llama-3.1-8B-Instruct
#   GPU_LABEL        default derived from nvidia-smi (e.g. l40s)
#   REPO             default ManasShouche/spot-resilient-serving
#   MAX_MODEL_LEN    default 131072
#   JOB_TIMEOUT_MIN  default 120 (hard cap on the whole job, a spend guard)
#   VAST_API_KEY     enables self-destroy at the end
# Test hooks (used by jobs/vast/dry_run.sh; leave unset on Vast):
#   REPO_URL         clone URL override (no token added)
#   VLLM_CMD         server command override
#   SKIP_INSTALL=1   skip pip installs
set -uo pipefail

MODEL="${MODEL:-meta-llama/Llama-3.1-8B-Instruct}"
REPO="${REPO:-ManasShouche/spot-resilient-serving}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-131072}"
JOB_TIMEOUT_MIN="${JOB_TIMEOUT_MIN:-120}"
WORK="${WORK_DIR:-/workspace/kvevac-job}"
mkdir -p "$WORK" && cd "$WORK"
exec > >(tee -a "$WORK/job.log") 2>&1

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
: "${HF_TOKEN:?HF_TOKEN is not set}"
: "${GH_TOKEN:?GH_TOKEN is not set}"
export HF_TOKEN HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

if ! command -v git >/dev/null || ! command -v curl >/dev/null; then
  log "installing git/curl"
  (apt-get update -qq && apt-get install -y -qq git curl) >/dev/null 2>&1 \
    || log "could not install git/curl; continuing"
fi

GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
GPU_LABEL="${GPU_LABEL:-$(echo "$GPU_NAME" | tr '[:upper:] ' '[:lower:]-' | sed 's/nvidia-//')}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BRANCH="calibration/${GPU_LABEL}-${STAMP}"
OUT="results/calibration/${GPU_LABEL}-${STAMP}"
log "GPU: $GPU_NAME -> label $GPU_LABEL; branch $BRANCH"

# Clone without ever echoing the token.
CLONE_URL="${REPO_URL:-https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git}"
git clone -q "$CLONE_URL" repo || {
  log "clone failed (check GH_TOKEN scope)"; exit 1; }
cd repo
git config user.name "kvevac-calibration-job"
git config user.email "kvevac-job@users.noreply.github.com"
mkdir -p "$OUT"

push_results() {
  cp "$WORK/job.log" "$OUT/job.log" 2>/dev/null || true
  [ -f "$WORK/vllm.log" ] && tail -n 400 "$WORK/vllm.log" > "$OUT/vllm.tail.log"
  git checkout -q -B "$BRANCH"
  git add "$OUT"
  git commit -q -m "Calibration run ${GPU_LABEL} ${STAMP}" || true
  git push -q origin "$BRANCH" && log "pushed $BRANCH" || log "PUSH FAILED"
}

self_destroy() {
  # VAST_API_KEY: your key, if you chose to provide one. CONTAINER_API_KEY /
  # CONTAINER_ID: instance-scoped values Vast may inject (unverified; always confirm in
  # the console that the instance is gone).
  local key="${VAST_API_KEY:-${CONTAINER_API_KEY:-}}"
  if [ -n "$key" ] && [ -n "${CONTAINER_ID:-}" ]; then
    log "destroying instance $CONTAINER_ID"
    curl -s -X DELETE "https://console.vast.ai/api/v0/instances/${CONTAINER_ID}/" \
      -H "Authorization: Bearer ${key}" >/dev/null || true
  else
    log "REMINDER: destroy this instance in the Vast console (storage bills until deleted)"
  fi
}

finish() {
  status=$?
  trap '' TERM INT  # cleanup (push + destroy) must not be interrupted
  log "job exiting with status $status"
  if [ -n "${WATCHER_PID:-}" ]; then
    # Kill the watcher before its sleep: killing the sleep first would let the
    # watcher go on to signal this script mid-cleanup.
    sleepers="$(pgrep -P "$WATCHER_PID" 2>/dev/null || true)"
    kill "$WATCHER_PID" 2>/dev/null
    [ -n "$sleepers" ] && kill $sleepers 2>/dev/null
  fi
  [ -n "${VLLM_PID:-}" ] && kill "$VLLM_PID" 2>/dev/null
  push_results
  self_destroy
}
trap finish EXIT
trap 'exit 143' TERM INT  # turn signals into a normal exit so the EXIT trap runs
# Spend guard: kill the whole job after JOB_TIMEOUT_MIN minutes.
# Its output is detached so the sleeping watcher never holds the log pipe open.
( sleep $((JOB_TIMEOUT_MIN * 60)); echo "TIMEOUT" >> "$WORK/job.log"; kill -TERM $$ ) \
  >/dev/null 2>&1 &
WATCHER_PID=$!

if [ "${SKIP_INSTALL:-0}" != 1 ]; then
  log "installing"
  python3 -m pip install -q --upgrade pip
  python3 -c "import vllm" 2>/dev/null || python3 -m pip install -q vllm
  python3 -m pip install -q -e . >/dev/null
fi

python3 - "$OUT/env.json" "$MODEL" "$GPU_NAME" <<'PY'
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
    head_dim = getattr(c, "head_dim", c.hidden_size // c.num_attention_heads)
    info["kv_bytes_per_token_bf16"] = 2 * c.num_hidden_layers * kv_heads * head_dim * 2
except Exception as e:
    info["config_error"] = repr(e)
info["nvidia_smi"] = subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout
json.dump(info, open(out, "w"), indent=1)
PY

log "starting vLLM ($MODEL, prefix caching OFF)"
DEFAULT_VLLM_CMD="python3 -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000 \
  --max-model-len $MAX_MODEL_LEN --no-enable-prefix-caching --gpu-memory-utilization 0.90"
VLLM_SERVER_DEV_MODE=1 bash -c "exec ${VLLM_CMD:-$DEFAULT_VLLM_CMD}" > "$WORK/vllm.log" 2>&1 &
VLLM_PID=$!
for _ in $(seq 1 180); do
  curl -sf localhost:8000/health >/dev/null && break
  kill -0 "$VLLM_PID" 2>/dev/null || { log "vLLM died during startup"; exit 1; }
  sleep 5
done
curl -sf localhost:8000/health >/dev/null || { log "vLLM never became healthy"; exit 1; }
log "vLLM healthy"

log "prefill/decode sweep"
python3 -m kvevac.measure.prefill --base-url http://localhost:8000 --model "$MODEL" \
  --gpu "${GPU_LABEL}-measured" --contexts 1000 4000 16000 32000 64000 96000 120000 \
  --repeats 3 --out "$OUT/prefill.json"

for mode in host h2d; do
  log "receiver slowdown ($mode)"
  python3 -m kvevac.measure.interference --base-url http://localhost:8000 --model "$MODEL" \
    --context 32000 --repeats 5 --rates 1 2.5 10 0 --mode "$mode" \
    --out "$OUT/interference-${mode}.json"
done

log "fitting"
python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
from kvevac.calibration import fit_prefill
out = Path(sys.argv[1])
data = json.loads((out / "prefill.json").read_text())
fit = fit_prefill([tuple(p) for p in data["prefill"]])
(out / "fit.json").write_text(json.dumps(fit.__dict__, indent=1))
print("fit:", fit)
PY
log "done"
