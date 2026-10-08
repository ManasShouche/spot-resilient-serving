# Phase 1c: related-work baselines, value at risk, and how much reuse prediction matters

**All numbers are simulated** with assumed hardware constants (`kvevac/profiles.py`,
8B on L40S, 25GbE), 6 paired seeds, 95% t-intervals. Each experiment ran on two
workloads:

- **synthetic**: the AgentX-calibrated generator, 800 sessions arriving over 2 h
  (`results/baselines/`, `results/characterize/`);
- **real trace**: the SemiAnalysis AgentX corpus (393 Claude Code sessions, 68,266
  requests, Apache-2.0), resampled with replacement (`results/trace/`).

**Load matching.** Real sessions last about 3× longer than synthetic ones (median
1.8 h vs. 0.6 h; the tail runs to 255 h), so equal session counts are not equal load.
At 800 trace sessions the fleet saturates (median TTFT 6.7 s vs. 0.3 s synthetic). The
trace runs use **250 sessions per 2 h** (500 per 4 h for §2), which matches the
synthetic run's no-reclaim median TTFT (0.33 s vs. 0.30 s). Real sessions also have a
lower cache hit rate (0.93 vs. 0.985).

```bash
python -m kvevac.experiments baselines --seeds 6 --out results/baselines
python -m kvevac.experiments hinted    --seeds 6 --out results/baselines
python -m kvevac.characterize          --seeds 3 --out results/characterize
T=data/raw/agentx.jsonl   # huggingface.co/datasets/semianalysisai/cc-traces-weka-062126-256k
python -m kvevac.experiments baselines --seeds 6 --sessions 250 --trace $T --out results/trace
python -m kvevac.experiments hinted    --seeds 6 --sessions 250 --trace $T --out results/trace
python -m kvevac.characterize --seeds 3 --sessions 500 --trace $T --out results/trace
```

This round answers the three reviewer questions the positioning doc predicted
(docs/positioning.md §4–5): *why not just use KevlarFlow-style replication, or a
Mooncake-style pool? Is the idle-session asset real? Is reuse prediction the lever?*

## 1. Related-work baselines (experiment 4)

Excess prefill GPU-seconds caused by reclaims, as Δ% vs. doing nothing (recompute).
Each cell is **synthetic / trace**. Replicas and pool shards all get the same
4M-token tier per node. Half-widths of the 95% intervals are 7–40 points. Read
differences under about 20 points as ties.

| policy | indep. W=0 | indep. W=30s | indep. W=120s | corr. W=0 | corr. W=30s | corr. W=120s | steady-state egress (TB) |
|---|---|---|---|---|---|---|---|
| evacuate (ours, zero steady-state cost) | 0 / 0% | −27 / −15% | −52 / −49% | 0 / 0% | −14 / −8% | −44 / −46% | 0 / 0 |
| replicate (session write-through) | −59 / −65% | −68 / −63% | −69 / −64% | −53 / −52% | −54 / −53% | −56 / −52% | 42 / 50 |
| hybrid (ours + write-through) | −59 / −65% | −72 / −66% | −62 / −70% | −53 / −52% | −60 / −54% | −60 / −60% | 43 / 50 |
| inflight_replicate (KevlarFlow/LUMEN-style) | −20 / −35% | −22 / −33% | −17 / −36% | −13 / −24% | −30 / −22% | −21 / −24% | **596 / 584** |
| pool, 1 copy (Mooncake-style) | −58 / −68% | −51 / −68% | −47 / −73% | −32 / −53% | −51 / −54% | −49 / −54% | 25 / 44 |
| pool, 2 copies | −55 / −70% | −61 / −72% | −69 / −69% | −44 / −60% | −62 / −58% | −52 / −61% | 69 / 88 |

What holds on both workloads:
- **Replicating in-flight requests is the wrong unit for agentic workloads.** It
  protects running turns (−13% to −36%) but not the between-turn prefixes that hold
  most of the value (§2). Its copy is released when the turn ends, so every turn
  re-ships its whole context: 12–14× the egress of session replication. KevlarFlow's
  2–4% overhead was measured on ShareGPT-sized requests and doesn't transfer.
- **Evacuation needs notice.** At W=0 it does nothing (the honest boundary). At 30 s
  it recovers only 8–27%. At 120 s it reaches −44% to −52% with zero steady-state
  cost, within about 10–20 points of continuous replication. Hybrid (write-through
  plus evacuation of what replication missed) is the best or tied-best row.

What **does not** hold on the real trace:
- **Pool fragility under correlated reclaims was a synthetic-workload effect.** On
  synthetic sessions a 1-copy, failure-domain-blind pool fell to −32% in a 0 s
  correlated wave (against −53% for domain-aware replication). On the real trace it
  holds −53%, and the pool is the best or tied-best protected policy with the least
  egress of the replicating designs. Don't claim that failure-domain-blind pools are
  fragile without a real-trace result that shows it; a likely missing ingredient is
  memory pressure on the pool tier itself, which these runs don't stress.

