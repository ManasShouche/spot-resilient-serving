## baselines (6 seeds, real AgentX sessions from agentx.jsonl, resampled with replacement to the setting's session count, calibrated from prefill.json; 27s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | displaced TTFT p99 (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|---|
| independent, W=0s | recompute | 1156 | — | — | +0.04 | 119.0 | 12.8 | 0 | 0 | 0.00 |
| independent, W=0s | evacuate | 1156 | +0 ± 0 | +0% | +0.04 | 119.0 | 12.8 | 0 | 0 | 0.00 |
| independent, W=0s | replicate | 473 | -683 ± 213 | -59% | +0.18 | 82.5 | 13.0 | 0 | 51151 | 0.00 |
| independent, W=0s | hybrid | 473 | -683 ± 213 | -59% | +0.18 | 82.5 | 13.0 | 0 | 51151 | 0.00 |
| independent, W=0s | inflight_replicate | 795 | -361 ± 254 | -31% | -0.01 | 112.1 | 12.5 | 0 | 584145 | 0.00 |
| independent, W=0s | pool | 415 | -741 ± 262 | -64% | +0.18 | 84.5 | 12.5 | 0 | 44183 | 0.00 |
| independent, W=0s | pool x2 | 438 | -718 ± 251 | -62% | +0.17 | 84.2 | 11.8 | 0 | 88482 | 0.00 |
| independent, W=30s | recompute | 1233 | — | — | +0.06 | 131.5 | 12.8 | 0 | 0 | 0.48 |
| independent, W=30s | evacuate | 1061 | -172 ± 358 | -14% | +0.11 | 108.2 | 4.7 | 310 | 0 | 0.48 |
| independent, W=30s | replicate | 452 | -781 ± 457 | -63% | +0.27 | 81.0 | 12.8 | 0 | 50396 | 0.48 |
| independent, W=30s | hybrid | 354 | -878 ± 425 | -71% | +0.15 | 89.7 | 4.5 | 288 | 50700 | 0.48 |
| independent, W=30s | inflight_replicate | 850 | -382 ± 449 | -31% | +0.01 | 109.4 | 11.8 | 0 | 584098 | 0.48 |
| independent, W=30s | pool | 449 | -784 ± 501 | -64% | +0.05 | 76.4 | 11.0 | 0 | 44013 | 0.47 |
| independent, W=30s | pool x2 | 358 | -874 ± 507 | -71% | +0.10 | 75.8 | 10.3 | 0 | 88412 | 0.47 |
| independent, W=120s | recompute | 1189 | — | — | +0.07 | 122.5 | 11.2 | 0 | 0 | 2.01 |
| independent, W=120s | evacuate | 566 | -624 ± 496 | -52% | +0.23 | 104.5 | 1.0 | 1040 | 0 | 1.97 |
| independent, W=120s | replicate | 488 | -701 ± 322 | -59% | +0.08 | 87.6 | 12.0 | 0 | 49993 | 1.94 |
| independent, W=120s | hybrid | 407 | -782 ± 397 | -66% | +0.31 | 115.3 | 0.8 | 701 | 50850 | 1.97 |
| independent, W=120s | inflight_replicate | 846 | -343 ± 286 | -29% | +0.02 | 99.7 | 13.2 | 0 | 584135 | 1.96 |
| independent, W=120s | pool | 528 | -661 ± 447 | -56% | +0.31 | 100.9 | 11.5 | 0 | 44121 | 1.98 |
| independent, W=120s | pool x2 | 470 | -719 ± 342 | -60% | +0.36 | 106.1 | 11.2 | 0 | 88850 | 1.98 |
| correlated, W=0s | recompute | 1691 | — | — | +0.03 | 140.8 | 14.5 | 0 | 0 | 0.00 |
| correlated, W=0s | evacuate | 1691 | +0 ± 0 | +0% | +0.03 | 140.8 | 14.5 | 0 | 0 | 0.00 |
| correlated, W=0s | replicate | 840 | -851 ± 113 | -50% | +0.23 | 91.5 | 14.0 | 0 | 54226 | 0.00 |
| correlated, W=0s | hybrid | 840 | -851 ± 113 | -50% | +0.23 | 91.5 | 14.0 | 0 | 54226 | 0.00 |
| correlated, W=0s | inflight_replicate | 1134 | -557 ± 169 | -33% | +0.06 | 113.2 | 15.0 | 0 | 584112 | 0.00 |
| correlated, W=0s | pool | 875 | -816 ± 174 | -48% | +0.41 | 103.0 | 14.5 | 0 | 43232 | 0.00 |
| correlated, W=0s | pool x2 | 876 | -815 ± 225 | -48% | +0.38 | 87.6 | 14.3 | 0 | 88989 | 0.00 |
| correlated, W=30s | recompute | 1660 | — | — | +0.08 | 142.7 | 14.7 | 0 | 0 | 0.28 |
| correlated, W=30s | evacuate | 1489 | -171 ± 204 | -10% | +0.08 | 112.8 | 4.0 | 315 | 0 | 0.28 |
| correlated, W=30s | replicate | 741 | -919 ± 82 | -55% | +0.25 | 84.5 | 13.7 | 0 | 54359 | 0.29 |
| correlated, W=30s | hybrid | 813 | -847 ± 111 | -51% | +0.27 | 72.4 | 4.3 | 288 | 53857 | 0.28 |
| correlated, W=30s | inflight_replicate | 1219 | -441 ± 251 | -27% | +0.18 | 113.2 | 14.8 | 0 | 584005 | 0.28 |
| correlated, W=30s | pool | 932 | -728 ± 237 | -44% | +0.44 | 101.9 | 14.0 | 0 | 43983 | 0.29 |
| correlated, W=30s | pool x2 | 927 | -733 ± 366 | -44% | +0.45 | 108.2 | 13.7 | 0 | 90155 | 0.29 |
| correlated, W=120s | recompute | 1657 | — | — | +0.25 | 123.7 | 14.2 | 0 | 0 | 1.14 |
| correlated, W=120s | evacuate | 878 | -779 ± 173 | -47% | +0.19 | 139.4 | 1.2 | 1215 | 0 | 1.14 |
| correlated, W=120s | replicate | 828 | -829 ± 138 | -50% | +0.34 | 91.1 | 14.2 | 0 | 54474 | 1.15 |
| correlated, W=120s | hybrid | 723 | -934 ± 214 | -56% | +0.37 | 115.9 | 1.3 | 857 | 53639 | 1.15 |
| correlated, W=120s | inflight_replicate | 1157 | -500 ± 161 | -30% | +0.09 | 110.5 | 15.0 | 0 | 584130 | 1.13 |
| correlated, W=120s | pool | 1047 | -609 ± 330 | -37% | +0.50 | 123.6 | 13.8 | 0 | 43799 | 1.15 |
| correlated, W=120s | pool x2 | 927 | -730 ± 362 | -44% | +0.42 | 92.1 | 13.8 | 0 | 90072 | 1.15 |
