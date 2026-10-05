# Step 0 — Upstream reconnaissance

Pinned vLLM commit: `34051ad7145104e73ba3a7f5b39506ad0949bb8d` (main, 2026-10-05).
Everything below was read from the source at this pin. Re-check it at week 4.

## (a) What V1 does on preemption today

`Scheduler._preempt_request` (`vllm/v1/core/sched/scheduler.py:1542`):
- frees the request's KV blocks (`_free_request_blocks`) and encoder cache;
- sets `status = PREEMPTED` and **`num_computed_tokens = 0`**;
- prepends the request to the waiting queue.

So, by default, a preempted request **recomputes its whole prefix** when it is
rescheduled. Prefix-cache hits can soften this if the blocks have not been evicted
yet. This is intra-instance preemption, caused by KV memory pressure. vLLM has
**no notion of instance loss**: `grep` finds no spot, IMDS, `instance-action` or
rebalance handling anywhere in `vllm/`.

## (b) The closest existing mechanisms

1. **Offload-on-preempt (single instance).** `KVConnectorBase_V1.handle_preemptions`
   (`kv_connector/v1/base.py:306`) runs before preempted blocks are overwritten. The
   `OffloadingConnector` worker (`offloading/worker.py:219`) uses it to flush
   pending GPU→CPU stores (`jobs_to_flush`), so the request can reload its KV
   instead of recomputing it. This is the behaviour PR #29870 described; it appears
   to be merged at this pin. The PR's merge state has not been checked against the
   GitHub API.
2. **Cross-instance KV sharing.** `vllm/v1/kv_offload/tiering/p2p/` adds a P2P
   secondary tier (ZMQ control and NIXL data transport, one session per peer).
   Peers can serve each other's KV blocks. **This narrows the gap:** the
   *mechanism* to move KV between instances now exists upstream.
3. **Pause / stop admitting.** `EngineCore.pause_scheduler(mode="wait")`
   (`vllm/v1/engine/core.py`) queues new requests and keeps stepping until the
   in-flight ones drain. It is exposed as a dev endpoint
   (`entrypoints/serve/dev/rlhf/api_router.py:31`, `POST /pause`). "Wait" means
   letting requests *finish locally*; it does not move them away.
4. **Elastic-EP drain** (`async_llm.py:1168`): waits up to a timeout for requests to
   finish before scaling. It also finishes locally.

## (c) What this project adds that none of these do

None of these mechanisms reacts to an **external termination deadline**, and none
**moves in-flight requests off an instance that is about to die**. Offload-on-preempt
keeps KV on the same node, which is useless when that node disappears. P2P tiering
shares blocks on demand but has no deadline or eviction trigger. Pause/drain waits
for local completion, which fails when generation would outlast the 2-minute notice
or the notice is shorter.

**Contribution, in one sentence:** on a spot rebalance or interruption signal, stop
admitting new work and migrate in-flight requests' committed KV to a healthy peer
before the deadline, so decoding resumes instead of restarting. The design must be
correlation-aware, so a request is not drained to a peer in the same reclaim wave.

## Implications for the plan

- **Reuse the P2P/NIXL tier, or `OffloadingConnector` plus a CPU→peer hop, as the
  transport.** Do not build a new one. That makes the fix smaller and squarely about
  *policy and triggering*, which is the defensible part.
- **The baseline is still "recompute on the surviving instance".** The router
  resubmits the request and its prefix is lost with the dead node. P2P tiering
  doesn't help here, because the blocks lived on the node that died.
- **Second baseline:** "pause and drain locally" (`pause_scheduler(mode="wait")`).
  This is the fair reactive baseline. It wins when the remaining decode time is
  short enough to fit the notice.
- **Still to verify:** PR #29870's exact merged scope; the Core SIG roadmap item
  "avoid excessive preemption"; and whether anyone is working on spot or
  termination handling in vLLM or the production stack. Search issues and PRs for
  "spot", "graceful shutdown" and "drain".
