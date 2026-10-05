## budget (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 127s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| 10gbe, W=15s | recompute | 2387 | — | — | +0.26 | 26.2 | 0 | 0 | 0.07 |
| 10gbe, W=15s | evacuate | 2184 | -203 ± 249 | -9% | +0.22 | 10.2 | 68 | 0 | 0.07 |
| 10gbe, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.13 |
| 10gbe, W=30s | evacuate | 2180 | -258 ± 216 | -11% | +0.24 | 5.7 | 142 | 0 | 0.13 |
| 10gbe, W=60s | recompute | 2278 | — | — | +0.24 | 24.9 | 0 | 0 | 0.25 |
| 10gbe, W=60s | evacuate | 2018 | -260 ± 233 | -11% | +0.21 | 2.6 | 279 | 0 | 0.25 |
| 10gbe, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 0.50 |
| 10gbe, W=120s | evacuate | 1874 | -433 ± 268 | -19% | +0.20 | 1.4 | 535 | 0 | 0.50 |
| 25gbe, W=15s | recompute | 2387 | — | — | +0.26 | 26.2 | 0 | 0 | 0.17 |
| 25gbe, W=15s | evacuate | 2174 | -213 ± 324 | -9% | +0.21 | 10.1 | 169 | 0 | 0.17 |
| 25gbe, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| 25gbe, W=30s | evacuate | 1873 | -566 ± 248 | -23% | +0.19 | 4.8 | 335 | 0 | 0.32 |
| 25gbe, W=60s | recompute | 2278 | — | — | +0.24 | 24.9 | 0 | 0 | 0.62 |
| 25gbe, W=60s | evacuate | 1699 | -579 ± 280 | -25% | +0.19 | 2.2 | 656 | 0 | 0.62 |
| 25gbe, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| 25gbe, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| 100gbe, W=15s | recompute | 2387 | — | — | +0.26 | 26.2 | 0 | 0 | 0.66 |
| 100gbe, W=15s | evacuate | 1658 | -729 ± 339 | -31% | +0.17 | 9.8 | 591 | 0 | 0.66 |
| 100gbe, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 1.26 |
| 100gbe, W=30s | evacuate | 1349 | -1089 ± 290 | -45% | +0.17 | 4.7 | 1001 | 0 | 1.27 |
| 100gbe, W=60s | recompute | 2278 | — | — | +0.24 | 24.9 | 0 | 0 | 2.50 |
| 100gbe, W=60s | evacuate | 1085 | -1193 ± 400 | -52% | +0.14 | 3.0 | 1546 | 0 | 2.49 |
| 100gbe, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 5.06 |
| 100gbe, W=120s | evacuate | 982 | -1325 ± 324 | -57% | +0.14 | 1.6 | 1647 | 0 | 5.00 |
