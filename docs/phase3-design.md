# Phase 3 design: deadline-triggered write-back in vLLM's KV tiering

Code pointers refer to vLLM `main` at `34051ad` (2026-10-05). Re-pin before
implementing.

## The framing upstream already gives us

vLLM's offloading stack is now **tiered**: GPU → CPU primary tier → zero or more
secondary tiers (filesystem `tiering/fs`, object store `tiering/obj`, peer-to-peer
`tiering/p2p` over NIXL). The orchestrator is
`vllm/v1/kv_offload/tiering/manager.py`, whose first design principle is:

> *Always offload to all tiers — when a chunk is stored to the primary tier, it is
> cascaded to ALL secondary tiers.*

That is **write-through**, and it is exactly the `replicate` baseline in our
simulator. It pays egress and storage bandwidth continuously. Under load, the
`BackpressureDetector` with its default `ThrottledDropPolicy`
(`tiering/backpressure.py`) **drops** secondary-tier stores, so write-through
coverage is silently incomplete exactly when the fleet is busiest.

The project's question, restated in vLLM's own terms:

> **On spot capacity, when does deadline-triggered write-back (cascade only on a
> termination notice, in planner order) match write-through, and at what saving in
> steady-state egress?** A hybrid uses write-through for whatever fits under
> backpressure and write-back at notice for whatever was dropped or is still in
> flight.

## Components

1. **Notice source.** `kvevac.notice.imds.NoticeWatcher` (done). It reads the real
   IMDSv2 paths, so the same code runs against `MockIMDS` locally and against AWS
   FIS-triggered reclaims.
