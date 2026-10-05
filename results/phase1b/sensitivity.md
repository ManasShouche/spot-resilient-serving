## sensitivity (6 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 84s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| cache 2M | recompute | 1632 | — | — | +0.33 | 28.5 | 0 | 0 | 1.52 |
| cache 2M | drain_local | 2494 | +862 ± 784 | +53% | +0.40 | 1.2 | 0 | 0 | 1.47 |
| cache 2M | evacuate | 1121 | -512 ± 698 | -31% | +0.25 | 1.7 | 779 | 0 | 1.51 |
| cache 2M | replicate | 1663 | +30 ± 872 | +2% | +0.34 | 30.2 | 0 | 106856 | 1.52 |
| cache 2M | hybrid | 1180 | -453 ± 759 | -28% | +0.25 | 1.5 | 450 | 108607 | 1.52 |
| cache 8M | recompute | 2072 | — | — | +0.17 | 23.0 | 0 | 0 | 0.79 |
| cache 8M | drain_local | 1987 | -85 ± 201 | -4% | +0.16 | 0.8 | 0 | 0 | 0.78 |
| cache 8M | evacuate | 1045 | -1027 ± 668 | -50% | +0.08 | 1.3 | 1222 | 0 | 0.78 |
| cache 8M | replicate | 1099 | -974 ± 717 | -47% | +0.11 | 24.8 | 0 | 28363 | 0.78 |
| cache 8M | hybrid | 255 | -1818 ± 1037 | -88% | +0.04 | 0.7 | 1054 | 28045 | 0.78 |
| load 400 sessions | recompute | 821 | — | — | +0.06 | 11.3 | 0 | 0 | 1.44 |
| load 400 sessions | drain_local | 775 | -46 ± 164 | -6% | +0.05 | 0.3 | 0 | 0 | 1.41 |
| load 400 sessions | evacuate | 289 | -531 ± 239 | -65% | +0.03 | 0.3 | 1061 | 0 | 1.46 |
| load 400 sessions | replicate | 519 | -302 ± 202 | -37% | +0.04 | 13.0 | 0 | 14362 | 1.39 |
| load 400 sessions | hybrid | 121 | -699 ± 324 | -85% | +0.02 | 0.3 | 743 | 14258 | 1.42 |
| load 1200 sessions | recompute | 2962 | — | — | +0.57 | 41.0 | 0 | 0 | 0.86 |
| load 1200 sessions | drain_local | 3137 | +175 ± 395 | +6% | +0.60 | 1.7 | 0 | 0 | 0.85 |
| load 1200 sessions | evacuate | 1728 | -1234 ± 764 | -42% | +0.43 | 1.0 | 1008 | 0 | 0.86 |
| load 1200 sessions | replicate | 2926 | -36 ± 914 | -1% | +0.57 | 45.2 | 0 | 91456 | 0.85 |
| load 1200 sessions | hybrid | 1792 | -1170 ± 482 | -39% | +0.52 | 2.3 | 662 | 89438 | 0.85 |
| 70B on 4xH100 | recompute | 1686 | — | — | +0.15 | 30.7 | 0 | 0 | 0.41 |
| 70B on 4xH100 | drain_local | 1533 | -153 ± 194 | -9% | +0.14 | 2.0 | 0 | 0 | 0.42 |
| 70B on 4xH100 | evacuate | 1309 | -377 ± 444 | -22% | +0.13 | 2.3 | 1278 | 0 | 0.42 |
| 70B on 4xH100 | replicate | 1304 | -382 ± 588 | -23% | +0.13 | 29.3 | 0 | 131652 | 0.41 |
| 70B on 4xH100 | hybrid | 761 | -924 ± 589 | -55% | +0.12 | 2.8 | 1228 | 139749 | 0.42 |
| whole-group bursts | recompute | 4501 | — | — | +0.87 | 47.0 | 0 | 0 | 0.62 |
| whole-group bursts | drain_local | 4608 | +107 ± 156 | +2% | +0.88 | 2.0 | 0 | 0 | 0.62 |
| whole-group bursts | evacuate | 3809 | -691 ± 627 | -15% | +0.69 | 1.8 | 1187 | 0 | 0.62 |
| whole-group bursts | replicate | 4346 | -154 ± 639 | -3% | +1.00 | 45.7 | 0 | 43997 | 0.62 |
| whole-group bursts | hybrid | 3064 | -1436 ± 1226 | -32% | +0.63 | 2.0 | 1151 | 39587 | 0.62 |
| quarter-group bursts | recompute | 1485 | — | — | +0.08 | 12.7 | 0 | 0 | 0.67 |
| quarter-group bursts | drain_local | 1509 | +25 ± 139 | +2% | +0.08 | 0.3 | 0 | 0 | 0.67 |
| quarter-group bursts | evacuate | 1044 | -440 ± 310 | -30% | +0.07 | 0.2 | 754 | 0 | 0.68 |
| quarter-group bursts | replicate | 1200 | -284 ± 249 | -19% | +0.09 | 13.3 | 0 | 44827 | 0.67 |
| quarter-group bursts | hybrid | 714 | -771 ± 192 | -52% | +0.07 | 0.2 | 489 | 43213 | 0.68 |
| replica tier 1M | recompute | 2133 | — | — | +0.20 | 23.5 | 0 | 0 | 1.01 |
| replica tier 1M | drain_local | 1999 | -133 ± 370 | -6% | +0.18 | 1.2 | 0 | 0 | 1.00 |
| replica tier 1M | evacuate | 1262 | -871 ± 407 | -41% | +0.13 | 1.7 | 1051 | 0 | 0.99 |
| replica tier 1M | replicate | 1811 | -322 ± 310 | -15% | +0.18 | 27.2 | 0 | 317144 | 1.00 |
| replica tier 1M | hybrid | 900 | -1233 ± 542 | -58% | +0.10 | 1.8 | 984 | 315590 | 0.99 |