## 2. Value at risk per node (contribution 1, characterization)

| node | workload | resident KV GB, p50 / p90 | not running, p50 / p10 | idle >60 s, p50 | rebuild GPU-s, p50 | returning share, p50 | ρ<1 at 25GbE, W=30 s / 120 s |
|---|---|---|---|---|---|---|---|
| 8B on L40S, 4M-token cache | synthetic | 512 / 524 | 69% / 53% | 62% | 1270 | 64% | 100% / 100% |
| | trace | 441 / 513 | **78% / 66%** | 74% | 1213 | 66% | 100% / 73% |
| 8B on g6e.xlarge, 400k-token cache | synthetic | 43 / 51 | 75% / 0% | 63% | 100 | 73% | 0% / 0% |
| | trace | 33 / 48 | 100% / 0% | 97% | 86 | 100% | 0% / 0% |
| 70B on 4×H100, 4M-token cache | synthetic | 1279 / 1309 | 61% / 46% | 55% | 1082 | 66% | 100% / 100% |
| | trace | 1095 / 1282 | **75% / 61%** | 72% | 1021 | 68% | 100% / 100% |

Steady state (1–4 h of a 4 h arrival window), no reclaims. "Not running" means KV of
sessions with no turn in flight, which is exactly what in-flight fault tolerance
leaves unprotected. The g6e.xlarge rows hold only 2–3 sessions, so their percentiles
are coarse.

- **Most of the KV at risk is not running, and real sessions make this stronger.** On
  large nodes, 75–78% of resident KV (trace; 61–69% synthetic) belongs to sessions
  with no turn in flight. Every fault-tolerance system in docs/positioning.md §3
  protects only the remainder.
- **About a third of it is dead weight.** Only 64–68% of the rebuild cost belongs to
  sessions that really send another turn. Under a deadline, an evacuation planner
  should skip the rest, which is why it weighs objects by P(reuse).
- **The planned testbed is in the trivial regime, now quantified.** On a g6e.xlarge,
  everything fits in the notice (ρ ≥ 1) in every snapshot, so every evacuation policy
  looks the same. Large nodes sit at ρ < 1 73–100% of the time. The Phase 4 two-node
  prototype must therefore emulate a short notice and throttle the NIC (positioning
  §4.1). Real g6e runs can validate mechanism and constants, not the planner.
- A methodological note for the paper: at equal *session count* the trace saturated
  the fleet, and queued turns then showed up as "running" (0% not running). Load
  must be matched on utilization, not on session count.

## 3. How good must reuse prediction be? (hinted estimator)

`ReuseModel.HINTED` returns the oracle answer with probability *a*, otherwise the
recency estimate. It stands in for metadata predictors (CacheWise, Continuum,
CacheScout) without claiming one. Evacuate vs. recompute, on 10GbE:

| hint accuracy | 0.0 (recency) | 0.5 | 0.8 | 0.95 | 1.0 (oracle) |
|---|---|---|---|---|---|
| W = 30 s, synthetic / trace | −14 / −25% | −22 / −22% | −25 / −21% | −23 / −21% | −22 / −22% |
| W = 120 s, synthetic / trace | −41 / −37% | −37 / −46% | −45 / −41% | −44 / −34% | −47 / −37% |

The intervals are ±12–30 points and overlap throughout. On the real trace there is
no trend at all: the oracle does no better than recency. **Reuse prediction is a
second-order lever**, which fits the real-trace finding that LRU is hard to beat
(agentic-kv-cache: liveness policies did not beat LRU-leaf). The paper should treat
the reuse estimator as a pluggable input, not a contribution, and the SOP should not
lean on prediction.

## 4. What changed in the model (for reviewers of the code)
- New policies `inflight_replicate` and `pool`, and the `variants` rows mechanism.
  The five Phase 1b policies are bit-identical to before (checked on four settings).
- New metrics: `displaced_ttft_p50/p99_s`, the TTFT of a session's first turn after
  its node is reclaimed (where survivor overload shows), and `replica_refusals`.
- Known simplifications: no memory-based admission control (hence the scaled-down
  g6e load in §2), and pool fetches use the fleet link with no contention.

## 5. Next
1. More seeds on the trace runs (the intervals are wide), plus a pool-tier
   memory-pressure setting to retest the pool result.
2. Phase 2 run on AWS (runner ready; needs one manual launch), then
   `--calibration` reruns.
3. First GPU test of the Phase 3 plugin (docs/phase3-design.md, "Prototype status").