2. **Stop admitting.** Implemented in `kvevac/notice/handler.py`, tested against a
   fake server. It calls `POST /pause?mode=wait&clear_cache=false`; the endpoint's
   default `clear_cache=true` would wipe the KV we are about to evacuate, and the
   route is only registered with vLLM's development endpoints enabled. Background:
   on notice, call the engine's
   `pause_scheduler(mode="wait")` (`vllm/v1/engine/core.py`). New requests queue and
   in-flight requests keep decoding. The router must also stop sending to this
   instance (`vllm-project/router` issue #252 covers the drain/readiness gate).
3. **Write-back policy.** Add a cascade mode to `TieringOffloadingManager`:
   `write_through` (today's behaviour) or `deferred`. In `deferred` mode,
   `complete_store()` keeps chunks in the primary tier and does not submit
   cascades.
4. **Evacuation flush.** New manager entry point
   `flush_for_deadline(order: list[OffloadKey-chain], deadline)`. It submits
   cascades through the existing `submit_store` / `create_store_job` paths, in the
   order `kvevac.planner.plan_evacuation` produces. It stops submitting when the
   projected finish passes the deadline, and lets in-flight jobs complete. GPU-only
   chunks of sessions chosen for evacuation are first stored GPU→CPU through the
   normal connector path; `handle_preemptions` already shows how to force pending
   stores to flush.
5. **Restore.** Nothing new. Once the session's next request lands on a surviving
   node attached to the same secondary tier (object store or P2P peer), the existing
   `lookup → promotion` path finds the chunks by block hash and loads them instead of
   recomputing.
6. **Router.** Session-sticky routing with a hint: after evacuation, route a
   session to a node that shares the tier its chunks went to. llm-d's
   inference-scheduler scorer plugins are the natural home for this.

## Session-level value, block-level mechanism

Implemented and tested in `kvevac/flush.py`. It expands the planner's session order
into a prefix-ordered, deduplicated, budget-truncated list of block keys, and reports
which sessions arrive complete, which arrive partial, and which are skipped.

The planner reasons about *sessions*: size, recompute cost, P(reuse). vLLM stores
*blocks* keyed by chained hashes. The bridge is the block-hash chain of a session's
latest request, which the scheduler already has per request. To evacuate a session
is to cascade the chain's keys from the front. Prefix order matters, because a hit
is only usable up to the first missing block: shipping the tail of a chain is
worthless if the head is lost.

## Experiments this enables (Phase 4)
- Write-through vs deferred vs hybrid on 2–4 single-GPU nodes (g6e.xlarge), with
  object-store or P2P tiers, under FIS-triggered reclaims and a replayed agent trace.
- Headline metrics: excess prefill GPU-seconds and TTFT after reclaim; steady-state
  secondary-tier egress; stores dropped under backpressure.
- Correctness: output parity (greedy decoding) between a session served
  continuously and one evacuated and restored mid-session.

## Risks
- `tiering/` is new and moving fast. Pin a commit, and expect the API to change by
  Phase 4.
- An object-store tier's write bandwidth may be well below the 25GbE assumed in the
  simulator. That lowers W·B, which the budget experiment shows matters most.
- P2P peers in the same reclaim wave are unsafe destinations. The router and planner
  must know each peer's failure domain.

## Prototype status (October 2026)

Written against vLLM `34051ad`. **Ran on a real L40S under vLLM 0.31.0** (same tiering
code) on 7 Oct 2026: deferred cascade, deadline flush and restore in a fresh process all
work, and greedy outputs match a cold recompute. See
[phase3-results.md](phase3-results.md).

| Piece | Where | State |
|---|---|---|
| Deferred / hybrid cascade | `kvevac/vllm_plugin/manager.py`, `DeadlineTieringOffloadingManager.complete_store` | written |
| Session index (keys per session, prefix positions, dirty/cascaded, evictions) | `kvevac/vllm_plugin/core.py`, `SessionIndex` | written, unit-tested |
| `flush_for_deadline` | manager; planning in `core.plan_flush` (planner order, then `kvevac.flush` block order, cut at `tier_bytes_per_s × (deadline − now − 2 s)`) | planning unit-tested; submission path written |
| Out-of-tree loading | `DeadlineTieringOffloadingSpec` via `spec_name` + `spec_module_path` (no vLLM fork) | written |
| Notice → flush | `SpotNoticeHandler(flush_control=...)` writes the request atomically **before** pausing admission; the manager polls it in `on_schedule_end` and writes `<control>.status` | handler side tested against MockIMDS |

Design decisions worth knowing:
- **Agent sessions come from the request.** Clients pass
  `kv_transfer_params={"kvevac_session_id": ...}`; vLLM carries it into `ReqContext`.
  Without it, every request is its own session.
- **The manager is adopted, not rebuilt.** `adopt()` swaps the class of the
  `TieringOffloadingManager` that upstream's spec constructs, so the plugin doesn't copy
  upstream's ~90 lines of tier construction, which change often.
- **Flush completions piggyback on `_update_backpressure`**, which upstream calls for
  every successful primary→secondary job. That is a private hook. If it moves, mark
  cascaded keys from `_process_finished_jobs` instead.
- **Upstream defaults to `offload_prompt_only=True`.** Decode-phase blocks are not
  offloaded. For agent sessions this is fine, because each turn's output is part of the
  next turn's prompt and is offloaded then.

Open risks, to settle on the first GPU run:
1. Does `on_schedule_end` run while the engine is paused with nothing in flight? If it
   doesn't, the handler's `--wake-model` one-token request is the workaround. Measure the
   delay between `flush_requested` and the plugin's `started_unix`.
2. Do the obj/p2p tiers accept store jobs under a synthetic `ReqContext` that never
   went through the scheduler? The manager calls `tier.on_new_request` and
   `on_request_finished` around the flush for this reason.
3. GPU-only blocks of running requests are not flushed (see the manager's docstring).

First GPU test (two g6e.xlarge, on-demand quota allows it): node A runs `deferred` with
an obj tier and `--flush-control`; a session builds an 80k-token context; trigger
`MockIMDS` (or FIS) on A; send the session's next turn to node B with the same tier and
check (1) TTFT vs. a cold prefill, (2) greedy-decoding output parity with an
uninterrupted run, (3) the `.status` report against `tier_bytes_per_s`.
