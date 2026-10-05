# Calibration: replacing assumptions with measurements (Phase 2)

Each constant in `kvevac/profiles.py` and `kvevac/costmodel.py` gets replaced by a
measurement on rented hardware. Each measurement is cheap, needs only one or two
GPUs, and can run on on-demand instances.

| Constant | Measure how | Instance |
|---|---|---|
| `prefill_tokens_per_s`, `attention_knee_tokens` | vLLM prefill latency at 1k–200k context (`benchmark_serving` with fixed prompts, prefix cache off) | g6e.xlarge (L40S), g6.xlarge (L4) |
| `decode_tokens_per_s` | ITL at batch sizes 1–32 | same |
| `LinkProfile.bytes_per_s`, `setup_s` | Time to move N GB of KV between two instances via LMCache (TCP) and via the NIXL P2P tier, idle and under serving load | 2 × g6e in one AZ; repeat across AZs |
| Object-store link | LMCache remote backend to S3 (or a store in another AZ): write and read throughput | same |
| `FleetConfig.ingress_slowdown` | Prefill TTFT on node B with and without a concurrent multi-GB KV ingest into B's CPU tier (LMCache / NIXL) | 2 × g6e |
| `RECOMPUTE_SETUP_S` | Time to first scheduled token for a cold request at low load | same |
| Notice timing | Real FIS `send-spot-instance-interruptions`: rebalance-recommendation lead time and gap from 2-minute notice to termination, measured via IMDS polling | any spot instance |

## Tooling (ready)
- `python -m kvevac.measure.prefill --base-url ... --model ... --gpu <name> --out f.json`
  measures cold-prefill TTFT (unique nonce per prompt; context length from the
  server's usage report) and decode rate. Tested against a fake streaming server,
  but **not yet run against real vLLM**.
- `kvevac.calibration` fits the cost-model constants from that JSON. Add measured
  link points under `"links"`.
- `python -m kvevac.experiments all --calibration f.json` reruns every experiment
  with the measured profile, and its output header records the calibration file.

Exit criterion: rerun `python -m kvevac.sweep` with the measured profile and check
that the ordering in `docs/simulator.md` survives. If it does not, that is the
finding.
