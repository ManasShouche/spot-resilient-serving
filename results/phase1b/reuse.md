## reuse (6 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 31s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| fixed, W=30s | recompute | 2317 | — | — | +0.21 | 25.0 | 0 | 0 | 0.25 |
| fixed, W=30s | evacuate | 1889 | -428 ± 680 | -18% | +0.16 | 5.3 | 331 | 0 | 0.26 |
| recency, W=30s | recompute | 2317 | — | — | +0.21 | 25.0 | 0 | 0 | 0.25 |
| recency, W=30s | evacuate | 1736 | -582 ± 338 | -25% | +0.17 | 6.0 | 297 | 0 | 0.26 |
| oracle, W=30s | recompute | 2317 | — | — | +0.21 | 25.0 | 0 | 0 | 0.25 |
| oracle, W=30s | evacuate | 1575 | -742 ± 464 | -32% | +0.16 | 5.2 | 264 | 0 | 0.26 |
| fixed, W=120s | recompute | 2133 | — | — | +0.20 | 23.5 | 0 | 0 | 1.01 |
| fixed, W=120s | evacuate | 1262 | -871 ± 407 | -41% | +0.13 | 1.7 | 1051 | 0 | 0.99 |
| recency, W=120s | recompute | 2133 | — | — | +0.20 | 23.5 | 0 | 0 | 1.01 |
| recency, W=120s | evacuate | 1149 | -984 ± 450 | -46% | +0.12 | 1.7 | 916 | 0 | 1.00 |
| oracle, W=120s | recompute | 2133 | — | — | +0.20 | 23.5 | 0 | 0 | 1.01 |
| oracle, W=120s | evacuate | 807 | -1326 ± 637 | -62% | +0.09 | 1.8 | 584 | 0 | 1.00 |
