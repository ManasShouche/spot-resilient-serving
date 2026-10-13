# Spending the Spot Notice: Deadline-Bounded Evacuation of Agent-Session KV Caches

*Workshop-paper draft (about 4 pages). Target venues: EuroMLSys, or an MLSys/NeurIPS
systems workshop. Every number cites a results file in this repository and is marked
simulated (S), simulated with measured constants (C), or measured on hardware (M).*

## Abstract

Agentic LLM workloads keep tens of thousands of tokens of KV cache per session alive
*between* turns. When a spot GPU node is reclaimed, that cache is lost silently: no
request fails, but every later turn of every resident session pays a full re-prefill.
Existing fault-tolerance systems protect in-flight requests, and agent-KV systems
protect idle sessions only against eviction. Replaying 393 real Claude Code sessions,
we find that 75–78% of a large serving node's resident KV belongs to sessions with no
turn in flight (S). We treat the cloud's termination notice as a budget and plan which
session caches to save, and where, under a deadline, bandwidth and failure domains.

In simulation calibrated on an NVIDIA L40S, on-notice evacuation recovers 47–52% of
reclaim-induced recompute at a 2-minute notice with zero steady-state cost, within
5–10 points of continuous replication (C). When replication's DRAM is instead given
to the primary cache (equal memory), evacuation still recovers about half, while
replication does worse than doing nothing (S). We implement the policy as an
out-of-tree plugin for vLLM's tiered KV offloading. On AWS it evacuates 10.2 GB of
session KV from an L40S node to a CPU memory node's DRAM (served over NFS) in 6.6 s, and
restores it with greedy output identical to recomputation (M). Restore and recompute
are at parity for 8B on L40S: 8.3 s vs 9.1 s TTFT at 59k tokens and 2.9 s vs 2.4 s at
22k, single runs (M). We report this as a crossover, not a win.

## 1. Introduction

Serving agents is dominated by long, multi-turn sessions. In the AgentX corpus of 393
Claude Code sessions, median input context is about 89k tokens, sessions have a median
of 70 requests, and the median session lasts 1.8 h (§4). Providers increasingly put
inference on preemptible capacity, which AWS reclaims with a 2-minute notice (Azure
and GCP give 30 s).

What does a reclaim cost? Systems from SpotServe to ShuntServe, KevlarFlow, LUMEN and
GhostServe answer for the **in-flight request**. They restart it, migrate it, or
replicate its KV continuously. For agentic serving this misses the main asset: the
**idle session prefix**. It is not running, so losing it fails nothing, but the next
turn silently re-prefills 50–100k tokens. Agent-KV systems (Continuum, CacheScout,
KVFlow) do manage idle prefixes, but against *eviction* on a live node, not node loss.

**Contributions.**
1. *Characterization* (§4): on a large node, 75–78% of resident KV is not running, and
   about a third belongs to sessions that never return.
2. *A deadline-bounded evacuation planner* (§3): a knapsack over in-flight and idle KV
   objects with release times, per-destination ingress, failure domains and P(reuse).
   It generalises ShuntServe's stated future work from in-flight requests to sessions.
3. *A regime map* (§5): when evacuation matches continuous replication, when it beats
   it (equal memory, shared-store bandwidth), and when it cannot help (W = 0).
4. *A vLLM prototype* (§6), out of tree, with deferred cascades and a deadline flush,
   evaluated on a real L40S, flushing to local NVMe and to a separate CPU memory node
   over the network, with output parity. The hardware runs exercise the mechanism; the
   planner's choices under a tight budget are evaluated only in simulation.

**Not claimed.** Predicting preemption (Parcae, SkyNomad, hazardserve); exploiting
correlated preemption (SkyServe); that KV transfer generally beats recompute
(ShuntServe measured the opposite on g6/g6e, and so do we on slow tiers); a better
reuse predictor (CacheScout, Continuum).

## 2. Background and related work

| system | protects | when it pays | uses the notice | idle session KV |
|---|---|---|---|---|
| SpotServe, ShuntServe | in-flight requests | at or after the notice | yes | no |
| KevlarFlow, LUMEN, GhostServe | in-flight KV | continuously | no | no |
| hazardserve | in-flight, speculatively | before the notice | no | no |
| Mooncake store, llm-d P2P | session prefixes | continuously | no | yes, but lost with the node holding them |
| Continuum, CacheScout | idle sessions | steady state | n/a | yes, against eviction only |
| **this work** | **idle and in-flight session KV** | **at the notice** | **yes, as a budget** | **yes, against node loss** |

llm-d's graceful shutdown drains in-flight requests only. Its P2P sharing is the
natural restore path for evacuated blocks, but assumes the peer survives.

## 3. Design

