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
- Two machines: evacuation over a real NIC to a peer's tier (llm-d-style P2P), and a
  real FIS reclaim instead of SIGKILL.
- Hybrid mode under real backpressure.
- `on_schedule_end` on an engine with nothing in flight. The test kept the scheduler
  stepping with one-token wake requests.
