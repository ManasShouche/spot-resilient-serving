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
- [ ] Phase 1b: hybrid policy (replicate + evacuate), sensitivity to cache size, model
  size and egress contention, and a real AgentX trace replay.
- [ ] Phase 2: calibrate the cost model on real GPUs and links
  ([docs/calibration.md](docs/calibration.md)).
- [ ] Phase 3: a vLLM implementation. An IMDS notice handler pauses admission and
  ships session KV through the KV connector / P2P tier. Output-parity test.
- [ ] Phase 4: live FIS-triggered reclaims, then the write-up.

## Quick start (CPU only)
```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m kvevac.sweep --seeds 5 --replica-tokens 2000000
```

## Layout
```
kvevac/profiles.py   model / GPU / link constants (assumed until Phase 2)
kvevac/costmodel.py  recompute vs transfer time, crossover
kvevac/planner.py    deadline-bounded evacuation knapsack (the core decision)
kvevac/workload.py   agent sessions (synthetic, AgentX-calibrated) + real-trace loader
kvevac/sim.py        discrete-event fleet simulation, four policies
kvevac/sweep.py      regime sweep CLI
```

## What this project does not do
No dynamic reparallelization (SpotServe). No claim to be the first to predict
preemption (Parcae, SkyNomad, hazardserve) or to exploit its correlation (SkyServe).
No claim that KV transfer generally beats recompute (ShuntServe measured the
opposite at short contexts).
