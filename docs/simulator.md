# Simulator v0: model, assumptions, and known gaps

`kvevac.sim` is a discrete-event simulation of agent sessions on a spot fleet. Its job
is to say **which regimes deserve real-hardware experiments**. It does not produce
numbers to quote. Every result it prints must be labelled *simulated, assumed
constants, synthetic workload* until Phases 2 and 3 replace those parts.

## What is modelled
- **Fleet:** 3 failure groups × 4 nodes. Each node has a session-cache capacity
  (GPU KV plus host tier, default 2M tokens) and an optional separate replica tier.
  A reclaimed node is replaced after 300 s with an empty cache.
- **Workload:** multi-turn agent sessions. Context grows each turn and compacts at
  the 256k cap. Marginals are fitted to the published AgentX summary
  (`kvevac/workload.py`). A loader for the real corpus exists but has not been run,
  because huggingface.co was blocked in the build environment.
- **Serving:** sticky routing and LRU over idle sessions. Incremental prefill is
  costed as `recompute(context) − recompute(resident prefix)`, with a linear
  attention penalty. Decode runs at a fixed per-request rate.
- **Reclaims:** independent (Poisson per node) or correlated (half of one failure
  group at once), each with a notice of W seconds.
- **Policies:**
  - `recompute`: no reaction.
  - `drain_local`: stop admitting; in-flight turns finish if they fit.
  - `evacuate`: drain plus the deadline-bounded knapsack in `kvevac/planner.py`.
  - `replicate`: continuous replication of each session's cache to a peer in
    another failure group after every turn.
- **Headline metric:** *excess prefill GPU-seconds* against the same workload with
  no reclaims. This includes displacement effects that per-session loss counters
  miss.

## Known gaps, and the direction each one biases results
| Gap | Biases toward |
|---|---|
| Prefill is serialized per node (v1b), but decode is not modelled as contending | Understates losses under heavy decode load |
| Evacuation traffic doesn't slow serving on the source or destination | Favours `evacuate` |
| `replicate` protects only completed turns; in-flight KV isn't streamed (KevlarFlow streams it). `hybrid` covers this at notice | Against `replicate` on killed turns |
| Replica updates land instantly; the bandwidth budget models only drops | Favours `replicate`/`hybrid` |
| The replica tier in the default sweep is as large as the primary cache | Favours `replicate` |
| Reuse probability is a fixed 0.9 for every session; no prediction | Neutral now; a real estimator could help `evacuate` |
| Session-granular prefixes: no block-level partial hits, no cross-session sharing | Unknown; cross-session sharing would favour `recompute` |
| Correlated bursts hit a single failure group; destinations outside it are assumed safe | Favours `evacuate` under truly correlated multi-group reclaims |
| All hardware constants are assumed (`kvevac/profiles.py`) | Unknown until Phase 2 |

## v0 regime map (superseded by docs/phase1b-results.md)

The v0 results below used a lightly loaded fleet with no contention. The "less
egress" comparison compared totals, not rates; see the correction in
`docs/phase1b-results.md` §5.

### v0 (5 seeds, synthetic, assumed constants)
Full table: `results/sweep_v0_synthetic.md`. Excess prefill GPU-seconds,
mean ± sd, independent reclaims, 25GbE:

| notice | recompute | drain_local | evacuate | replicate (separate tier) |
|---|---|---|---|---|
| 0 s | 519 ± 154 | 519 ± 154 | 519 ± 154 | **210 ± 145** (5.3 TB egress) |
| 30 s | 534 ± 250 | 488 ± 201 | **240 ± 94** (0.35 TB) | 276 ± 199 (5.2 TB) |
| 120 s | 451 ± 170 | 518 ± 246 | **72 ± 51** (0.9 TB) | 263 ± 173 (5.3 TB) |

How to read it, provisionally:
1. **With 0 s notice, continuous replication is the only thing that helps.** This is
   the honest boundary of the approach.
2. **With 30 s notice, evacuation roughly matches replication** on about 15× less
   egress, and with no steady-state cost.
3. **With 120 s notice, evacuation beats replication** on about 6× less egress.
   Correlated reclaims shrink the advantage (184 vs 256).
4. **Draining locally alone does not help** and can be slightly worse than doing
   nothing. It stops using the doomed node's cache for the whole notice window and
   saves only in-flight turns.

The variance is large (sd roughly 30–70% of the mean). Run more seeds before
reading anything finer than these orderings.
