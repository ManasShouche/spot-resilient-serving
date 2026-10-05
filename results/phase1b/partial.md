## partial (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 127s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| 10gbe, W=30s, partial=False | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.13 |
| 10gbe, W=30s, partial=False | evacuate | 2180 | -258 ± 216 | -11% | +0.24 | 5.7 | 142 | 0 | 0.13 |
| 10gbe, W=30s, partial=False | hybrid | 977 | -1461 ± 460 | -60% | +0.15 | 5.7 | 135 | 48853 | 0.13 |
| 10gbe, W=30s, partial=True | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.13 |
| 10gbe, W=30s, partial=True | evacuate | 2161 | -277 ± 227 | -11% | +0.23 | 5.6 | 144 | 0 | 0.13 |
| 10gbe, W=30s, partial=True | hybrid | 1095 | -1343 ± 462 | -55% | +0.16 | 5.0 | 138 | 45538 | 0.13 |
| 10gbe, W=120s, partial=False | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 0.50 |
| 10gbe, W=120s, partial=False | evacuate | 1874 | -433 ± 268 | -19% | +0.20 | 1.4 | 535 | 0 | 0.50 |
| 10gbe, W=120s, partial=False | hybrid | 978 | -1329 ± 337 | -58% | +0.14 | 1.4 | 481 | 49354 | 0.50 |
| 10gbe, W=120s, partial=True | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 0.50 |
| 10gbe, W=120s, partial=True | evacuate | 1763 | -544 ± 259 | -24% | +0.18 | 1.4 | 542 | 0 | 0.50 |
| 10gbe, W=120s, partial=True | hybrid | 1011 | -1296 ± 334 | -56% | +0.14 | 1.3 | 489 | 48887 | 0.50 |
| 25gbe, W=30s, partial=False | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| 25gbe, W=30s, partial=False | evacuate | 1873 | -566 ± 248 | -23% | +0.19 | 4.8 | 335 | 0 | 0.32 |
| 25gbe, W=30s, partial=False | hybrid | 1021 | -1417 ± 502 | -58% | +0.13 | 5.2 | 307 | 46972 | 0.32 |
| 25gbe, W=30s, partial=True | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| 25gbe, W=30s, partial=True | evacuate | 1845 | -593 ± 257 | -24% | +0.20 | 4.9 | 336 | 0 | 0.32 |
| 25gbe, W=30s, partial=True | hybrid | 1063 | -1375 ± 463 | -56% | +0.14 | 5.4 | 319 | 47870 | 0.32 |
| 25gbe, W=120s, partial=False | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| 25gbe, W=120s, partial=False | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| 25gbe, W=120s, partial=False | hybrid | 1022 | -1285 ± 349 | -56% | +0.17 | 1.3 | 798 | 49962 | 1.25 |
| 25gbe, W=120s, partial=True | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| 25gbe, W=120s, partial=True | evacuate | 1285 | -1022 ± 293 | -44% | +0.15 | 1.5 | 1113 | 0 | 1.25 |
| 25gbe, W=120s, partial=True | hybrid | 1139 | -1168 ± 368 | -51% | +0.18 | 1.2 | 797 | 49799 | 1.25 |
