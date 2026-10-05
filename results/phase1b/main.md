## main (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 150s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| independent, W=0s | recompute | 2212 | — | — | +0.23 | 23.9 | 0 | 0 | 0.00 |
| independent, W=0s | drain_local | 2212 | +0 ± 0 | +0% | +0.23 | 23.9 | 0 | 0 | 0.00 |
| independent, W=0s | evacuate | 2212 | +0 ± 0 | +0% | +0.23 | 23.9 | 0 | 0 | 0.00 |
| independent, W=0s | replicate | 1082 | -1129 ± 349 | -51% | +0.14 | 24.8 | 0 | 48139 | 0.00 |
| independent, W=0s | hybrid | 1082 | -1129 ± 349 | -51% | +0.14 | 24.8 | 0 | 48139 | 0.00 |
| independent, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| independent, W=30s | drain_local | 2259 | -179 ± 226 | -7% | +0.25 | 6.0 | 0 | 0 | 0.32 |
| independent, W=30s | evacuate | 1873 | -566 ± 248 | -23% | +0.19 | 4.8 | 335 | 0 | 0.32 |
| independent, W=30s | replicate | 1003 | -1435 ± 463 | -59% | +0.13 | 27.4 | 0 | 49713 | 0.32 |
| independent, W=30s | hybrid | 1021 | -1417 ± 502 | -58% | +0.13 | 5.2 | 307 | 46972 | 0.32 |
| independent, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| independent, W=120s | drain_local | 2315 | +8 ± 227 | +0% | +0.25 | 1.2 | 0 | 0 | 1.26 |
| independent, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| independent, W=120s | replicate | 981 | -1325 ± 422 | -57% | +0.12 | 25.5 | 0 | 47550 | 1.27 |
| independent, W=120s | hybrid | 1022 | -1285 ± 349 | -56% | +0.17 | 1.3 | 798 | 49962 | 1.25 |
| correlated, W=0s | recompute | 2155 | — | — | +0.18 | 19.5 | 0 | 0 | 0.00 |
| correlated, W=0s | drain_local | 2155 | +0 ± 0 | +0% | +0.18 | 19.5 | 0 | 0 | 0.00 |
| correlated, W=0s | evacuate | 2155 | +0 ± 0 | +0% | +0.18 | 19.5 | 0 | 0 | 0.00 |
| correlated, W=0s | replicate | 915 | -1240 ± 303 | -58% | +0.10 | 20.4 | 0 | 41234 | 0.00 |
| correlated, W=0s | hybrid | 915 | -1240 ± 303 | -58% | +0.10 | 20.4 | 0 | 41234 | 0.00 |
| correlated, W=30s | recompute | 2294 | — | — | +0.20 | 20.7 | 0 | 0 | 0.17 |
| correlated, W=30s | drain_local | 2209 | -85 ± 180 | -4% | +0.20 | 5.8 | 0 | 0 | 0.17 |
| correlated, W=30s | evacuate | 1976 | -318 ± 128 | -14% | +0.17 | 5.5 | 315 | 0 | 0.17 |
| correlated, W=30s | replicate | 1018 | -1276 ± 256 | -56% | +0.13 | 20.4 | 0 | 43011 | 0.17 |
| correlated, W=30s | hybrid | 890 | -1403 ± 312 | -61% | +0.13 | 5.2 | 284 | 40953 | 0.17 |
| correlated, W=120s | recompute | 2332 | — | — | +0.20 | 20.4 | 0 | 0 | 0.69 |
| correlated, W=120s | drain_local | 2307 | -25 ± 140 | -1% | +0.21 | 1.0 | 0 | 0 | 0.69 |
| correlated, W=120s | evacuate | 1365 | -967 ± 314 | -41% | +0.14 | 1.1 | 1044 | 0 | 0.69 |
| correlated, W=120s | replicate | 953 | -1378 ± 353 | -59% | +0.11 | 20.5 | 0 | 42851 | 0.69 |
| correlated, W=120s | hybrid | 942 | -1390 ± 380 | -60% | +0.14 | 1.0 | 723 | 40051 | 0.69 |
