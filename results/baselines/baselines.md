## baselines (6 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 359s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | displaced TTFT p99 (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|---|
| independent, W=0s | recompute | 2125 | — | — | +0.20 | 187.1 | 24.3 | 0 | 0 | 0.00 |
| independent, W=0s | evacuate | 2125 | +0 ± 0 | +0% | +0.20 | 187.1 | 24.3 | 0 | 0 | 0.00 |
| independent, W=0s | replicate | 862 | -1263 ± 668 | -59% | +0.08 | 70.1 | 24.8 | 0 | 44705 | 0.00 |
| independent, W=0s | hybrid | 862 | -1263 ± 668 | -59% | +0.08 | 70.1 | 24.8 | 0 | 44705 | 0.00 |
| independent, W=0s | inflight_replicate | 1711 | -414 ± 267 | -20% | +0.17 | 150.2 | 23.0 | 0 | 595533 | 0.00 |
| independent, W=0s | pool | 895 | -1230 ± 818 | -58% | +0.14 | 97.7 | 21.8 | 0 | 25095 | 0.00 |
| independent, W=0s | pool x2 | 959 | -1166 ± 837 | -55% | +0.14 | 100.5 | 23.5 | 0 | 68888 | 0.00 |
| independent, W=30s | recompute | 2317 | — | — | +0.21 | 178.8 | 25.0 | 0 | 0 | 0.25 |
| independent, W=30s | evacuate | 1692 | -625 ± 429 | -27% | +0.16 | 149.8 | 5.0 | 329 | 0 | 0.26 |
| independent, W=30s | replicate | 732 | -1585 ± 759 | -68% | +0.08 | 87.0 | 26.3 | 0 | 44837 | 0.25 |
| independent, W=30s | hybrid | 642 | -1675 ± 868 | -72% | +0.05 | 57.0 | 6.2 | 305 | 46293 | 0.25 |
| independent, W=30s | inflight_replicate | 1814 | -503 ± 464 | -22% | +0.17 | 162.2 | 22.2 | 0 | 592142 | 0.25 |
| independent, W=30s | pool | 1127 | -1190 ± 923 | -51% | +0.27 | 98.1 | 24.7 | 0 | 25264 | 0.26 |
| independent, W=30s | pool x2 | 908 | -1409 ± 786 | -61% | +0.13 | 98.4 | 24.2 | 0 | 68293 | 0.26 |
| independent, W=120s | recompute | 2133 | — | — | +0.20 | 174.2 | 23.5 | 0 | 0 | 1.01 |
| independent, W=120s | evacuate | 1024 | -1109 ± 591 | -52% | +0.10 | 125.5 | 1.5 | 1070 | 0 | 0.99 |
| independent, W=120s | replicate | 662 | -1471 ± 635 | -69% | +0.07 | 66.8 | 26.5 | 0 | 42711 | 1.02 |
| independent, W=120s | hybrid | 812 | -1321 ± 615 | -62% | +0.11 | 100.8 | 1.7 | 787 | 46122 | 1.00 |
| independent, W=120s | inflight_replicate | 1771 | -362 ± 662 | -17% | +0.18 | 134.8 | 26.2 | 0 | 595791 | 1.00 |
| independent, W=120s | pool | 1132 | -1001 ± 810 | -47% | +0.26 | 109.2 | 29.3 | 0 | 25295 | 1.00 |
| independent, W=120s | pool x2 | 657 | -1476 ± 750 | -69% | +0.09 | 67.9 | 24.8 | 0 | 68340 | 1.01 |
| correlated, W=0s | recompute | 2261 | — | — | +0.21 | 217.8 | 19.7 | 0 | 0 | 0.00 |
| correlated, W=0s | evacuate | 2261 | +0 ± 0 | +0% | +0.21 | 217.8 | 19.7 | 0 | 0 | 0.00 |
| correlated, W=0s | replicate | 1069 | -1192 ± 508 | -53% | +0.11 | 70.1 | 19.8 | 0 | 40174 | 0.00 |
| correlated, W=0s | hybrid | 1069 | -1192 ± 508 | -53% | +0.11 | 70.1 | 19.8 | 0 | 40174 | 0.00 |
| correlated, W=0s | inflight_replicate | 1969 | -293 ± 197 | -13% | +0.18 | 200.4 | 20.5 | 0 | 596935 | 0.00 |
| correlated, W=0s | pool | 1547 | -714 ± 549 | -32% | +0.50 | 249.5 | 21.0 | 0 | 27148 | 0.00 |
| correlated, W=0s | pool x2 | 1257 | -1004 ± 670 | -44% | +0.27 | 142.7 | 20.8 | 0 | 69003 | 0.00 |
| correlated, W=30s | recompute | 2605 | — | — | +0.23 | 191.2 | 20.8 | 0 | 0 | 0.17 |
| correlated, W=30s | evacuate | 2232 | -373 ± 183 | -14% | +0.20 | 167.8 | 5.8 | 306 | 0 | 0.17 |
| correlated, W=30s | replicate | 1188 | -1417 ± 438 | -54% | +0.13 | 64.5 | 20.2 | 0 | 41675 | 0.17 |
| correlated, W=30s | hybrid | 1044 | -1561 ± 499 | -60% | +0.12 | 71.5 | 5.7 | 280 | 40139 | 0.17 |
| correlated, W=30s | inflight_replicate | 1833 | -772 ± 534 | -30% | +0.17 | 197.2 | 20.5 | 0 | 596600 | 0.17 |
| correlated, W=30s | pool | 1285 | -1320 ± 542 | -51% | +0.54 | 174.7 | 20.3 | 0 | 26813 | 0.17 |
| correlated, W=30s | pool x2 | 996 | -1609 ± 482 | -62% | +0.32 | 112.6 | 19.7 | 0 | 69061 | 0.17 |
| correlated, W=120s | recompute | 2528 | — | — | +0.21 | 204.5 | 20.0 | 0 | 0 | 0.69 |
| correlated, W=120s | evacuate | 1423 | -1105 ± 590 | -44% | +0.14 | 149.0 | 1.2 | 1092 | 0 | 0.68 |
| correlated, W=120s | replicate | 1116 | -1412 ± 598 | -56% | +0.12 | 60.8 | 19.5 | 0 | 39785 | 0.68 |
| correlated, W=120s | hybrid | 1019 | -1509 ± 641 | -60% | +0.13 | 104.5 | 1.2 | 734 | 39185 | 0.68 |
| correlated, W=120s | inflight_replicate | 1993 | -535 ± 302 | -21% | +0.18 | 166.3 | 20.0 | 0 | 595423 | 0.68 |
| correlated, W=120s | pool | 1281 | -1246 ± 626 | -49% | +0.41 | 169.6 | 19.3 | 0 | 27050 | 0.69 |
| correlated, W=120s | pool x2 | 1220 | -1308 ± 680 | -52% | +0.31 | 138.6 | 19.2 | 0 | 69166 | 0.69 |
