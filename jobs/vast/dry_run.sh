#!/usr/bin/env bash
# Run onstart.sh end to end on a CPU machine: fake GPU, fake vLLM, local git remote.
# Verifies the plumbing (clone, measure, fit, push to a branch) before paying for a GPU.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone -q --bare "$ROOT" "$TMP/remote.git"
mkdir -p "$TMP/bin"
cat > "$TMP/bin/nvidia-smi" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *query-gpu* ]]; then echo "NVIDIA FAKE-GPU"; else echo "fake nvidia-smi"; fi
SH
chmod +x "$TMP/bin/nvidia-smi"

PATH="$TMP/bin:$PATH" WORK_DIR="$TMP/work" REPO_URL="$TMP/remote.git" SKIP_INSTALL=1 \
  HF_TOKEN=dry-run GH_TOKEN=dry-run MODEL=fake-model JOB_TIMEOUT_MIN=10 \
  VLLM_CMD="python3 $ROOT/jobs/vast/fake_vllm.py --port 8000" \
  bash "$ROOT/jobs/vast/onstart.sh" || true

BRANCH="$(git --git-dir="$TMP/remote.git" branch --list 'calibration/*' --format='%(refname:short)' | head -1)"
[ -n "$BRANCH" ] || { echo "DRY RUN FAILED: no calibration branch pushed"; exit 1; }
echo "pushed branch: $BRANCH"
git --git-dir="$TMP/remote.git" ls-tree -r --name-only "$BRANCH" | grep results/calibration
for f in prefill.json fit.json env.json job.log interference-host.json interference-h2d.json; do
  git --git-dir="$TMP/remote.git" ls-tree -r --name-only "$BRANCH" | grep -q "/$f$" \
    || { echo "DRY RUN FAILED: missing $f"; exit 1; }
done
echo "DRY RUN OK"
