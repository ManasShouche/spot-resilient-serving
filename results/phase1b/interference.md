## interference (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 62s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| ingress slowdown 0%, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| ingress slowdown 0%, W=120s | evacuate | 1311 | -996 ± 343 | -43% | +0.16 | 1.5 | 1091 | 0 | 1.25 |
| ingress slowdown 0%, W=120s | hybrid | 1022 | -1285 ± 349 | -56% | +0.17 | 1.3 | 798 | 49962 | 1.25 |
| ingress slowdown 25%, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| ingress slowdown 25%, W=120s | evacuate | 1402 | -904 ± 296 | -39% | +0.18 | 1.5 | 1095 | 0 | 1.25 |
| ingress slowdown 25%, W=120s | hybrid | 1097 | -1210 ± 304 | -52% | +0.18 | 1.2 | 773 | 50898 | 1.25 |
| ingress slowdown 50%, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| ingress slowdown 50%, W=120s | evacuate | 1720 | -587 ± 263 | -25% | +0.22 | 1.6 | 1089 | 0 | 1.25 |
| ingress slowdown 50%, W=120s | hybrid | 1177 | -1130 ± 269 | -49% | +0.17 | 1.0 | 815 | 51683 | 1.25 |
| ingress slowdown 100%, W=120s | recompute | 2307 | — | — | +0.24 | 24.3 | 0 | 0 | 1.26 |
| ingress slowdown 100%, W=120s | evacuate | 1805 | -502 ± 304 | -22% | +0.24 | 1.5 | 1082 | 0 | 1.25 |
| ingress slowdown 100%, W=120s | hybrid | 1200 | -1107 ± 296 | -48% | +0.18 | 1.2 | 800 | 51157 | 1.26 |
