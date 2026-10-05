## reuse (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 60s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| fixed, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| fixed, W=30s | evacuate | 1873 | -566 ± 248 | -23% | +0.19 | 4.8 | 335 | 0 | 0.32 |
| recency, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| recency, W=30s | evacuate | 1755 | -683 ± 273 | -28% | +0.18 | 4.7 | 285 | 0 | 0.32 |
| oracle, W=30s | recompute | 2438 | — | — | +0.25 | 25.9 | 0 | 0 | 0.32 |
| oracle, W=30s | evacuate | 1550 | -889 ± 291 | -36% | +0.19 | 5.2 | 280 | 0 | 0.32 |
| fixed, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| fixed, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| recency, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| recency, W=120s | evacuate | 1212 | -1095 ± 228 | -47% | +0.15 | 1.4 | 954 | 0 | 1.25 |
| oracle, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| oracle, W=120s | evacuate | 906 | -1401 ± 301 | -61% | +0.15 | 1.6 | 604 | 0 | 1.26 |
