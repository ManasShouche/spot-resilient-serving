## hinted (6 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 152s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | displaced TTFT p99 (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|---|
| hint accuracy 0.00, W=30s | recompute | 2317 | — | — | +0.21 | 178.8 | 25.0 | 0 | 0 | 0.10 |
| hint accuracy 0.00, W=30s | evacuate | 2004 | -313 ± 480 | -14% | +0.19 | 174.8 | 7.3 | 127 | 0 | 0.10 |
| hint accuracy 0.50, W=30s | recompute | 2317 | — | — | +0.21 | 178.8 | 25.0 | 0 | 0 | 0.10 |
| hint accuracy 0.50, W=30s | evacuate | 1814 | -503 ± 414 | -22% | +0.17 | 163.3 | 7.2 | 132 | 0 | 0.10 |
| hint accuracy 0.80, W=30s | recompute | 2317 | — | — | +0.21 | 178.8 | 25.0 | 0 | 0 | 0.10 |
| hint accuracy 0.80, W=30s | evacuate | 1742 | -575 ± 500 | -25% | +0.16 | 156.5 | 6.3 | 132 | 0 | 0.10 |
| hint accuracy 0.95, W=30s | recompute | 2317 | — | — | +0.21 | 178.8 | 25.0 | 0 | 0 | 0.10 |
| hint accuracy 0.95, W=30s | evacuate | 1781 | -536 ± 381 | -23% | +0.17 | 155.4 | 6.3 | 129 | 0 | 0.10 |
| hint accuracy 1.00, W=30s | recompute | 2317 | — | — | +0.21 | 178.8 | 25.0 | 0 | 0 | 0.10 |
| hint accuracy 1.00, W=30s | evacuate | 1799 | -518 ± 365 | -22% | +0.17 | 150.1 | 6.3 | 126 | 0 | 0.10 |
| hint accuracy 0.00, W=120s | recompute | 2133 | — | — | +0.20 | 174.2 | 23.5 | 0 | 0 | 0.40 |
| hint accuracy 0.00, W=120s | evacuate | 1256 | -877 ± 650 | -41% | +0.13 | 132.2 | 1.7 | 488 | 0 | 0.40 |
| hint accuracy 0.50, W=120s | recompute | 2133 | — | — | +0.20 | 174.2 | 23.5 | 0 | 0 | 0.40 |
| hint accuracy 0.50, W=120s | evacuate | 1343 | -790 ± 432 | -37% | +0.15 | 111.4 | 1.8 | 499 | 0 | 0.40 |
| hint accuracy 0.80, W=120s | recompute | 2133 | — | — | +0.20 | 174.2 | 23.5 | 0 | 0 | 0.40 |
| hint accuracy 0.80, W=120s | evacuate | 1176 | -957 ± 466 | -45% | +0.12 | 112.2 | 2.2 | 503 | 0 | 0.40 |
| hint accuracy 0.95, W=120s | recompute | 2133 | — | — | +0.20 | 174.2 | 23.5 | 0 | 0 | 0.40 |
| hint accuracy 0.95, W=120s | evacuate | 1201 | -932 ± 453 | -44% | +0.12 | 116.8 | 2.2 | 408 | 0 | 0.40 |
| hint accuracy 1.00, W=120s | recompute | 2133 | — | — | +0.20 | 174.2 | 23.5 | 0 | 0 | 0.40 |
| hint accuracy 1.00, W=120s | evacuate | 1137 | -996 ± 459 | -47% | +0.12 | 122.6 | 2.2 | 376 | 0 | 0.40 |
