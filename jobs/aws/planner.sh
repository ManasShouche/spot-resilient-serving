#!/usr/bin/env bash
# Planner trials on AWS (kvevac.planner_trials): does the evacuation planner choose
# better than simple orders when not everything fits before the deadline?
#
#   AWS_REGION=us-east-2 TRACE=data/raw/agentx.jsonl bash jobs/aws/planner.sh
#
# 1. Exports trace snapshots (trials.json) from the AgentX trace on this machine, and
#    an offline prediction of the sweep (preview.json) to compare the run against.
# 2. Launches the memory node (jobs/aws/peer_node.sh) with the trial code and
#    trials.json added to its user-data, since the GPU node's user-data is full.
# 3. Runs an on-demand g6e.2xlarge (L40S, 64 GB RAM: room for a 36 GiB CPU tier)
#    through jobs/aws/two_node.sh. It prefills each snapshot's sessions once, then for
#    every link rate x notice x policy empties the tier and flushes again.
# Both instances power themselves off after MAX_MIN minutes whatever happens, and
# two_node.sh terminates the memory node on exit. Expected: about 5 h, ~$13
# (g6e.2xlarge ~$2.24/h + r7i.xlarge ~$0.27/h). Cap at MAX_MIN=330: about $14.
set -euo pipefail
cd "$(dirname "$0")/../.."
export AWS_REGION="${AWS_REGION:-us-east-2}"
MAX_MIN="${MAX_MIN:-330}"
TRACE="${TRACE:-data/raw/agentx.jsonl}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ -n "${TRIALS:-}" ]; then
  cp "$TRIALS" "$WORK/trials.json"
else
  python3 -m kvevac.planner_trials export --trace "$TRACE" --out "$WORK/trials.json" \
    --snapshots "${SNAPSHOTS:-14}"
fi
# Offline prediction of the sweep (no AWS): kept next to the run for the write-up.
SAVE="${KVEVAC_RUNS:-$HOME/kvevac-runs/planner}/inputs-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$SAVE"
cp "$WORK/trials.json" "$SAVE/"
python3 -m kvevac.planner_trials preview "$WORK/trials.json" >"$SAVE/preview.json"
echo "trials and offline preview saved in $SAVE"

mkdir -p "$WORK/src/kvevac"
cp kvevac/planner_trials.py "$WORK/src/kvevac/"
cp jobs/aws/planner_job.sh "$WORK/trials.json" "$WORK/src/"
tar -C "$WORK/src" -czf "$WORK/code.tgz" .

# Memory node user-data: peer_node.sh with its own cap, plus code.tgz written into the
# NFS export right after it is mounted.
python3 - "$WORK/code.tgz" "$WORK/peer.sh" "$MAX_MIN" <<'PY'
import base64, sys
code, out, max_min = sys.argv[1:4]
lines = open("jobs/aws/peer_node.sh").read().splitlines()
payload = base64.encodebytes(open(code, "rb").read()).decode().rstrip()
result = []
for line in lines:
    if line.startswith('MAX_MIN="${KVEVAC_MAX_MIN'):
        line = f'MAX_MIN="{int(max_min) + 15}"'
    result.append(line)
    if line.strip() == "chmod 777 /export":
        result += ["base64 -d >/export/code.tgz <<'KVEVAC_CODE'", payload, "KVEVAC_CODE"]
text = "\n".join(result) + "\n"
assert "/export/code.tgz" in text, "peer_node.sh changed; payload not inserted"
assert len(text) < 16384, f"memory-node user-data is {len(text)} bytes"
open(out, "w").write(text)
PY

export KVEVAC_JOB=planner PEER_USER_DATA="$WORK/peer.sh" MAX_MIN \
  INSTANCE_TYPE="${INSTANCE_TYPE:-g6e.2xlarge}" ON_DEMAND_PRICE="${ON_DEMAND_PRICE:-2.242}" \
  PHASE3_CPU_GB="${PHASE3_CPU_GB:-36}" PLANNER_RUN_MIN="$((MAX_MIN - 45))" \
  KVEVAC_RUNS="${KVEVAC_RUNS:-$HOME/kvevac-runs/planner}"
if [ "${DRY:-0}" = 1 ]; then  # stop before launching anything (tests)
  cp "$WORK/peer.sh" "${DRY_OUT:-/dev/stdout}"
  exit 0
fi
bash jobs/aws/two_node.sh
