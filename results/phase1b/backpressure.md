## backpressure (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 86s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| replication unlimited, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| replication unlimited, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| replication unlimited, W=120s | replicate | 981 | -1325 ± 422 | -57% | +0.12 | 25.5 | 0 | 47550 | 1.27 |
| replication unlimited, W=120s | hybrid | 1022 | -1285 ± 349 | -56% | +0.17 | 1.3 | 798 | 49962 | 1.25 |
| replication 200 MB/s, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| replication 200 MB/s, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| replication 200 MB/s, W=120s | replicate | 1283 | -1024 ± 373 | -44% | +0.15 | 26.9 | 0 | 24600 | 1.26 |
| replication 200 MB/s, W=120s | hybrid | 1020 | -1287 ± 335 | -56% | +0.15 | 1.3 | 949 | 24425 | 1.25 |
| replication 83 MB/s, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| replication 83 MB/s, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| replication 83 MB/s, W=120s | replicate | 1737 | -570 ± 227 | -25% | +0.19 | 25.9 | 0 | 14499 | 1.25 |
| replication 83 MB/s, W=120s | hybrid | 1129 | -1178 ± 329 | -51% | +0.17 | 1.2 | 1081 | 14389 | 1.25 |
| replication 40 MB/s, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| replication 40 MB/s, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| replication 40 MB/s, W=120s | replicate | 1824 | -483 ± 264 | -21% | +0.22 | 25.0 | 0 | 8688 | 1.25 |
| replication 40 MB/s, W=120s | hybrid | 1229 | -1078 ± 297 | -47% | +0.18 | 1.2 | 1073 | 8619 | 1.25 |
