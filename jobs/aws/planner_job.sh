# Planner trials on the GPU node (kvevac.planner_trials run). Sourced by instance_job.sh
# after the memory node's NFS export is mounted at $TIER_BASE; it arrives, with
# kvevac/planner_trials.py and trials.json, in the memory node's code.tgz because the
# GPU node's user-data is full (jobs/aws/planner.sh packs it).
#
# vLLM keeps its CPU tier in /dev/shm, whose default size is half of RAM; the trials
# want 36 GiB of it on a 64 GiB g6e.2xlarge.
mount -o remount,size="$(( ${PHASE3_CPU_GB:-36} + 8 ))G" /dev/shm
IFACE="$(ip route get "${PEER_IP:?}" | sed -n 's/.* dev \([^ ]*\).*/\1/p' | head -1)"
event planner "nic $IFACE; $(grep -c '"snapshot"' "$ROOT/src/trials.json") snapshots"
"$PYTHON" -m kvevac.planner_trials run --trials "$ROOT/src/trials.json" \
  --tier "$TIER_BASE/kvevac-tier" --out "$OUT" --logs "$ROOT" --python "$PYTHON" \
  --model "$MODEL" --cpu-gb "${PHASE3_CPU_GB:-36}" --iface "$IFACE" \
  --max-minutes "${PLANNER_RUN_MIN:-300}"
