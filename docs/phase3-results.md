# Phase 3: the deadline write-back plugin on a real GPU (7 October 2026)

`kvevac/vllm_plugin` running inside vLLM 0.31.0 (whose tiering code is identical to the
`34051ad` commit the plugin was written against) on one on-demand `g6e.xlarge` (L40S)
in us-east-2, with Llama-3.1-8B. The test is `kvevac/vllm_plugin/gpu_test.py`,
launched with `KVEVAC_JOB=phase3 bash jobs/aws/kvevac-aws.sh`. Raw results are in
`results/phase3/`.

**Setup: a single-node stand-in for a reclaim.** Three vLLM processes share one
filesystem tier:
- **A**, deferred mode, serves turn 1 of two agent sessions.
- An emulated 120 s termination notice triggers the plugin's deadline flush, then A is
  SIGKILLed.
- **B** is a fresh process on the same tier and serves turn 2, restoring the session
  prefixes.
- **C** is a fresh process on an empty tier and serves the same turn 2 cold.

## 1. The mechanism works

Run 2, tier on the instance's local NVMe:

| check | result |
|---|---|
| deferred mode keeps session KV off the tier before the notice | **0 files** in the tier after turn 1 |
| flush on notice (planner order, deadline 120 s) | both sessions planned complete; **4,851 / 4,851 blocks confirmed**, 10.17 GB |
| flush time: planner projection vs actual | **46.5 s projected, 49.2 s actual** (6% over), from the measured 0.22 GB/s tier write |
| restore in a fresh process (B), from the tier only | worked: turn 2 served after A was killed |
| **output parity**: B's greedy output vs. cold recompute (C) | **identical for both sessions** |

The first run (`run1/`) got as far as the flush, with identical flush numbers. Its
process B could not start: the SIGKILLed A had left its 14 GB CPU-tier region in
`/dev/shm`. On a real reclaim the machine is gone, so the test now removes it.

The parity prompts are random words from a 50-word vocabulary, and the greedy outputs
are repetitive. Parity here shows bit-identical decoding from restored vs. recomputed
KV, not answer quality on real text.

## 2. When restore beats recompute depends on the tier

| tier | tier write | session | turn-2 prompt | TTFT restored (B) | TTFT cold (C) | restored ÷ cold |
|---|---|---|---|---|---|---|
| local NVMe (run 2) | 0.22 GB/s | s-long | 58,784 tok | 19.38 s | 9.33 s | 2.08× slower |
| local NVMe (run 2) | 0.22 GB/s | s-short | 22,000 tok | 6.63 s | 2.37 s | 2.79× slower |
| RAM / tmpfs (run 3) | 2.18 GB/s | s-long | 40,052 tok (turn 1) | no result | no result | — |
| **peer DRAM over the network** (two nodes, 8 Oct) | 1.30 GB/s | s-long | 58,784 tok | **8.31 s** | 9.11 s | **1.10× faster** |
| **peer DRAM over the network** (two nodes, 8 Oct) | 1.30 GB/s | s-short | 22,000 tok | 2.94 s | 2.39 s | 1.23× slower |

On the instance NVMe, restore moves about 0.39–0.40 GB/s end to end (7.5 GB in 19.4 s;
2.7 GB in 6.6 s). The L40S recomputes 57k tokens in about 9 s, which is equivalent to
0.83 GB/s of 8B KV. **So restore loses below roughly 0.8 GB/s and wins above it.**
This reproduces ShuntServe's finding that recompute usually wins on g6/g6e, as a
function of tier bandwidth rather than as a blanket claim.

**Run 3 tried to test a fast tier and failed.** It put the tier in RAM (tmpfs, 2.18
GB/s write). After turn 1 (40k- and 14k-token sessions, cold TTFT 5.34 s and 1.34 s)
the instance went silent during the flush and was deleted by its 60-minute spending
cap. The most likely cause is memory: a 9 GB tmpfs tier plus an 8 GB shared-memory
CPU tier plus the vLLM process on a 32 GiB instance with no swap. A g6e.xlarge is too
small to emulate a fast tier in its own RAM. The fast-tier case needs either two
instances (a peer's DRAM over the NIC, the real deployment shape) or a larger instance.

## 2b. Two nodes: evacuate to, and restore from, a peer's DRAM (8 October)

`jobs/aws/two_node.sh`: a CPU memory node (r7i.xlarge) exports 20 GB of RAM over
NFS (`nconnect=8`) in the same zone as the L40S node. The plugin's flush and the
restore both cross the network, which is the deployment shape: a surviving peer's
DRAM tier. Raw data is in `results/phase3/two-node-peer-dram-20261008/`.

| check | result |
|---|---|
| deferred mode, tier before the notice | 0 files |
| flush to the peer, 120 s deadline | **4,851 / 4,851 blocks (10.17 GB) confirmed in 6.6 s** (projected 7.8 s) |
| restore in a fresh process, from the peer's RAM | worked |
| output parity vs. cold recompute | **identical for both sessions** |
| TTFT, 58.8k-token turn 2 | **8.31 s restored vs. 9.11 s cold (1.10× faster)** |
| TTFT, 22k-token turn 2 | 2.94 s restored vs. 2.39 s cold (slower) |

- **The evacuation side is easy.** At network speed, all 10 GB of both sessions left
  the "reclaimed" node in 6.6 s, about 5% of AWS's 2-minute notice. For a node like this
  the planner has nothing to choose (ρ ≫ 1). That matches the characterization (§2 of
  phase1c-results) and the positioning doc's warning that the planner only matters on
  big nodes or short notices.
- **The restore side sits at the crossover** for an 8B model on an L40S. Restore runs at
  about 0.9 GB/s end to end (7.5 GB in about 8.3 s). That is above recompute's ~0.83
  GB/s equivalent, so the long session wins, narrowly. The short one loses to fixed
  promotion overheads. Upstream's promotion path (NFS read → CPU tier → GPU, in
  scheduler-step batches), not the network, is the bottleneck: the same mount took
  writes at 1.3–1.5 GB/s.
