# Phase 2: first calibration on a real L40S (7 October 2026)

One on-demand `g6e.xlarge` (1× NVIDIA L40S 46 GB) in us-east-2c, driver 595.91
(CUDA 13.2), vLLM 0.31.0, torch 2.13.0+cu130, `NousResearch/Meta-Llama-3.1-8B-Instruct`
with prefix caching off. 69 instance-minutes, about $2.13. Raw files are in
`results/phase2/l40s-us-east-2-20261007/`.

**How we got here.** Spot g6e.xlarge had no capacity in any us-east-1 zone, and
on-demand didn't either. Spot placement scores were 1/10 in us-east-1, us-east-2 and
us-west-2. The runner gained `RETRY_MIN` and `MARKET=on-demand`. The first us-east-2
attempt died in vLLM warm-up: FlashInfer's sampler JIT-compiles on first use and
`ninja` was missing. Fixed by `VLLM_USE_FLASHINFER_SAMPLER=0` plus installing ninja.
On-demand means **no FIS notice timing this run**, since FIS only interrupts spot.

## 1. Measured constants vs. the ones the simulator assumed

| L40S, Llama-3.1-8B, bf16 KV | assumed (`profiles.py`) | **measured** |
|---|---|---|
| prefill throughput (short context) | 10,000 tok/s | **16,011 tok/s** |
| attention knee (per-token cost doubles) | 32,000 tok | **20,506 tok** |
| decode, single request | 60 tok/s | **46.7 tok/s** |
| cold prefill, 32k / 64k / 120k tokens | 4.8 / 12.8 / 34.5 s | **3.6 / 10.3 / 29.4 s** |
| KV bytes per token | 131,072 | 131,072 (from the model config) |

Fit (`kvevac.calibration`): time = setup + c/p · (1 + c/2k), with setup 0.046 s. It is
within 1% from 32k to 120k tokens, −2% at 16k and +6% at 4k. The 40% max relative error
is at 1k tokens (0.11 s predicted vs. 0.08 s measured), which is negligible in absolute
terms, since agent contexts are mostly above 30k. Each context
was measured 3 times, and repeats agree within 2%.

## 2. Receiver-side interference is negligible

A 32k-token prefill timed while the same node ingests synthetic "evacuated KV"
traffic (5 repeats each; every load generator hit its target rate):

| ingest load | host memory (pinned copies) | host→GPU (h2d) |
|---|---|---|
| 1 GB/s | −0.8% | −1.9% |
| 2.5 GB/s | −1.6% | −1.5% |
| 10 GB/s | −0.2% | +0.2% |
| max achievable (16.4 / 13.4 GB/s) | +2.1% | +2.9% |

Phase 1b had flagged receiver slowdown as the assumption that most threatened
evacuation (`ingress_slowdown` 0–100%). **On this hardware it is 0–3%, well inside the
range where Phase 1b found evacuation unaffected.** A NIC-driven load (real
cross-node traffic) is still unmeasured, but a 25GbE NIC moves at most about 3 GB/s,
far below the 13–16 GB/s tested here.

## 3. Simulator rerun with measured constants, on real sessions

`python -m kvevac.experiments baselines --seeds 6 --sessions 250 --trace
data/raw/agentx.jsonl --calibration results/phase2/l40s-us-east-2-20261007/prefill.json`
(`results/phase2/calibrated-trace/`). Δ% vs. recompute, assumed → **calibrated**:

| policy | indep. W=30s | indep. W=120s | corr. W=30s | corr. W=120s |
|---|---|---|---|---|
| evacuate | −15 → **−14%** | −49 → **−52%** | −8 → **−10%** | −46 → **−47%** |
| replicate | −63 → **−63%** | −64 → **−59%** | −53 → **−55%** | −52 → **−50%** |
| hybrid | −66 → **−71%** | −70 → **−66%** | −54 → **−51%** | −60 → **−56%** |
| inflight_replicate | −33 → **−31%** | −36 → **−29%** | −22 → **−27%** | −24 → **−30%** |
| pool, 1 copy | −68 → **−64%** | −73 → **−56%** | −54 → **−44%** | −54 → **−37%** |

- **The ranking survives calibration.** At a 2-minute notice, evacuation recovers about
  half of reclaim-induced recompute at zero steady-state cost, within about 5–10
  points of continuous replication. Hybrid is the best or tied. In-flight replication
  stays around −30%.
- The absolute cost of a reclaim is 25–30% lower than assumed, because measured
  prefill is faster (e.g. 1,189 vs. 1,560 excess GPU-s, independent, W=120 s).
- The 95% intervals are wide (±5–42 points at 6 seeds). Treat differences under about
  20 points as ties.

## 4. Still unmeasured
- **FIS notice timing** (how much of the 120 s is usable). Needs a spot run:
  `RETRY_MIN=120 AWS_REGION=us-east-2 bash jobs/aws/kvevac-aws.sh` when capacity returns.
- **Sustained NIC and object-store bandwidth** (sets ρ). The links in `profiles.py`
  remain assumed.
- The vLLM plugin (Phase 3) on a GPU.
