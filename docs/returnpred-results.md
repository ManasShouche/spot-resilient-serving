# Predicting which idle sessions return (15 October)

The planner sweep (`docs/phase3-results.md` §2e) found that an oracle knowing which
sessions return saves 1.5–2× more than any policy. The planner's P(reuse) is a recency
curve fitted to published gap quantiles (`kvevac/reuse.py`). This study asks whether a
model over each session's own history does better, and how much of the oracle gap that
recovers. Everything here is offline (CPU only, no AWS). Code: `kvevac/returnpred.py`;
raw output: `results/returnpred/`.

```bash
python -m kvevac.returnpred --trace data/raw/agentx.jsonl --out results/returnpred
```

## Method
- **Data.** The same simulation the sweep's snapshots come from: the 8B node, 1,600
  sessions resampled from the 393 real AgentX sessions, with snapshots every 5 minutes
  in steady state. Every idle session at every snapshot is one example (1,639 in all;
  70% return). Its label is "sends another turn".
- **Features**, from the session's history up to the snapshot only: idle time, turns so
  far, session age, context size, the last, mean-of-5 and max inter-request gap, idle
  time relative to its own median gap, share of long (>60 s) gaps, last output length,
  context growth, compactions, and the recency estimate itself.
- **Cross-fitting by source session.** Five folds split by the *source* AgentX session.
  Every prediction comes from a model that never saw that source session, because
  resampled copies of one real session would otherwise leak between train and test.
- **Planner value.** The offline sweep preview (`kvevac.planner_trials.preview`; at
  250 MB/s it matched the L40S hardware run closely), with the planner fed recency,
  logistic, boosted-tree or oracle P(reuse). It is scored on the hardware sweep's exact
  14 snapshots and on 148 more drawn the same way. Value is recompute seconds saved for
  sessions that return, net of restore.

## 1. Classifier quality

| P(returns) estimate | AUC | Brier | log loss |
|---|---|---|---|
| constant (70%) | 0.50 | 0.208 | 0.607 |
| recency curve (planner today) | 0.59 | 0.267 | 0.748 |
| logistic regression | 0.66 | 0.207 | 0.605 |
| **gradient-boosted trees** | **0.79** | 0.208 | 0.717 |

The recency curve ranks returns only slightly better than chance, and its
probabilities are worse calibrated than a constant. Gradient-boosted trees rank much
better (AUC 0.79) but are overconfident (log loss).

## 2. Does better ranking mean more value saved?

Mean value saved per snapshot (s), 148 offline snapshots:

| link, notice | planner (recency) | planner (logistic) | planner (boosted) | planner (oracle P) | recent | largest | random |
|---|---|---|---|---|---|---|---|
| 250 MB/s, 60 s | 5.36 | 5.25 | 5.58 | 6.50 | 4.07 | 5.01 | 3.59 |
| 1000 MB/s, 15 s | 3.98 | 3.93 | 4.24 | 4.99 | 3.15 | 3.72 | 2.96 |
| 1000 MB/s, 30 s | 8.85 | 8.85 | 8.95 | 9.18 | 8.54 | 8.69 | 8.53 |

Settings where every policy saves almost nothing (≤ 30 s at 250 MB/s, 10 s at 1000 MB/s)
and where everything fits (60 s at 1000 MB/s) are in `results/returnpred/planner_value.json`.

- **A better predictor recovers only about a fifth of the oracle gap.** Boosted vs.
  recency planner: +0.22 ± 0.42 s of a possible +1.13 s at 250 MB/s / 60 s, and +0.25 ±
  0.31 s of +1.01 s at 1000 MB/s / 15 s. It is ahead about three times as often as behind
  (15 vs 5, 17 vs 6), but no single setting is significant at 95%. Logistic regression
  adds nothing.
- **On the hardware sweep's 14 snapshots the same predictor looks much better** (about
  half the oracle gap, e.g. 2.87 → 4.25 s vs 5.22 s oracle). That is small-sample
  optimism; the 148-snapshot estimate is the one to trust.

## 3. Revisiting "the planner is no better than simple orders"

Paired planner (recency) minus baseline, 148 offline snapshots, mean ± 95%:

| link, notice | vs most-recent | vs largest-first | vs random |
|---|---|---|---|
| 250 MB/s, 60 s | **+1.29 ± 0.54** | +0.35 ± 0.37 | **+1.78 ± 0.66** |
| 1000 MB/s, 15 s | **+0.83 ± 0.42** | +0.26 ± 0.27 | **+1.02 ± 0.50** |
| 1000 MB/s, 30 s | **+0.31 ± 0.18** | +0.16 ± 0.20 | **+0.32 ± 0.24** |

- **With enough snapshots the planner beats most-recent and random orders, and ties
  largest-first.** The hardware sweep (10 snapshots) could not see this: its intervals
  were ±2 s wide. Its "no advantage" result was underpowered, not a contradiction.
- The 250 MB/s row is the most trustworthy, since that is where the offline model
  matched the hardware. At 1000 MB/s the hardware saved less than the model predicted
  (§2e), so treat that row as an upper bound.

## What this means
- The planner's value-density ordering is worth having over naive orders. It mostly
  rediscovers "save the biggest returning context first", which is why it ties
  largest-first.
- **Which sessions return is the open problem.** Session history carries real signal
  (AUC 0.79), but turning it into saved value is hard. Most snapshots hold 2–4
  sessions, and the predictor's errors on large sessions cost the most. Better
  calibration, or a value-aware training objective (weighting large contexts), is the
  obvious next step, and so are richer signals than the trace offers (tool-call types,
  as in CacheScout and Continuum).
- Limits: one trace (393 sessions), the 8B node only, an offline value model validated
  on hardware only at 250 MB/s, and labels of "ever returns" rather than "returns
  before this KV would be evicted anyway".