**Budget.** A notice of W seconds and an egress bandwidth B define a budget; the KV
resident on the node is R. We call ρ = W·B / R the budget ratio. When ρ ≥ 1 everything
fits and planning is trivial. When ρ < 1 the planner decides.

**Planner** (`kvevac/planner.py`). Objects are in-flight requests (which may finish
locally if their remaining decode fits in W) and idle session prefixes. Each has a
size, a recompute cost r(c) = c/p·(1 + c/2k), and P(reuse). Value is P(reuse)·(r(c) −
reload). Destinations carry a failure domain, free capacity and an ingress already
booked by other evacuating nodes. Peers in the reclaim wave are excluded. A greedy pass
by value density on one serial egress pipe, with release times, places each object on
the destination that finishes it before the deadline at the highest value. Leftover
time can carry partial prefixes, since a prefix is usable from the front.

**Block order** (`kvevac/flush.py`). Sessions expand into vLLM block-hash chains, in
prefix order, deduplicated across shared system prompts, and truncated to budget.

**vLLM plugin** (`kvevac/vllm_plugin`). vLLM's tiered offloading cascades every stored
block to all secondary tiers (write-through), and drops cascades under backpressure.
Our `DeadlineTieringOffloadingSpec` loads out of tree, with no fork, and adds:
*deferred* mode, where blocks stay in the CPU tier and are tracked per agent session
(`kv_transfer_params`); *hybrid* mode, write-through where backpressure admits and
dirty-tracking where it drops; and `flush_for_deadline`. On notice, a handler writes a
flush request *before* pausing admission. The scheduler-side manager plans, submits
store jobs through vLLM's own `create_store_job`/`submit_store` path, and reports.
Restore needs nothing new: a later request finds the blocks by hash.

## 4. Characterization (simulated, real sessions)

A discrete-event simulator of a 12-node fleet in 3 failure domains replays the AgentX
corpus, resampled with replacement to a load whose median TTFT matches a calibrated
baseline. Real sessions are about 3× longer than a generator fitted to the same
marginals, so equal session counts would have overloaded the fleet. We snapshot every
node in steady state (`results/trace/value_at_risk.md`):

| node | resident KV p50 | not running (p50) | returning share of rebuild cost |
|---|---|---|---|
| 8B, 4M-token cache | 441 GB | **78%** | 66% |
| 70B on 4×H100, 4M-token cache | 1,095 GB | **75%** | 68% |
| 8B on g6e.xlarge, 400k-token cache | 33 GB | 100% | 100% |

Three-quarters of what a reclaim destroys is outside the reach of in-flight fault
tolerance. A third of it is dead weight that a planner should skip. And a single
g6e.xlarge sits at ρ ≥ 1 in every snapshot: small nodes need no planner.

## 5. Regime map (simulated; calibrated where marked)

Excess prefill GPU-seconds caused by reclaims, as Δ vs. no reaction (recompute).
Paired seeds, 95% t-intervals of ±5–40 points.

**Against related work, on real sessions with measured L40S constants** (C;
`results/phase2/calibrated-trace/`):

| policy | indep. W=30 s | indep. W=120 s | corr. W=30 s | corr. W=120 s | steady egress |
|---|---|---|---|---|---|
| evacuate (ours) | −14% | **−52%** | −10% | **−47%** | 0 |
| session write-through | −63% | −59% | −55% | −50% | ~50 TB |
| hybrid (ours + write-through) | −71% | −66% | −51% | −56% | ~50 TB |
| in-flight replication (KevlarFlow-style) | −31% | −29% | −27% | −30% | ~584 TB |

**Where evacuation wins** (S, synthetic sessions, `results/phase1b/`):
- *Equal memory.* If the DRAM write-through would spend on replicas goes to the
  primary cache instead, evacuation reaches −50% (independent) and −46% (correlated)
  at W = 120 s, while write-through *worsens* reclaim cost by +84% to +94%, because
  halving the primary cache costs more in steady-state misses than replicas save at
  reclaim. This holds only under that memory constraint; with spare DRAM (table above)
  write-through is the strongest single policy.
- *A shared store.* With one ~1 GB/s store shared by 12 nodes (83 MB/s each),
  write-through drops bursts and falls to −25%. Evacuation holds −43% and hybrid −51%.

**Where it cannot help.** At W = 0 evacuation does nothing, by construction. At W = 30 s
it recovers only 10–27%.

**What does not matter much.** An oracle reuse predictor adds no significant benefit
over recency on real sessions (S, `results/trace/hinted.md`). A synthetic-only finding
that failure-domain-blind pools are fragile under correlated reclaims did **not**
replicate on real sessions, and we retract it.

## 6. Prototype on real GPUs (measured)

