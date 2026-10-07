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
  **Findings (simulated):**
  - 55–63% of a node's resident KV belongs to *idle* sessions, which no
    fault-tolerance system protects.
  - KevlarFlow-style in-flight replication gets only −13% to −30% at about 14× the
    egress of session replication.
  - A pool that ignores failure domains drops to −32% under correlated waves.
  - Perfect reuse prediction adds only 6–8 points.
- [x] Novelty check against 2026 agent-KV and llm-d work
  ([docs/positioning.md §7](docs/positioning.md)).
- [x] Spot-notice harness: IMDSv2 mock and watcher on the real EC2 paths
  (`kvevac/notice/imds.py`).
- [x] Phase 3 design against vLLM's KV tiering ([docs/phase3-design.md](docs/phase3-design.md)).
- [ ] Real AgentX trace replay (blocked on data access from this environment).
- [ ] Phase 2: calibrate the cost model on real GPUs and links
  ([docs/calibration.md](docs/calibration.md)). The tooling (measurement client,
  fitting, `--calibration`) is ready and tested against fakes; it **needs GPU
  access to run**.
- [~] Phase 3: a vLLM prototype, written but **not yet run on a GPU**
  (`kvevac/vllm_plugin`, [status](docs/phase3-design.md#prototype-status-october-2026)).
  It is an out-of-tree offloading spec. Deferred/hybrid cascades keep session KV in
  the CPU tier; on notice, the handler triggers a deadline-bounded, planner-ordered
  flush to a secondary tier. Still to do: the GPU run and the output-parity test.
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
