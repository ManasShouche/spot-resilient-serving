## Value at risk per spot node (real AgentX sessions from agentx.jsonl, resampled with replacement; simulated, assumed constants)

| scenario | resident GB p50 / p90 | not running, p50 / p10 | idle >60 s, p50 | rebuild GPU-s p50 / p90 | returning share p50 | sessions p50 | ρ<1 share, 25GbE W=30s / 120s |
|---|---|---|---|---|---|---|---|
| 8B on L40S, 4M-token cache | 440.6 / 512.65 | 78% / 66% | 74% | 1213.03 / 1486.95 | 66% | 24 | 100% / 73% |
| 8B on g6e.xlarge, 400k-token cache | 32.73 / 47.91 | 100% / 0% | 97% | 86.27 / 138.12 | 100% | 2 | 0% / 0% |
| 70B on 4xH100, 4M-token cache | 1094.95 / 1282.25 | 75% / 61% | 72% | 1020.71 / 1245.58 | 68% | 24 | 100% / 100% |

Not running: KV of sessions with no turn in flight (between turns or idle); this is what in-flight fault tolerance leaves unprotected. Idle >60 s: no activity for a minute. Returning share: the part of the rebuild cost that belongs to sessions with another turn (what an oracle would protect). ρ = W × B / resident KV; below 1, not everything fits in the notice and the planner's choices matter.
