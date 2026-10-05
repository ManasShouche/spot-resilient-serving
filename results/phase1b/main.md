## main (20 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 237s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| independent, W=0s | recompute | 2053 | — | — | +0.18 | 21.9 | 0 | 0 | 0.00 |
| independent, W=0s | drain_local | 2053 | +0 ± 0 | +0% | +0.18 | 21.9 | 0 | 0 | 0.00 |
| independent, W=0s | evacuate | 2053 | +0 ± 0 | +0% | +0.18 | 21.9 | 0 | 0 | 0.00 |
| independent, W=0s | replicate | 968 | -1085 ± 272 | -53% | +0.11 | 22.6 | 0 | 47040 | 0.00 |
| independent, W=0s | hybrid | 968 | -1085 ± 272 | -53% | +0.11 | 22.6 | 0 | 47040 | 0.00 |
| independent, W=30s | recompute | 2157 | — | — | +0.20 | 23.1 | 0 | 0 | 0.50 |
| independent, W=30s | drain_local | 2051 | -106 ± 173 | -5% | +0.19 | 5.3 | 0 | 0 | 0.50 |
| independent, W=30s | evacuate | 1733 | -424 ± 205 | -20% | +0.16 | 5.0 | 329 | 0 | 0.50 |
| independent, W=30s | replicate | 965 | -1192 ± 349 | -55% | +0.12 | 24.8 | 0 | 47438 | 0.50 |
| independent, W=30s | hybrid | 915 | -1243 ± 349 | -58% | +0.11 | 5.5 | 297 | 47144 | 0.50 |
| independent, W=120s | recompute | 2124 | — | — | +0.20 | 22.2 | 0 | 0 | 2.00 |
| independent, W=120s | drain_local | 2113 | -11 ± 181 | -1% | +0.20 | 1.0 | 0 | 0 | 2.00 |
| independent, W=120s | evacuate | 1226 | -899 ± 251 | -42% | +0.13 | 1.4 | 1098 | 0 | 2.00 |
| independent, W=120s | replicate | 878 | -1247 ± 267 | -59% | +0.10 | 23.6 | 0 | 45887 | 2.01 |
| independent, W=120s | hybrid | 944 | -1180 ± 246 | -56% | +0.14 | 1.2 | 784 | 48076 | 2.00 |
| correlated, W=0s | recompute | 2197 | — | — | +0.18 | 20.9 | 0 | 0 | 0.00 |
| correlated, W=0s | drain_local | 2197 | +0 ± 0 | +0% | +0.18 | 20.9 | 0 | 0 | 0.00 |
| correlated, W=0s | evacuate | 2197 | +0 ± 0 | +0% | +0.18 | 20.9 | 0 | 0 | 0.00 |
| correlated, W=0s | replicate | 941 | -1256 ± 215 | -57% | +0.10 | 21.7 | 0 | 40701 | 0.00 |
| correlated, W=0s | hybrid | 941 | -1256 ± 215 | -57% | +0.10 | 21.7 | 0 | 40701 | 0.00 |
| correlated, W=30s | recompute | 2306 | — | — | +0.19 | 21.4 | 0 | 0 | 0.18 |
| correlated, W=30s | drain_local | 2275 | -31 ± 122 | -1% | +0.20 | 5.8 | 0 | 0 | 0.18 |
| correlated, W=30s | evacuate | 1934 | -372 ± 103 | -16% | +0.16 | 6.0 | 344 | 0 | 0.18 |
| correlated, W=30s | replicate | 953 | -1352 ± 199 | -59% | +0.12 | 21.4 | 0 | 40902 | 0.18 |
| correlated, W=30s | hybrid | 944 | -1362 ± 208 | -59% | +0.13 | 5.7 | 314 | 40855 | 0.18 |
| correlated, W=120s | recompute | 2368 | — | — | +0.20 | 21.6 | 0 | 0 | 0.71 |
| correlated, W=120s | drain_local | 2319 | -49 ± 110 | -2% | +0.20 | 1.1 | 0 | 0 | 0.71 |
| correlated, W=120s | evacuate | 1352 | -1016 ± 244 | -43% | +0.14 | 1.0 | 1130 | 0 | 0.71 |
| correlated, W=120s | replicate | 935 | -1433 ± 244 | -61% | +0.11 | 21.8 | 0 | 40263 | 0.71 |
| correlated, W=120s | hybrid | 918 | -1450 ± 247 | -61% | +0.13 | 0.9 | 825 | 39607 | 0.71 |
