# Phase 1b results (simulated)

**Status of these numbers:** discrete-event simulation. The workload is synthetic
agent sessions fitted to the published AgentX marginals. Hardware constants are
assumed (`kvevac/profiles.py`). Six seeds per setting. Every policy within a seed
sees the same workload and reclaim schedule, so comparisons with `recompute` are
**paired**: Δ is the mean per-seed difference, ± its 95% t-interval. Raw tables and
JSON are in `results/phase1b/`. Reproduce with:

```bash
python -m kvevac.experiments all --seeds 6 --out results/phase1b
```

Default setting: 12 nodes in 3 failure groups, 4M-token session cache per node and
a 4M-token replica tier, 800 sessions (≈36% prefill utilization), Llama-3.1-8B on
L40S, 25GbE, independent reclaims at 0.1 per node-hour. Headline metric: **excess
prefill GPU-seconds** against the same run with no reclaims.

## 1. Main regime map (`results/phase1b/main.md`)

Δ% vs `recompute`, independent / correlated (half a failure group per burst):

| notice W | drain_local | evacuate | replicate (write-through) | **hybrid** |
|---|---|---|---|---|
| 0 s | 0 / 0 | 0 / 0 | −29% / −13% | −29% / −13% |
| 30 s | −10% / −11% | −18% / −10% | −36% / −16% | **−61% / −58%** |
| 120 s | −6% / +1% | −41% / −43% | −24% / −19% | **−65% / −55%** |

- **The hybrid is the finding.** Write-through protects idle sessions
  continuously. Evacuation at notice protects what write-through misses: in-flight
  turns (killed turns fall from about 24 to 1–6) and replicas that are stale or were
  evicted. The two cover different failures, so the combination beats both. Its
  intervals exclude zero in every setting with W ≥ 30 s.
- **Evacuation alone beats write-through only with enough notice.** At 120 s it
  gets −41% vs −24%. At 30 s it is the other way round. With 0 s notice, only
  write-through helps, which is the expected boundary.
- **Draining locally alone is roughly worthless.** It also hurts badly under cache
  pressure (see §3).

## 2. The governing ratio (`results/phase1b/budget.md`)

Evacuation's benefit tracks **ρ = W · B / (KV resident on the reclaimed node)**:

| ρ | ≤ 0.12 | 0.19–0.26 | 0.40–0.51 | ≈ 1.0 | 2–4 |
|---|---|---|---|---|---|
| Δ% (evacuate vs recompute) | −2% to −6% | −11% to −18% | −13% to −31% | −41% to −44% | −47% to −57% |

The benefit is close to monotone in ρ and saturates above about 1. The spread at
equal ρ (10GbE W=120 s at −13% vs 25GbE W=60 s at −31%) suggests that ρ is not
sufficient on its own. A likely second factor is per-object transfer granularity:
on a slower link, each 100k+-token session takes longer to ship, so fewer complete
sessions finish. **Paper-ready framing:** a dimensionless ratio that operators can
compute from their notice window, NIC, and cache size predicts whether evacuation is
worth deploying.

## 3. Sensitivity (`results/phase1b/sensitivity.md`)

| Setting | evacuate | replicate | hybrid | Reading |
|---|---|---|---|---|
| default (for reference) | −41% | −24% | −65% | |
| cache 2M (pressure) | −31% | +2% | −28% | Write-through stops helping under cache pressure; draining is +53% (harmful) |
| cache 8M (roomy) | −50% | −47% | **−88%** | With room, the combination nearly eliminates the loss |
| 400 sessions | −65% | −37% | −85% | |
| 1200 sessions (high load) | −42% | **−1%** | −39% | **Write-through collapses under load** (replica churn); evacuation does not |
| 70B on 4×H100 | −22% | −23% | −55% | Bigger KV per token lowers ρ to 0.42 |
| whole-group bursts | −15% | −3% | −32% | Correlated reclaim is the hard case for everything |
| quarter-group bursts | −30% | −19% | −52% | |
| replica tier 1M | −41% | −15% | −58% | A small replica tier thrashes: 585 MB/s/node re-shipping full contexts |

## 4. How much would better reuse prediction help? (`results/phase1b/reuse.md`)

| W | fixed P=0.9 | recency (idle time) | oracle |
|---|---|---|---|
| 30 s | −18% | −25% | −32% |
| 120 s | −41% (1051 GB) | −46% (916 GB) | **−62% (584 GB)** |

Knowing which sessions will come back is worth about 20 more points *while moving
45% less data*. A simple recency model captures about a quarter of that.
**Open sub-problem:** predict session continuation from agent semantics (tool-call
state, plan progress). SemSpot (arXiv 2608.29581) points the same way at the API
level.

## 5. Correcting an earlier framing: steady-state cost

v0's docs said evacuation used "15× less egress" than write-through. That compared
totals and overstated the case. Write-through ships only each turn's new tokens, so
its *rate* is modest: **about 70–85 MB/s per node** by default (3–7% of a
10–25GbE NIC), rising to 160–240 MB/s under high load or with the 70B model, and
585 MB/s when the replica tier thrashes. The real costs of write-through are:

1. **Replica capacity.** It needs a tier as large as the primary cache to work
   (§3, replica tier 1M).
2. **Shared-tier saturation.** Twelve nodes at 85 MB/s already saturate one
   ~1 GB/s object store. That is where vLLM's `ThrottledDropPolicy` starts dropping
   stores (modelled by `FleetConfig.replication_bytes_per_s`).
3. **Coverage.** It does not protect in-flight turns. It becomes stale under load.

Evacuation's advantage is that it costs nothing until a notice arrives. **The
strongest system is both: write-through within budget, and write-back at notice.**

## Threats to validity (see also `docs/simulator.md`)
- Assumed hardware constants. Phase 2 measures them. The ordering of policies is
  what must survive, not the percentages.
- Synthetic workload. The real AgentX replay is blocked on data access.
- Six seeds. Several intervals are wide. Rerun main with `--seeds 20` before quoting
  any number.
- The replica tier updates instantly; the queue models only drops. This flatters
  write-through.
- Evacuation traffic does not slow serving. This flatters evacuation.