- **For the claims:** evacuation is a sure win for *preserving* the KV within the
  notice. Whether *restoring* it beats recompute depends on model size, context length
  and restore path. For 8B on L40S it is roughly break-even. It tips toward restore for
  larger models (2.5× the KV but ~8.75× the prefill compute per token at 70B), longer
  contexts, or a faster restore path (e.g. NIXL P2P into GPU memory).

## 2c. Tight budget: the flush must truncate (13 October, L4)

The gap the paper admits is that no GPU run had ρ < 1. On-demand L40S was unavailable in
every zone of us-east-1 and us-east-2 for 85 minutes, so this ran on an **L4**
(g6.xlarge) with the same two-node setup (CPU memory node over NFS). Settings: four
sessions served in order s4, s3, s2, s1 (2k, 4k, 7k and 12k tokens; ~3.6 GB of KV), a
**30 s notice**, and the GPU node's egress capped at **320 Mbit/s** (tc) while process A
evacuated, so only about 1.1 GB could leave (ρ ≈ 0.3). Restore and the cold baseline ran
uncapped. Raw data: `results/phase3/tight-budget-l4-20261013/`.

| check | result |
|---|---|
| flush plan | s4 and s3 complete, **s2 partial (first 147 blocks)**, s1 skipped |
| blocks submitted / confirmed | 529 / 529 (1.11 GB) |
| flush time, projected vs actual | **27.9 s vs 28.0 s** |
| finished before the 30 s deadline | **yes, by 2.0 s** (the planner's safety margin) |
| output parity, restored vs cold | s4 ✓, **s2 (partial) ✓**, s1 (skipped) ✓, **s3 ✗** |

- **The deadline mechanism works under a binding budget.** The flush cut exactly where
  the budget ran out, mid-session, finished within 0.1 s of its projection, and all
  submitted blocks landed before the deadline.
- **A partially evacuated session restores correctly.** s2's head (147 blocks) was
  restored and the rest recomputed, and its greedy output matched cold recompute.
- **s3's divergence is a floating-point tie, not corrupted KV (settled by a repeat).**
  A second run with identical settings (`results/phase3/tight-budget-l4-repeat-20261013/`)
  reproduced everything: the same flush plan, 529/529 blocks, 2.0 s before the deadline,
  and parity for s4, s2 and s1. s3 again diverged at its second token, and this time the
  test recorded top-2 logprobs. In the cold run the two candidates were **exactly
  tied**: " notice" −3.0773 and " disk" −3.0773. Restored and cold logprobs differ by
  0.01–0.05 throughout, the size of bf16 noise between prefill on a restored prefix and
  a full prefill. That is enough to flip an exact tie, and the flip reversed between the
  runs (restored "notice" in the first, "disk" in the second), which corrupted KV would
  not do. The partially restored s2 tracks cold within ~0.02 per token. **Restored KV is
  numerically equivalent to recomputed KV; greedy output parity holds except at exact
  logit ties.**
- **What the planner chose.** These sessions (2k–12k tokens) are far shorter than the
  length at which restoring 8B KV beats recomputing it (about 54k tokens with the
  measured L40S prefill and 0.9 GB/s restore), so every restore was valued ≤ 0 and the
  order fell back to serving order. This run validates truncation, deadline compliance
  and partial restore, not value-based choices. Testing those needs sessions above the
  crossover, which the AgentX trace has; 8B is enough, 70B is not required.

## 3. What this means for the claims
- The Phase 3 design is implementable out of tree, against vLLM's real tiering code,
  without a fork, and it is correct (parity).
- The planner's flush-time projection holds on real hardware (6% error), so the
  deadline budget is trustworthy.
- Whether evacuated KV is *worth restoring* depends on the destination tier's
  bandwidth relative to the GPU's prefill speed. The simulator already models this
  (`save_value_s` subtracts reload time for remote stores). With the measured
  constants, slow tiers make evacuation worthless for 8B on L40S. Fast tiers (peer
  DRAM over a 25–100 GbE NIC, a DRAM pool) or bigger models are where it pays. A 70B
  model has 2.5× the KV per token of 8B but about 8.75× the prefill compute per token,
  so on the same GPU budget its crossover tier bandwidth is several times lower.

## 4. Not yet tested
- A real FIS reclaim instead of SIGKILL (needs spot capacity), and NIXL P2P restore
  straight into a peer's GPU instead of NFS.
- Hybrid mode under real backpressure.
- `on_schedule_end` on an engine with nothing in flight. The test kept the scheduler
  stepping with one-token wake requests.
