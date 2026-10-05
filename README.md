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
- [x] Spot-notice harness: IMDSv2 mock and watcher on the real EC2 paths
  (`kvevac/notice/imds.py`).
- [x] Phase 3 design against vLLM's KV tiering ([docs/phase3-design.md](docs/phase3-design.md)).
- [ ] Real AgentX trace replay (blocked on data access from this environment).
- [ ] Phase 2: calibrate the cost model on real GPUs and links
  ([docs/calibration.md](docs/calibration.md)).
- [ ] Phase 3: a vLLM implementation. An IMDS notice handler pauses admission and
  ships session KV through the KV connector / P2P tier. Output-parity test.
- [ ] Phase 4: live FIS-triggered reclaims, then the write-up.

## Quick start (CPU only)
```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m kvevac.experiments all --seeds 6 --out results/phase1b
```

## Layout
```
kvevac/profiles.py   model / GPU / link constants (assumed until Phase 2)
kvevac/costmodel.py  recompute vs transfer time, crossover
kvevac/planner.py    deadline-bounded evacuation knapsack (the core decision)
kvevac/workload.py   agent sessions (synthetic, AgentX-calibrated) + real-trace loader
kvevac/sim.py        discrete-event fleet simulation, four policies
kvevac/sweep.py      regime sweep CLI (v0)
kvevac/experiments.py  Phase 1b experiments with paired 95% CIs
kvevac/reuse.py      session reuse estimators (fixed / recency / oracle)
kvevac/notice/imds.py  IMDSv2 mock + spot-notice watcher
```

## What this project does not do
No dynamic reparallelization (SpotServe). No claim to be the first to predict
preemption (Parcae, SkyNomad, hazardserve) or to exploit its correlation (SkyServe).
No claim that KV transfer generally beats recompute (ShuntServe measured the
opposite at short contexts).
