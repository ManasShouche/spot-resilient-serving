## sensitivity (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 190s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| cache 2M | recompute | 2002 | — | — | +0.41 | 31.4 | 0 | 0 | 1.80 |
| cache 2M | drain_local | 2499 | +497 ± 550 | +25% | +0.49 | 1.2 | 0 | 0 | 1.77 |
| cache 2M | evacuate | 1648 | -354 ± 490 | -18% | +0.40 | 2.2 | 782 | 0 | 1.78 |
| cache 2M | replicate | 1769 | -232 ± 626 | -12% | +0.35 | 30.9 | 0 | 106974 | 1.79 |
| cache 2M | hybrid | 1368 | -634 ± 490 | -32% | +0.41 | 1.5 | 442 | 103613 | 1.80 |
| cache 8M | recompute | 2175 | — | — | +0.17 | 22.5 | 0 | 0 | 1.05 |
| cache 8M | drain_local | 2135 | -40 ± 176 | -2% | +0.19 | 1.2 | 0 | 0 | 1.04 |
| cache 8M | evacuate | 1093 | -1082 ± 385 | -50% | +0.09 | 1.5 | 1259 | 0 | 1.04 |
| cache 8M | replicate | 452 | -1723 ± 552 | -79% | +0.04 | 25.6 | 0 | 29526 | 1.05 |
| cache 8M | hybrid | 331 | -1844 ± 528 | -85% | +0.05 | 1.0 | 1110 | 29327 | 1.04 |
| load 400 sessions | recompute | 1010 | — | — | +0.07 | 10.9 | 0 | 0 | 2.23 |
| load 400 sessions | drain_local | 1029 | +20 ± 145 | +2% | +0.07 | 0.8 | 0 | 0 | 2.22 |
| load 400 sessions | evacuate | 377 | -633 ± 174 | -63% | +0.03 | 0.6 | 1141 | 0 | 2.24 |
| load 400 sessions | replicate | 207 | -803 ± 211 | -79% | +0.02 | 11.8 | 0 | 14141 | 2.21 |
| load 400 sessions | hybrid | 164 | -846 ± 227 | -84% | +0.02 | 0.6 | 838 | 14804 | 2.21 |
| load 1200 sessions | recompute | 3007 | — | — | +0.63 | 45.4 | 0 | 0 | 1.08 |
| load 1200 sessions | drain_local | 3042 | +35 ± 508 | +1% | +0.67 | 3.2 | 0 | 0 | 1.08 |
| load 1200 sessions | evacuate | 2360 | -647 ± 570 | -22% | +0.66 | 3.1 | 1030 | 0 | 1.08 |
| load 1200 sessions | replicate | 1658 | -1349 ± 505 | -45% | +0.48 | 43.1 | 0 | 103023 | 1.08 |
| load 1200 sessions | hybrid | 1321 | -1686 ± 620 | -56% | +0.40 | 4.3 | 727 | 101960 | 1.07 |
| 70B on 4xH100 | recompute | 1922 | — | — | +0.18 | 32.2 | 0 | 0 | 0.64 |
| 70B on 4xH100 | drain_local | 1846 | -76 ± 163 | -4% | +0.18 | 3.3 | 0 | 0 | 0.65 |
| 70B on 4xH100 | evacuate | 1389 | -533 ± 298 | -28% | +0.13 | 2.7 | 1333 | 0 | 0.64 |
| 70B on 4xH100 | replicate | 809 | -1114 ± 333 | -58% | +0.10 | 31.7 | 0 | 153361 | 0.64 |
| 70B on 4xH100 | hybrid | 702 | -1221 ± 369 | -63% | +0.09 | 2.6 | 1251 | 137049 | 0.64 |
| whole-group bursts | recompute | 4624 | — | — | +0.94 | 51.7 | 0 | 0 | 0.73 |
| whole-group bursts | drain_local | 4725 | +102 ± 305 | +2% | +1.02 | 2.6 | 0 | 0 | 0.73 |
| whole-group bursts | evacuate | 3583 | -1040 ± 535 | -22% | +0.77 | 2.8 | 1388 | 0 | 0.73 |
| whole-group bursts | replicate | 3357 | -1267 ± 591 | -27% | +1.02 | 49.8 | 0 | 57808 | 0.73 |
| whole-group bursts | hybrid | 2885 | -1738 ± 597 | -38% | +0.78 | 2.3 | 1068 | 51940 | 0.73 |
| quarter-group bursts | recompute | 1464 | — | — | +0.11 | 14.6 | 0 | 0 | 0.72 |
| quarter-group bursts | drain_local | 1421 | -44 ± 150 | -3% | +0.12 | 0.4 | 0 | 0 | 0.72 |
| quarter-group bursts | evacuate | 882 | -582 ± 130 | -40% | +0.06 | 0.6 | 729 | 0 | 0.72 |
| quarter-group bursts | replicate | 602 | -863 ± 134 | -59% | +0.06 | 15.1 | 0 | 52015 | 0.72 |
| quarter-group bursts | hybrid | 597 | -867 ± 188 | -59% | +0.07 | 0.6 | 509 | 48159 | 0.73 |
| replica tier 1M | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| replica tier 1M | drain_local | 2315 | +8 ± 227 | +0% | +0.25 | 1.2 | 0 | 0 | 1.26 |
| replica tier 1M | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| replica tier 1M | replicate | 1589 | -718 ± 357 | -31% | +0.15 | 23.7 | 0 | 327670 | 1.27 |
| replica tier 1M | hybrid | 960 | -1347 ± 411 | -58% | +0.13 | 1.2 | 1060 | 322622 | 1.25 |
