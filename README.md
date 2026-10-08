# spot-resilient-serving

A faithful AWS spot-preemption harness for vLLM serving, plus one targeted fix:
KV-cache-aware drain on interruption signals.

**Question (reframed after the October 2026 SOTA sweep, see
[docs/sota-2026.md](docs/sota-2026.md)):** with a termination notice of W seconds,
how much of the KV value at risk on a spot node can deadline-bounded evacuation
preserve? That value includes in-flight requests and idle agent-session prefix
caches. In which regimes does on-notice evacuation match continuous replication,
at zero steady-state cost?

## Status
- [x] Step 0: upstream reconnaissance at a pinned vLLM commit
  ([docs/step0-recon.md](docs/step0-recon.md)).
- [x] SOTA sweep and reframing ([docs/sota-2026.md](docs/sota-2026.md)).
- [x] Positioning check against primary sources, with corrections and the
  experiments that would make this paper-worthy ([docs/positioning.md](docs/positioning.md)).
- [x] **Phase 1 (this commit):** cost model, deadline-bounded evacuation planner,
  agent-session workload generator, discrete-event simulator, regime sweep
  ([docs/simulator.md](docs/simulator.md)). Results are **simulated with assumed
  constants and a synthetic workload**.
- [x] **Phase 1b:** contention, hybrid policy, shared ingress, write-through
  backpressure, reuse ablation, and paired 12-seed experiments. **Findings
  (simulated):**
  - With a free replica tier and unlimited bandwidth, write-through and hybrid cut
    reclaim-induced recompute by about 55–60%. Evacuation alone gets 14–43%.
  - At **equal memory**, evacuation wins: −50% vs +90% for write-through.
  - Under a **shared-store bandwidth budget**, write-through drops to −25% while
    hybrid holds −51%.
  - Evacuation's benefit tracks ρ = notice × bandwidth / resident KV.

  See [docs/phase1b-results.md](docs/phase1b-results.md), including §7,
  corrections to an earlier 6-seed claim.
- [x] **Phase 1c:** related-work baselines, value-at-risk characterization, and a
  reuse-prediction sweep ([docs/phase1c-results.md](docs/phase1c-results.md)).
  Each experiment ran on both the synthetic workload and the **real AgentX trace**
  (load-matched). **Findings (simulated):**
  - On the real trace, 75–78% of a large node's resident KV belongs to sessions
    with no turn running, which no in-flight fault-tolerance system protects.
  - KevlarFlow-style in-flight replication gets only −13% to −36% at 12–14× the
    egress of session replication.
  - Reuse prediction is second-order; on the trace, an oracle is no better than
    recency.
  - Correction: the synthetic result that failure-domain-blind pools are fragile
    under correlated waves did **not** replicate on the trace.
- [x] Novelty check against 2026 agent-KV and llm-d work
  ([docs/positioning.md §7](docs/positioning.md)).
- [x] Spot-notice harness: IMDSv2 mock and watcher on the real EC2 paths
  (`kvevac/notice/imds.py`).
- [x] Phase 3 design against vLLM's KV tiering ([docs/phase3-design.md](docs/phase3-design.md)).
- [ ] Real AgentX trace replay (blocked on data access from this environment).
- [x] **Phase 2 (first run):** measured on a real L40S, on demand in us-east-2
  ([docs/phase2-results.md](docs/phase2-results.md)). Measured prefill is 16k tok/s
  (assumed 10k), the knee is 20.5k tokens, and decode is 46.7 tok/s.
  Receiver-side interference from incoming KV is **0–3%**. The simulator's ranking
  holds with measured constants. Not yet measured: FIS notice timing (needs spot
  capacity) and NIC/store bandwidth.
- [x] **Phase 3 (first GPU test):** the out-of-tree vLLM plugin (`kvevac/vllm_plugin`)
  ran on a real L40S under vLLM 0.31.0 ([docs/phase3-results.md](docs/phase3-results.md)).
  Deferred mode kept the tier empty until the notice. The deadline flush wrote and
  confirmed 10.2 GB in 49 s, against a 46.5 s projection. A fresh process restored the
  sessions with **output parity** against cold recompute. On the instance's NVMe (~0.4
  GB/s restore) recompute is faster. **Two nodes**: evacuation to a peer's DRAM over the
  network took 6.6 s for 10.2 GB, and restore from it beat recompute on a 59k-token turn
  (8.3 s vs 9.1 s TTFT) with output parity. 8B on L40S sits at the crossover.
- [ ] Phase 4: live FIS-triggered reclaims, then the write-up.

![Write-through vs hybrid vs evacuation under a replication bandwidth budget](docs/figures/backpressure.svg)

## Quick start (CPU only)
```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m kvevac.experiments all --seeds 6 --out results/phase1b
```

## Layout
```
kvevac/profiles.py        model / GPU / link constants (assumed until Phase 2)
kvevac/costmodel.py       recompute vs transfer time, crossover
kvevac/planner.py         deadline-bounded evacuation knapsack (the core decision)
kvevac/flush.py           session plan -> prefix-ordered, deduplicated block flush order
kvevac/reuse.py           session reuse estimators (fixed / recency / oracle)
kvevac/workload.py        agent sessions (synthetic, AgentX-calibrated) + real-trace loader
kvevac/sim.py             discrete-event fleet simulation, five policies
kvevac/experiments.py     Phase 1b experiments with paired 95% CIs (--calibration aware)
kvevac/calibration.py     fit cost-model constants from measurements
kvevac/measure/prefill.py Phase 2: cold-prefill TTFT + decode-rate client for vLLM
kvevac/notice/imds.py     IMDSv2 mock + spot-notice watcher (real EC2 paths)
kvevac/notice/handler.py  notice handler: timeline log, flush request, vLLM pause
kvevac/characterize.py    value at risk per node: hot/idle KV, rebuild cost, rho
kvevac/vllm_plugin/       Phase 3: deadline write-back for vLLM's tiered KV offload
scripts/figures.py        SVG figures from results JSON
```

## What this project does not do
No dynamic reparallelization (SpotServe). No claim to a better reuse predictor
(CacheScout, Continuum, CacheWise); the estimator is pluggable. No claim to be the first to predict
preemption (Parcae, SkyNomad, hazardserve) or to exploit its correlation (SkyServe).
No claim that KV transfer generally beats recompute (ShuntServe measured the
opposite at short contexts).
