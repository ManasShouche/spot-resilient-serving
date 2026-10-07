# Phase 1c: related-work baselines, value at risk, and how much reuse prediction matters

**All numbers are simulated** with assumed hardware constants (`kvevac/profiles.py`,
8B on L40S, 25GbE) and the synthetic AgentX-calibrated workload, with 6 paired seeds
and 95% t-intervals. Raw tables: `results/baselines/`, `results/characterize/`.
Reproduce with:

```bash
python -m kvevac.experiments baselines --seeds 6 --out results/baselines
python -m kvevac.experiments hinted    --seeds 6 --out results/baselines
python -m kvevac.characterize          --seeds 3 --out results/characterize
```

This round answers the three reviewer questions the positioning doc predicted
(docs/positioning.md §4–5): *why not just use KevlarFlow-style replication, or a
Mooncake-style pool? Is the idle-session asset real? Is reuse prediction the lever?*

## 1. Related-work baselines (experiment 4)

Excess prefill GPU-seconds caused by reclaims, as Δ% vs. doing nothing (recompute).
Replicas and pool shards all get the same 4M-token tier per node.

| policy | indep. W=0 | indep. W=30s | indep. W=120s | corr. W=0 | corr. W=30s | corr. W=120s | steady-state egress (GB) |
|---|---|---|---|---|---|---|---|
| evacuate (ours, zero steady-state cost) | 0% | −27% | −52% | 0% | −14% | −44% | 0 |
| replicate (session write-through) | −59% | −68% | −69% | −53% | −54% | −56% | ~42k |
| hybrid (ours + write-through) | −59% | −72% | −62% | −53% | −60% | −60% | ~43k |
| inflight_replicate (KevlarFlow/LUMEN-style) | −20% | −22% | −17% | −13% | −30% | −21% | **~595k** |
| pool, 1 copy (Mooncake-style) | −58% | −51% | −47% | **−32%** | −51% | −49% | ~25k |
| pool, 2 copies | −55% | −61% | −69% | −44% | −62% | −52% | ~69k |

What it shows:
- **Replicating in-flight requests is the wrong unit for agentic workloads.** It
  protects running turns (−13% to −30%) but not the idle prefixes that hold most of
  the value (§2). Its copy is released when the turn ends, so every turn re-ships its
  whole ~90K-token context. That comes to about 14× the egress of session
  replication. KevlarFlow's 2–4% overhead was measured on ShareGPT-sized requests and
  doesn't transfer.
- **A pool that ignores failure domains is fragile under correlated reclaims.** With
  one copy placed by hashing, a 0 s-notice correlated wave takes it down to −32%,
  against −53% for replication across failure domains. A second copy restores most
  of it but costs 2.8× the egress of one copy. That is the operational case for making
  placement (and evacuation) failure-domain-aware.
- **Evacuation needs notice.** At W=0 it can do nothing (the honest boundary). By
  W=120s it reaches −44% to −52% with zero steady-state cost. Paired with
  write-through (hybrid), it is the best or tied-best row at 30 s.

## 2. Value at risk per node (contribution 1, characterization)

| node | resident KV GB, p50 / p90 | idle share of GB, p50 | rebuild GPU-s, p50 | returning share, p50 | ρ<1 at 25GbE, W=30 s / 120 s |
|---|---|---|---|---|---|
| 8B on L40S, 4M-token cache | 512 / 524 | 62% | 1270 | 64% | 100% / 100% |
| 8B on g6e.xlarge, 400k-token cache | 43 / 51 | 63% | 100 | 73% | 0% / 0% |
| 70B on 4×H100, 4M-token cache | 1279 / 1309 | 55% | 1082 | 66% | 100% / 100% |

Steady state (1–4 h of a 4 h arrival window), no reclaims. Hot means running or
active in the last 60 s.

- **Most of the KV at risk is idle.** About 55–63% of a node's resident KV belongs to
  sessions that are neither running nor recently active. Every fault-tolerance system
  in docs/positioning.md §3 protects only the other 37–45%.
- **About a third of it is dead weight.** Only 64–73% of the rebuild cost belongs to
  sessions that really send another turn. Under a deadline, an evacuation planner
  should skip the rest, which is why it weighs objects by P(reuse).
- **The planned testbed is in the trivial regime, now quantified.** On a g6e.xlarge,
  everything fits in the notice 100% of the time (ρ ≥ 1), so every evacuation policy
  looks the same. Large nodes are below ρ = 1 100% of the time. The Phase 4 two-node
  prototype must therefore emulate a short notice and throttle the NIC (positioning
  §4.1). Real g6e runs can only validate mechanism and constants, not the planner.

## 3. How good must reuse prediction be? (hinted estimator)

`ReuseModel.HINTED` returns the oracle answer with probability *a*, otherwise the
recency estimate. It stands in for metadata predictors (CacheWise, Continuum,
CacheScout) without claiming one. Evacuate vs. recompute, on 10GbE:

| hint accuracy | 0.0 (recency) | 0.5 | 0.8 | 0.95 | 1.0 (oracle) |
|---|---|---|---|---|---|
| W = 30 s | −14% | −22% | −25% | −23% | −22% |
| W = 120 s | −41% | −37% | −45% | −44% | −47% |

The intervals are ±16–30 points and overlap throughout. **Reuse prediction is a
second-order lever.** A perfect oracle adds 6–8 points, within noise at 6 seeds. This
fits the real-trace finding that LRU is hard to beat (agentic-kv-cache: liveness
policies did not beat LRU-leaf). The paper should treat the reuse estimator as a
pluggable input, not a contribution, and the SOP should not lean on prediction.

## 4. What changed in the model (for reviewers of the code)
- New policies `inflight_replicate` and `pool`, and the `variants` rows mechanism.
  The five Phase 1b policies are bit-identical to before (checked on four settings).
- New metrics: `displaced_ttft_p50/p99_s`, the TTFT of a session's first turn after
  its node is reclaimed (where survivor overload shows), and `replica_refusals`.
- Known simplifications: no memory-based admission control (hence the scaled-down
  g6e load in §2), and pool fetches use the fleet link with no contention.

## 5. Next
1. Re-run §1–§3 on the real AgentX trace (`--trace`) once it is downloaded.
2. Phase 2 run on AWS (runner ready; needs one manual launch), then
   `--calibration` reruns.
3. First GPU test of the Phase 3 plugin (docs/phase3-design.md, "Prototype status").
