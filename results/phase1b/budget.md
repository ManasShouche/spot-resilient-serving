## budget (6 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 56s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| 10gbe, W=15s | recompute | 2071 | — | — | +0.20 | 24.8 | 0 | 0 | 0.05 |
| 10gbe, W=15s | evacuate | 1953 | -118 ± 350 | -6% | +0.18 | 10.5 | 66 | 0 | 0.05 |
| 10gbe, W=30s | recompute | 2317 | — | — | +0.21 | 25.0 | 0 | 0 | 0.10 |
| 10gbe, W=30s | evacuate | 2263 | -54 ± 555 | -2% | +0.24 | 5.7 | 138 | 0 | 0.10 |
| 10gbe, W=60s | recompute | 2164 | — | — | +0.21 | 24.8 | 0 | 0 | 0.19 |
| 10gbe, W=60s | evacuate | 1921 | -243 ± 320 | -11% | +0.15 | 2.7 | 273 | 0 | 0.20 |
| 10gbe, W=120s | recompute | 2133 | — | — | +0.20 | 23.5 | 0 | 0 | 0.40 |
| 10gbe, W=120s | evacuate | 1864 | -269 ± 519 | -13% | +0.17 | 1.7 | 533 | 0 | 0.40 |
| 25gbe, W=15s | recompute | 2071 | — | — | +0.20 | 24.8 | 0 | 0 | 0.12 |
| 25gbe, W=15s | evacuate | 1994 | -77 ± 319 | -4% | +0.20 | 10.3 | 169 | 0 | 0.13 |
| 25gbe, W=30s | recompute | 2317 | — | — | +0.21 | 25.0 | 0 | 0 | 0.25 |
| 25gbe, W=30s | evacuate | 1889 | -428 ± 680 | -18% | +0.16 | 5.3 | 331 | 0 | 0.26 |
| 25gbe, W=60s | recompute | 2164 | — | — | +0.21 | 24.8 | 0 | 0 | 0.49 |
| 25gbe, W=60s | evacuate | 1499 | -665 ± 475 | -31% | +0.15 | 2.3 | 643 | 0 | 0.49 |
| 25gbe, W=120s | recompute | 2133 | — | — | +0.20 | 23.5 | 0 | 0 | 1.01 |
| 25gbe, W=120s | evacuate | 1262 | -871 ± 407 | -41% | +0.13 | 1.7 | 1051 | 0 | 0.99 |
| 100gbe, W=15s | recompute | 2071 | — | — | +0.20 | 24.8 | 0 | 0 | 0.50 |
| 100gbe, W=15s | evacuate | 1710 | -361 ± 473 | -17% | +0.14 | 10.8 | 592 | 0 | 0.51 |
| 100gbe, W=30s | recompute | 2317 | — | — | +0.21 | 25.0 | 0 | 0 | 1.01 |
| 100gbe, W=30s | evacuate | 1290 | -1027 ± 691 | -44% | +0.14 | 5.3 | 917 | 0 | 1.02 |
| 100gbe, W=60s | recompute | 2164 | — | — | +0.21 | 24.8 | 0 | 0 | 1.96 |
| 100gbe, W=60s | evacuate | 1137 | -1026 ± 519 | -47% | +0.10 | 2.3 | 1367 | 0 | 1.96 |
| 100gbe, W=120s | recompute | 2133 | — | — | +0.20 | 23.5 | 0 | 0 | 4.03 |
| 100gbe, W=120s | evacuate | 916 | -1217 ± 586 | -57% | +0.09 | 1.8 | 1528 | 0 | 3.99 |
