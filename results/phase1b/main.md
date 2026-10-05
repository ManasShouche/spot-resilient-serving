## main (6 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 62s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| independent, W=0s | recompute | 2125 | — | — | +0.20 | 24.3 | 0 | 0 | 0.00 |
| independent, W=0s | drain_local | 2125 | +0 ± 0 | +0% | +0.20 | 24.3 | 0 | 0 | 0.00 |
| independent, W=0s | evacuate | 2125 | +0 ± 0 | +0% | +0.20 | 24.3 | 0 | 0 | 0.00 |
| independent, W=0s | replicate | 1509 | -616 ± 447 | -29% | +0.15 | 24.2 | 0 | 45472 | 0.00 |
| independent, W=0s | hybrid | 1509 | -616 ± 447 | -29% | +0.15 | 24.2 | 0 | 45472 | 0.00 |
| independent, W=30s | recompute | 2317 | — | — | +0.21 | 25.0 | 0 | 0 | 0.25 |
| independent, W=30s | drain_local | 2091 | -226 ± 433 | -10% | +0.20 | 6.3 | 0 | 0 | 0.25 |
| independent, W=30s | evacuate | 1889 | -428 ± 680 | -18% | +0.16 | 5.3 | 331 | 0 | 0.26 |
| independent, W=30s | replicate | 1493 | -824 ± 596 | -36% | +0.15 | 24.5 | 0 | 46089 | 0.25 |
| independent, W=30s | hybrid | 893 | -1424 ± 759 | -61% | +0.09 | 5.8 | 305 | 47253 | 0.26 |
| independent, W=120s | recompute | 2133 | — | — | +0.20 | 23.5 | 0 | 0 | 1.01 |
| independent, W=120s | drain_local | 1999 | -133 ± 370 | -6% | +0.18 | 1.2 | 0 | 0 | 1.00 |
| independent, W=120s | evacuate | 1262 | -871 ± 407 | -41% | +0.13 | 1.7 | 1051 | 0 | 0.99 |
| independent, W=120s | replicate | 1619 | -514 ± 275 | -24% | +0.17 | 26.8 | 0 | 47011 | 0.99 |
| independent, W=120s | hybrid | 747 | -1386 ± 595 | -65% | +0.09 | 1.3 | 729 | 46873 | 0.99 |
| correlated, W=0s | recompute | 2261 | — | — | +0.21 | 19.7 | 0 | 0 | 0.00 |
| correlated, W=0s | drain_local | 2261 | +0 ± 0 | +0% | +0.21 | 19.7 | 0 | 0 | 0.00 |
| correlated, W=0s | evacuate | 2261 | +0 ± 0 | +0% | +0.21 | 19.7 | 0 | 0 | 0.00 |
| correlated, W=0s | replicate | 1978 | -283 ± 471 | -13% | +0.22 | 19.5 | 0 | 41084 | 0.00 |
| correlated, W=0s | hybrid | 1978 | -283 ± 471 | -13% | +0.22 | 19.5 | 0 | 41084 | 0.00 |
| correlated, W=30s | recompute | 2605 | — | — | +0.23 | 20.8 | 0 | 0 | 0.17 |
| correlated, W=30s | drain_local | 2327 | -277 ± 216 | -11% | +0.23 | 6.2 | 0 | 0 | 0.17 |
| correlated, W=30s | evacuate | 2343 | -262 ± 114 | -10% | +0.21 | 5.5 | 309 | 0 | 0.17 |
| correlated, W=30s | replicate | 2192 | -413 ± 262 | -16% | +0.23 | 20.7 | 0 | 39860 | 0.17 |
| correlated, W=30s | hybrid | 1098 | -1507 ± 379 | -58% | +0.14 | 5.7 | 281 | 40373 | 0.17 |
| correlated, W=120s | recompute | 2528 | — | — | +0.21 | 20.0 | 0 | 0 | 0.69 |
| correlated, W=120s | drain_local | 2548 | +20 ± 289 | +1% | +0.24 | 1.2 | 0 | 0 | 0.68 |
| correlated, W=120s | evacuate | 1432 | -1096 ± 507 | -43% | +0.14 | 1.2 | 1073 | 0 | 0.69 |
| correlated, W=120s | replicate | 2058 | -470 ± 290 | -19% | +0.22 | 20.0 | 0 | 38224 | 0.68 |
| correlated, W=120s | hybrid | 1147 | -1381 ± 533 | -55% | +0.13 | 1.2 | 724 | 39496 | 0.68 |
