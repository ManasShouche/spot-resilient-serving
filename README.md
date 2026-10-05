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
- [x] Step 0: upstream reconnaissance at a pinned vLLM commit. See
  [docs/step0-recon.md](docs/step0-recon.md).
- [x] SOTA sweep and reframing. See [docs/sota-2026.md](docs/sota-2026.md).
- [ ] Harness: IMDS mock and FIS path, preemption generator (Poisson, correlated,
  trace replay), load generator, metrics.
- [ ] Baseline characterization (recompute, local drain).
- [ ] KV-aware drain with an output-parity test.
- [ ] Sweeps and the headline chart.

## What this project does not do
No dynamic reparallelization (SpotServe), no migration-plan optimization, no RDMA
in v1, and no tensor-parallel sweep.
