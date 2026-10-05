# spot-resilient-serving

A faithful AWS spot-preemption harness for vLLM serving, plus one targeted fix:
KV-cache-aware drain on interruption signals.

**Question:** spot preemption is correlated and partly predictable. When does
migrating in-flight requests' KV on the rebalance or interruption signal beat
recomputing them, or draining them locally? Where does that advantage disappear?

## Status
- [x] Step 0: upstream reconnaissance at a pinned vLLM commit. See
  [docs/step0-recon.md](docs/step0-recon.md).
- [ ] Harness: IMDS mock and FIS path, preemption generator (Poisson, correlated,
  trace replay), load generator, metrics.
- [ ] Baseline characterization (recompute, local drain).
- [ ] KV-aware drain with an output-parity test.
- [ ] Sweeps and the headline chart.

## What this project does not do
No dynamic reparallelization (SpotServe), no migration-plan optimization, no RDMA
in v1, and no tensor-parallel sweep.
