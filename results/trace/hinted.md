## hinted (6 seeds, real AgentX sessions from agentx.jsonl, resampled with replacement to the setting's session count, assumed hardware constants; 47s)

| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | Δ% | ΔTTFT mean (s) | displaced TTFT p99 (s) | killed turns | notice GB | replication GB | budget ratio |
|---|---|---|---|---|---|---|---|---|---|---|
| hint accuracy 0.00, W=30s | recompute | 1618 | — | — | +0.03 | 135.9 | 11.0 | 0 | 0 | 0.16 |
| hint accuracy 0.00, W=30s | evacuate | 1220 | -398 ± 292 | -25% | -0.02 | 115.6 | 5.5 | 124 | 0 | 0.16 |
| hint accuracy 0.50, W=30s | recompute | 1618 | — | — | +0.03 | 135.9 | 11.0 | 0 | 0 | 0.16 |
| hint accuracy 0.50, W=30s | evacuate | 1259 | -359 ± 322 | -22% | -0.05 | 118.7 | 5.0 | 122 | 0 | 0.16 |
| hint accuracy 0.80, W=30s | recompute | 1618 | — | — | +0.03 | 135.9 | 11.0 | 0 | 0 | 0.16 |
| hint accuracy 0.80, W=30s | evacuate | 1275 | -343 ± 283 | -21% | +0.03 | 130.6 | 5.7 | 122 | 0 | 0.16 |
| hint accuracy 0.95, W=30s | recompute | 1618 | — | — | +0.03 | 135.9 | 11.0 | 0 | 0 | 0.16 |
| hint accuracy 0.95, W=30s | evacuate | 1271 | -347 ± 199 | -21% | +0.01 | 130.1 | 5.7 | 124 | 0 | 0.16 |
| hint accuracy 1.00, W=30s | recompute | 1618 | — | — | +0.03 | 135.9 | 11.0 | 0 | 0 | 0.16 |
| hint accuracy 1.00, W=30s | evacuate | 1261 | -357 ± 216 | -22% | +0.01 | 130.1 | 5.7 | 125 | 0 | 0.16 |
| hint accuracy 0.00, W=120s | recompute | 1560 | — | — | -0.07 | 145.8 | 10.5 | 0 | 0 | 0.63 |
| hint accuracy 0.00, W=120s | evacuate | 989 | -571 ± 374 | -37% | +0.34 | 145.7 | 1.2 | 413 | 0 | 0.65 |
| hint accuracy 0.50, W=120s | recompute | 1560 | — | — | -0.07 | 145.8 | 10.5 | 0 | 0 | 0.63 |
| hint accuracy 0.50, W=120s | evacuate | 842 | -718 ± 239 | -46% | +0.22 | 133.9 | 1.3 | 448 | 0 | 0.64 |
| hint accuracy 0.80, W=120s | recompute | 1560 | — | — | -0.07 | 145.8 | 10.5 | 0 | 0 | 0.63 |
| hint accuracy 0.80, W=120s | evacuate | 925 | -634 ± 299 | -41% | +0.09 | 136.8 | 1.3 | 460 | 0 | 0.65 |
| hint accuracy 0.95, W=120s | recompute | 1560 | — | — | -0.07 | 145.8 | 10.5 | 0 | 0 | 0.63 |
| hint accuracy 0.95, W=120s | evacuate | 1031 | -529 ± 228 | -34% | +0.11 | 127.0 | 1.3 | 454 | 0 | 0.65 |
| hint accuracy 1.00, W=120s | recompute | 1560 | — | — | -0.07 | 145.8 | 10.5 | 0 | 0 | 0.63 |
| hint accuracy 1.00, W=120s | evacuate | 977 | -583 ± 243 | -37% | +0.06 | 123.6 | 1.3 | 451 | 0 | 0.65 |
