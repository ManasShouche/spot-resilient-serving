## remote_replica (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 85s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| store replicas, unlimited, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| store replicas, unlimited, W=30s | evacuate | 1873 | -566 ± 248 | -23% | +0.19 | 4.8 | 335 | 0 | 0.32 |
| store replicas, unlimited, W=30s | replicate | 1036 | -1402 ± 369 | -58% | +0.17 | 26.0 | 0 | 49397 | 0.31 |
| store replicas, unlimited, W=30s | hybrid | 989 | -1449 ± 477 | -59% | +0.14 | 5.7 | 310 | 50442 | 0.32 |
| store replicas, unlimited, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| store replicas, unlimited, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| store replicas, unlimited, W=120s | replicate | 919 | -1388 ± 395 | -60% | +0.11 | 24.8 | 0 | 51257 | 1.27 |
| store replicas, unlimited, W=120s | hybrid | 987 | -1320 ± 330 | -57% | +0.16 | 1.4 | 800 | 50487 | 1.25 |
| store replicas, 83 MB/s, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| store replicas, 83 MB/s, W=30s | evacuate | 1873 | -566 ± 248 | -23% | +0.19 | 4.8 | 335 | 0 | 0.32 |
| store replicas, 83 MB/s, W=30s | replicate | 1650 | -788 ± 362 | -32% | +0.21 | 26.3 | 0 | 14452 | 0.32 |
| store replicas, 83 MB/s, W=30s | hybrid | 1259 | -1179 ± 361 | -48% | +0.18 | 5.0 | 332 | 14447 | 0.32 |
| store replicas, 83 MB/s, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| store replicas, 83 MB/s, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| store replicas, 83 MB/s, W=120s | replicate | 1568 | -739 ± 321 | -32% | +0.19 | 23.8 | 0 | 14509 | 1.25 |
| store replicas, 83 MB/s, W=120s | hybrid | 1164 | -1143 ± 341 | -50% | +0.16 | 1.4 | 1047 | 14409 | 1.25 |
