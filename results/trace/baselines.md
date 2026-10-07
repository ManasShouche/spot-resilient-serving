## baselines (6 seeds, real AgentX sessions from agentx.jsonl, resampled with replacement to the setting's session count, assumed hardware constants; 217s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | displaced TTFT p99 (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|---|
| independent, W=0s | recompute | 1673 | — | — | +0.10 | 155.4 | 11.7 | 0 | 0 | 0.00 |
| independent, W=0s | evacuate | 1673 | +0 ± 0 | +0% | +0.10 | 155.4 | 11.7 | 0 | 0 | 0.00 |
| independent, W=0s | replicate | 578 | -1095 ± 541 | -65% | +0.10 | 84.4 | 10.2 | 0 | 50676 | 0.00 |
| independent, W=0s | hybrid | 578 | -1095 ± 541 | -65% | +0.10 | 84.4 | 10.2 | 0 | 50676 | 0.00 |
| independent, W=0s | inflight_replicate | 1083 | -590 ± 347 | -35% | +0.01 | 127.8 | 11.3 | 0 | 584115 | 0.00 |
| independent, W=0s | pool | 533 | -1140 ± 418 | -68% | +0.08 | 94.6 | 11.0 | 0 | 44382 | 0.00 |
| independent, W=0s | pool x2 | 502 | -1171 ± 425 | -70% | +0.04 | 92.6 | 11.0 | 0 | 88893 | 0.00 |
| independent, W=30s | recompute | 1618 | — | — | +0.03 | 135.9 | 11.0 | 0 | 0 | 0.39 |
| independent, W=30s | evacuate | 1377 | -240 ± 254 | -15% | +0.02 | 120.3 | 5.0 | 316 | 0 | 0.41 |
| independent, W=30s | replicate | 606 | -1012 ± 449 | -63% | +0.15 | 108.3 | 12.3 | 0 | 50429 | 0.40 |
| independent, W=30s | hybrid | 549 | -1068 ± 364 | -66% | +0.26 | 88.1 | 5.5 | 280 | 50638 | 0.40 |
| independent, W=30s | inflight_replicate | 1084 | -534 ± 362 | -33% | -0.01 | 124.2 | 12.7 | 0 | 584132 | 0.39 |
| independent, W=30s | pool | 517 | -1100 ± 341 | -68% | +0.28 | 108.2 | 11.2 | 0 | 43582 | 0.40 |
| independent, W=30s | pool x2 | 454 | -1164 ± 424 | -72% | +0.32 | 96.6 | 11.2 | 0 | 89046 | 0.40 |
| independent, W=120s | recompute | 1560 | — | — | -0.07 | 145.8 | 10.5 | 0 | 0 | 1.58 |
| independent, W=120s | evacuate | 792 | -767 ± 230 | -49% | +0.19 | 128.7 | 1.0 | 1021 | 0 | 1.62 |
| independent, W=120s | replicate | 561 | -999 ± 318 | -64% | +0.12 | 103.5 | 10.8 | 0 | 49646 | 1.58 |
| independent, W=120s | hybrid | 471 | -1089 ± 373 | -70% | +0.13 | 134.1 | 1.3 | 710 | 50161 | 1.59 |
| independent, W=120s | inflight_replicate | 995 | -565 ± 395 | -36% | +0.03 | 112.5 | 10.8 | 0 | 584108 | 1.63 |
| independent, W=120s | pool | 428 | -1132 ± 294 | -73% | +0.11 | 107.0 | 10.7 | 0 | 44187 | 1.59 |
| independent, W=120s | pool x2 | 479 | -1081 ± 425 | -69% | +0.12 | 111.8 | 10.0 | 0 | 87659 | 1.56 |
| correlated, W=0s | recompute | 2117 | — | — | +0.03 | 162.0 | 11.2 | 0 | 0 | 0.00 |
| correlated, W=0s | evacuate | 2117 | +0 ± 0 | +0% | +0.03 | 162.0 | 11.2 | 0 | 0 | 0.00 |
| correlated, W=0s | replicate | 1018 | -1099 ± 338 | -52% | +0.42 | 108.8 | 11.0 | 0 | 50232 | 0.00 |
| correlated, W=0s | hybrid | 1018 | -1099 ± 338 | -52% | +0.42 | 108.8 | 11.0 | 0 | 50232 | 0.00 |
| correlated, W=0s | inflight_replicate | 1614 | -503 ± 224 | -24% | +0.10 | 113.8 | 10.7 | 0 | 584121 | 0.00 |
| correlated, W=0s | pool | 995 | -1122 ± 463 | -53% | +0.22 | 122.3 | 11.2 | 0 | 43307 | 0.00 |
| correlated, W=0s | pool x2 | 845 | -1272 ± 407 | -60% | +0.13 | 100.9 | 11.3 | 0 | 86735 | 0.00 |
| correlated, W=30s | recompute | 2110 | — | — | +0.12 | 150.9 | 11.0 | 0 | 0 | 0.27 |
| correlated, W=30s | evacuate | 1939 | -171 ± 457 | -8% | +0.05 | 146.5 | 3.5 | 316 | 0 | 0.27 |
| correlated, W=30s | replicate | 1001 | -1109 ± 250 | -53% | +0.46 | 103.7 | 10.5 | 0 | 50200 | 0.27 |
| correlated, W=30s | hybrid | 972 | -1139 ± 153 | -54% | +0.41 | 105.5 | 3.8 | 304 | 50134 | 0.27 |
| correlated, W=30s | inflight_replicate | 1650 | -461 ± 276 | -22% | +0.17 | 116.0 | 10.2 | 0 | 584111 | 0.27 |
| correlated, W=30s | pool | 979 | -1131 ± 387 | -54% | +0.12 | 128.7 | 11.2 | 0 | 43787 | 0.27 |
| correlated, W=30s | pool x2 | 877 | -1233 ± 314 | -58% | +0.13 | 92.3 | 10.8 | 0 | 87861 | 0.27 |
| correlated, W=120s | recompute | 2155 | — | — | +0.06 | 127.0 | 9.8 | 0 | 0 | 1.08 |
| correlated, W=120s | evacuate | 1165 | -990 ± 282 | -46% | +0.15 | 118.5 | 0.5 | 1220 | 0 | 1.08 |
| correlated, W=120s | replicate | 1024 | -1131 ± 299 | -52% | +0.26 | 108.1 | 10.3 | 0 | 50256 | 1.07 |
| correlated, W=120s | hybrid | 857 | -1298 ± 269 | -60% | +0.42 | 136.0 | 0.3 | 829 | 50727 | 1.06 |
| correlated, W=120s | inflight_replicate | 1633 | -522 ± 351 | -24% | +0.12 | 112.1 | 9.8 | 0 | 584109 | 1.08 |
| correlated, W=120s | pool | 994 | -1161 ± 419 | -54% | +0.20 | 106.0 | 10.3 | 0 | 43763 | 1.06 |
| correlated, W=120s | pool x2 | 837 | -1318 ± 305 | -61% | +0.11 | 113.8 | 10.3 | 0 | 87194 | 1.07 |