**Calibration** (`results/phase2/`). On an L40S with Llama-3.1-8B and vLLM 0.31.0:
cold prefill runs at 16,011 tok/s with a 20.5k-token attention knee (the fit is within
1% from 32k to 120k tokens), decode at 46.7 tok/s. Receiver-side interference from 1 to
16 GB/s of incoming KV traffic is 0–3%, removing the assumption that most threatened
evacuation in simulation.

**Mechanism** (`results/phase3/`). Two agent sessions (57k and 20k tokens). Process A
runs in deferred mode, flushes on an emulated 120 s notice, and is SIGKILLed. A fresh
process restores turn 2 from the tier; another computes it cold.

| tier | flush (10.17 GB) | projected | parity | TTFT restored / cold, 59k | 22k |
|---|---|---|---|---|---|
| local NVMe | 49.2 s | 46.5 s | ✓ | 19.4 / 9.3 s | 6.6 / 2.4 s |
| CPU memory node's DRAM over NFS (two nodes) | **6.6 s** | 7.8 s | ✓ | 8.3 / 9.1 s | 2.9 / 2.4 s |

The two-node setup is a stand-in for a surviving peer: the destination is an
r7i.xlarge CPU instance exporting 20 GB of RAM over NFS (`nconnect=8`) in the same
zone, not a second GPU server, and NFS into vLLM's CPU tier is not the restore path a
production system would use.

Deferred mode left the tier empty until the notice in every run. The planner's flush
projection was within 6–15%. Restored KV decoded identically to recomputed KV under
greedy decoding; the prompts are random words and the outputs repetitive, so this
checks KV correctness, not answer quality.

**The planner had nothing to decide.** Both sessions fit in 6.6 s of a 120 s notice
(ρ ≫ 1), so every run saved everything. These runs validate the flush mechanism and
the planner's time projection, not its choices; the value of planning when ρ < 1
rests on the simulation in §5. A hardware test of that needs a larger node, a
throttled link, or a 15–30 s notice.

**Restore vs. recompute.** On local NVMe (~0.4 GB/s end to end) restore loses by
2–3×. From the memory node (~0.9 GB/s end to end, limited by vLLM's promotion pipeline
rather than the 1.3–1.5 GB/s network) it is 9% faster at 59k tokens and 23% slower at
22k. Each figure is a single run. Cold TTFT for the same 59k prompt was 9.33 s and
9.11 s on two different instances, so run-to-run spread is a few percent and the 59k
gap is suggestive, not established; we call it parity. This agrees with the arithmetic:
for 8B on L40S, recompute costs the equivalent of ~0.83 GB/s of KV, close to the
measured restore rate. We expect larger models to favour restore, since a 70B model
has 2.5× the KV per token but about 8.75× the prefill compute, but this is reasoning,
not measurement.

## 7. Discussion and limitations

- **The simulator is a model.** It has no memory-based admission control, an
  approximate prefill-queue contention model, and assumed network constants. Policy
  differences under about 20 points are within noise.
- **No real reclaim yet.** Spot g6e capacity was unavailable throughout (placement
  score 1/10 in three US regions), so FIS notice timing is unmeasured and the GPU tests
  emulate the reclaim with SIGKILL.
- **The planner's choices are untested on hardware.** One L4 run forced ρ ≈ 0.3 (egress
  cap, 30 s notice). The flush truncated mid-session, finished 2 s before the deadline
  (within 0.1 s of projection), and a partially evacuated session restored with output
  parity. One complete session diverged at its second token, which we attribute,
  unverified, to a floating-point near-tie. Its sessions (2k–12k tokens) were below the
  ~54k-token length where restoring 8B KV beats recomputing it, so every restore was
  valued ≤ 0 and value-based choices remain untested (`docs/phase3-results.md` §2c).
- **Single runs.** The GPU timings have no repeats or error bars.
- **Small models are the hard case for restore.** The prototype's GPU results are for
  8B. The value of saving KV, and the crossover, should be measured at 70B on
  multi-GPU nodes, where both the at-risk KV and the recompute cost are an order of
  magnitude larger.
- **Restore path.** The "peer" was a CPU memory node serving RAM over NFS into vLLM's
  CPU tier. A surviving GPU peer reached by NIXL P2P into GPU memory would remove the
  promotion bottleneck, and is unmeasured.

## 8. Conclusion

In agentic serving, most of the state a spot reclaim destroys is idle session KV that
no existing fault-tolerance mechanism protects. The termination notice is enough to
move it: 10 GB in under 7 s on commodity cloud networking, planned against the
deadline, and restored with output identical to recomputation. Whether moving it
*pays* is a crossover in model size, context length and restore bandwidth. For 8B on
an L40S we measured parity; the larger-model side of the crossover is the next
measurement, not a result.

## Artifacts
Code, results and the AWS harness: `kvevac/`, `results/`, `jobs/aws/`. Reproduction
commands are in `docs/phase1c-results.md`, `docs/phase2-results.md` and
`docs/phase3-results.md`.
