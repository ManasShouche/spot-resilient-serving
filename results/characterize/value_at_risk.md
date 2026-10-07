## Value at risk per spot node (synthetic AgentX-calibrated workload; simulated, assumed constants)

| scenario | resident GB p50 / p90 | not running, p50 / p10 | idle >60 s, p50 | rebuild GPU-s p50 / p90 | returning share p50 | sessions p50 | ρ<1 share, 25GbE W=30s / 120s |
|---|---|---|---|---|---|---|---|
| 8B on L40S, 4M-token cache | 511.99 / 523.52 | 69% / 53% | 62% | 1269.78 / 1393.26 | 64% | 38 | 100% / 100% |
| 8B on g6e.xlarge, 400k-token cache | 43.16 / 51.46 | 75% / 0% | 63% | 99.53 / 141.36 | 73% | 3 | 0% / 0% |
| 70B on 4xH100, 4M-token cache | 1279.27 / 1308.84 | 61% / 46% | 55% | 1082.02 / 1174.36 | 66% | 38 | 100% / 100% |

Not running: KV of sessions with no turn in flight (between turns or idle); this is what in-flight fault tolerance leaves unprotected. Idle >60 s: no activity for a minute. Returning share: the part of the rebuild cost that belongs to sessions with another turn (what an oracle would protect). ρ = W × B / resident KV; below 1, not everything fits in the notice and the planner's choices matter.
