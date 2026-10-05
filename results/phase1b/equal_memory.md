## equal_memory (12 seeds, synthetic AgentX-calibrated workload, assumed hardware constants; 97s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|
| independent, W=30s | recompute | 2232 | — | — | +0.20 | 25.2 | 0 | 0 | 0.26 |
| independent, W=30s | drain_local | 2186 | -47 ± 155 | -2% | +0.20 | 5.6 | 0 | 0 | 0.26 |
| independent, W=30s | evacuate | 1803 | -430 ± 217 | -19% | +0.14 | 5.4 | 338 | 0 | 0.26 |
| independent, W=30s | replicate | 4252 | +2019 ± 481 | +90% | +0.42 | 27.4 | 0 | 49713 | 0.32 |
| independent, W=30s | hybrid | 4269 | +2037 ± 488 | +91% | +0.42 | 5.2 | 307 | 46972 | 0.32 |
| independent, W=120s | recompute | 2175 | — | — | +0.17 | 22.5 | 0 | 0 | 1.05 |
| independent, W=120s | drain_local | 2135 | -40 ± 176 | -2% | +0.19 | 1.2 | 0 | 0 | 1.04 |
| independent, W=120s | evacuate | 1093 | -1082 ± 385 | -50% | +0.09 | 1.5 | 1259 | 0 | 1.04 |
| independent, W=120s | replicate | 4230 | +2055 ± 377 | +94% | +0.41 | 25.5 | 0 | 47550 | 1.27 |
| independent, W=120s | hybrid | 4271 | +2096 ± 377 | +96% | +0.46 | 1.3 | 798 | 49962 | 1.25 |
| correlated, W=30s | recompute | 2203 | — | — | +0.17 | 20.2 | 0 | 0 | 0.12 |
| correlated, W=30s | drain_local | 2218 | +15 ± 78 | +1% | +0.17 | 5.4 | 0 | 0 | 0.12 |
| correlated, W=30s | evacuate | 1909 | -294 ± 160 | -13% | +0.13 | 5.3 | 335 | 0 | 0.12 |
| correlated, W=30s | replicate | 4267 | +2064 ± 326 | +94% | +0.42 | 20.4 | 0 | 43011 | 0.17 |
| correlated, W=30s | hybrid | 4139 | +1936 ± 291 | +88% | +0.42 | 5.2 | 284 | 40953 | 0.17 |
| correlated, W=120s | recompute | 2286 | — | — | +0.17 | 19.3 | 0 | 0 | 0.46 |
| correlated, W=120s | drain_local | 2234 | -52 ± 110 | -2% | +0.17 | 0.8 | 0 | 0 | 0.46 |
| correlated, W=120s | evacuate | 1241 | -1045 ± 341 | -46% | +0.08 | 0.8 | 1254 | 0 | 0.45 |
| correlated, W=120s | replicate | 4202 | +1916 ± 436 | +84% | +0.40 | 20.5 | 0 | 42851 | 0.69 |
| correlated, W=120s | hybrid | 4189 | +1903 ± 334 | +83% | +0.42 | 1.0 | 723 | 40051 | 0.69 |
