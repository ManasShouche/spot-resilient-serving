"""Deadline write-back for vLLM's tiered KV offloading (Phase 3 prototype).

Targets vLLM `main` at 34051ad (2026-10-05); the tiering API is new and moving, so
re-pin before running. Load it out of tree, with no vLLM fork:

    vllm serve NousResearch/Meta-Llama-3.1-8B-Instruct \\
      --kv-transfer-config '{"kv_connector": "OffloadingConnector",
        "kv_role": "kv_both",
        "kv_connector_extra_config": {
          "spec_name": "DeadlineTieringOffloadingSpec",
          "spec_module_path": "kvevac.vllm_plugin.manager",
          "cpu_bytes_to_use": 21474836480,
          "secondary_tiers": [{"type": "obj", ...}],
          "kvevac": {"cascade_mode": "deferred",
                     "control_path": "/run/kvevac/flush.json",
                     "tier_bytes_per_s": 8e8}}}'

What changes relative to upstream `TieringOffloadingManager`:

- complete_store(): in `deferred` mode nothing is cascaded; the keys are recorded as
  dirty under their agent session. In `hybrid` mode a cascade is submitted only when
  the tier's backpressure detector admits it; whatever it refuses stays dirty
  (upstream silently drops it). `write_through` is upstream behaviour.
- on_schedule_end(): polls the control file. When the notice handler
  (kvevac.notice.handler) writes a flush request, the manager plans which sessions
  to save (kvevac.vllm_plugin.core.plan_flush) and submits their dirty blocks, in
  prefix order, as store jobs through the normal create_store_job/submit_store path,
  stopping at what the tier can absorb before the deadline. A status file reports
  what was submitted and, once the jobs finish, what was confirmed.
- Restore needs nothing new: a session's next request on a surviving node that shares
  the tier finds the blocks by hash through lookup() -> promotion.

Known gaps (docs/phase3-design.md, "Prototype status"):
- Blocks that only exist in GPU memory (never stored to the CPU primary tier) are not
  flushed. With CHUNK_LEVEL offloading every computed chunk is stored to the primary
  tier, so this is the tail of running requests.
- The scheduler must keep stepping for on_schedule_end() to run. The handler writes
  the flush request *before* pausing admission, and in-flight decodes keep the loop
  alive; an idle engine needs a wake-up request (handler option `wake_request`).
"""

from __future__ import annotations

import time
from collections.abc import Collection
from pathlib import Path

from typing_extensions import override
from vllm.logger import init_logger
from vllm.v1.kv_offload.base import (
    LookupResult,
    OffloadingManager,
    OffloadKey,
    PrepareStoreOutput,
    ReqContext,
    RequestOffloadingContext,
    ScheduleEndContext,
)
from vllm.v1.kv_offload.tiering.base import JobResult, SecondaryTierManager
from vllm.v1.kv_offload.tiering.manager import JobMetadata, TieringOffloadingManager
from vllm.v1.kv_offload.tiering.spec import TieringOffloadingSpec

from kvevac.profiles import GPUS, GpuProfile
from kvevac.vllm_plugin.core import (
    SESSION_PARAM,
    CascadeMode,
    FlushParams,
    FlushReport,
    FlushRequest,
    SessionIndex,
    plan_flush,
    read_flush_request,
    write_report,
)

logger = init_logger(__name__)

FLUSH_REQ_ID = "kvevac-deadline-flush"
FLUSH_BATCH_KEYS = 256
"""Keys per store job: big enough to amortize per-job overhead, small enough that the
tier starts writing the highest-priority sessions first."""
CONTROL_POLL_S = 0.2


class DeadlineTieringOffloadingManager(TieringOffloadingManager):
    """TieringOffloadingManager with deferred/hybrid cascades and a deadline flush."""

    # Set by adopt(); declared for type checkers.
    _mode: CascadeMode
    _index: SessionIndex
    _control_path: Path | None
    _params: FlushParams
    _last_seq: int
    _next_poll: float
    _flush_jobs: set[int]
    _report: FlushReport | None
    _flush_ctx: ReqContext | None
    _flush_tier: int
    _batch_keys: int

    @classmethod
    def adopt(cls, manager: TieringOffloadingManager, *, mode: CascadeMode,
              control_path: Path | None, params: FlushParams,
              batch_keys: int = FLUSH_BATCH_KEYS) -> DeadlineTieringOffloadingManager:
        """Upgrade the manager upstream's spec just built, instead of copying its
        construction code (which changes often)."""
        manager.__class__ = cls
        assert isinstance(manager, cls)
        manager._mode = mode
        manager._index = SessionIndex()
        manager._control_path = control_path
        manager._params = params
        manager._last_seq = 0
        manager._next_poll = 0.0
        manager._flush_jobs = set()
        manager._report = None
        manager._flush_ctx = None
        manager._flush_tier = 0
        manager._batch_keys = batch_keys
        logger.info("kvevac: cascade mode %s, control file %s", mode, control_path)
        return manager

    # ------------------------------------------------------------- session tracking
    @staticmethod
    def _session_of(req_context: ReqContext) -> str:
        params = req_context.kv_transfer_params or {}
        return str(params.get(SESSION_PARAM) or req_context.req_id)

    @override
    def on_new_request(self, req_context: ReqContext, *,
                       exclude_tier_idx: int | None = None) -> RequestOffloadingContext:
        self._index.touch(self._session_of(req_context), time.time())
        return super().on_new_request(req_context, exclude_tier_idx=exclude_tier_idx)

    @override
    def prepare_store(self, keys: Collection[OffloadKey],
                      req_context: ReqContext) -> PrepareStoreOutput | None:
        result = super().prepare_store(keys, req_context)
        if result is not None and result.evicted_keys:
            self._index.forget(result.evicted_keys)
        return result

    # ----------------------------------------------------------------- cascades
    @override
    def complete_store(self, keys: Collection[OffloadKey], req_context: ReqContext,
                       success: bool = True) -> None:
        if success:
            session, now = self._session_of(req_context), time.time()
            for key in keys:
                self._index.record(session, key,
                                   req_context.get_offload_key_position(key), now)
        if self._mode is CascadeMode.WRITE_THROUGH or not success:
            super().complete_store(keys, req_context, success)
            return
        # Mirrors upstream complete_store, minus the unconditional cascade.
        self.primary_tier.complete_store(keys, req_context, success)
        for tier_idx, tier in enumerate(self.secondary_tiers):
            if self._mode is CascadeMode.HYBRID and \
                    self._should_store_to_tier(tier, len(keys)):
                tier.submit_store(self.create_store_job(keys, req_context, tier_idx))
            else:
                self._index.mark_dirty(keys)
        state = self._req_state[req_context.req_id]
        assert state.pending_primary_stores > 0
        state.pending_primary_stores -= 1
        self._maybe_finalize_request(req_context.req_id)

    @override
    def _update_backpressure(self, tier: SecondaryTierManager, job_metadata: JobMetadata,
                             completed_job: JobResult) -> None:
        # Upstream calls this for every successful primary->secondary job.
        super()._update_backpressure(tier, job_metadata, completed_job)
        keys = job_metadata.transfer_job.keys
        self._index.mark_cascaded(keys)
        if job_metadata.transfer_job.job_id in self._flush_jobs and self._report:
            self._report.keys_confirmed += len(keys)
            self._report.jobs_done.append([round(time.time(), 3), len(keys)])

    @override
    def _process_finished_jobs(self) -> None:
        super()._process_finished_jobs()
        if self._flush_jobs:
            self._flush_jobs.intersection_update(self._jobs)
            if not self._flush_jobs:
                self._finish_flush()

    # -------------------------------------------------------------------- flush
    @override
    def on_schedule_end(self, context: ScheduleEndContext) -> None:
        super().on_schedule_end(context)
        now = time.monotonic()
        if self._control_path is None or now < self._next_poll:
            return
        self._next_poll = now + CONTROL_POLL_S
        request = read_flush_request(self._control_path, self._last_seq)
        if request is not None:
            self._last_seq = request.seq
            self.flush_for_deadline(request)

    def flush_for_deadline(self, request: FlushRequest) -> FlushReport:
        """Submit dirty blocks of the most valuable sessions before the deadline."""
        started = time.time()
        if request.reset and request.only:
            self._index.uncascade(request.only)
        tier = self.secondary_tiers[request.tier]
        flush, order = plan_flush(self._index, request, self._params, now_unix=started)
        ctx = self._flush_ctx = ReqContext(req_id=f"{FLUSH_REQ_ID}-{request.seq}")
        self._flush_tier = request.tier
        tier.on_new_request(ctx)
        # Only blocks still resident in the primary tier can be read from it.
        resident = [(k, sid) for k, sid in zip(flush.keys, flush.key_sessions, strict=True)
                    if self.primary_tier.lookup(k, ctx) is LookupResult.HIT]
        ready = [k for k, _ in resident]
        segments: list[list] = []
        for _, sid in resident:
            if segments and segments[-1][0] == sid:
                segments[-1][1] += 1
            else:
                segments.append([sid, 1])
        for start in range(0, len(ready), self._batch_keys):
            job = self.create_store_job(ready[start:start + self._batch_keys], ctx,
                                        request.tier)
            self._flush_jobs.add(job.job_id)
            tier.submit_store(job)
        sent = len(ready) * self._params.block_bytes
        self._report = FlushReport(
            seq=request.seq, started_unix=started, sessions_planned=order,
            complete_sessions=flush.complete_sessions,
            partial_sessions=flush.partial_sessions,
            skipped_sessions=flush.skipped_sessions, keys_submitted=len(ready),
            bytes_submitted=sent,
            projected_finish_unix=started + sent / (request.tier_bytes_per_s
                                                    or self._params.tier_bytes_per_s),
            already_in_tier=len(self._index.cascaded), segments=segments)
        logger.info("kvevac: flush %d submitted %d blocks (%.2f GB) for %d sessions; "
                    "%.1f s to deadline", request.seq, len(ready), sent / 1e9,
                    len(flush.complete_sessions) + len(flush.partial_sessions),
                    request.deadline_unix - started)
        if self._control_path:
            write_report(self._control_path, self._report)
        if not self._flush_jobs:
            self._finish_flush()
        return self._report

    def _finish_flush(self) -> None:
        if self._report is None:
            return
        self._report.finished_unix = time.time()
        if self._flush_ctx is not None:
            self.secondary_tiers[self._flush_tier].on_request_finished(self._flush_ctx)
            self._flush_ctx = None
        if self._control_path:
            write_report(self._control_path, self._report)
        logger.info("kvevac: flush %d confirmed %d blocks", self._report.seq,
                    self._report.keys_confirmed)


class DeadlineTieringOffloadingSpec(TieringOffloadingSpec):
    """TieringOffloadingSpec whose manager is a DeadlineTieringOffloadingManager.

    Reads a `kvevac` dict from kv_connector_extra_config: cascade_mode, control_path,
    tier_bytes_per_s (measured; required for deferred/hybrid), tier_setup_s.
    """

    @override
    def get_manager(self) -> OffloadingManager:
        manager = super().get_manager()
        if isinstance(manager, DeadlineTieringOffloadingManager):
            return manager
        assert isinstance(manager, TieringOffloadingManager)
        cfg = dict(self.extra_config.get("kvevac", {}))
        mode = CascadeMode(cfg.get("cascade_mode", CascadeMode.DEFERRED))
        if mode is not CascadeMode.WRITE_THROUGH and "tier_bytes_per_s" not in cfg:
            raise ValueError("kvevac.tier_bytes_per_s is required (measure it in Phase 2)")
        control = cfg.get("control_path")
        # One offload key covers one chunk of blocks_per_chunk GPU blocks.
        tokens = int(self.tokens_per_block[0]) * int(self.blocks_per_chunk)
        gpu = GPUS["l40s"]
        if "prefill_tokens_per_s" in cfg:  # measured constants (results/phase2/)
            gpu = GpuProfile("measured", float(cfg["prefill_tokens_per_s"]),
                             float(cfg.get("attention_knee_tokens",
                                           gpu.attention_knee_tokens)),
                             gpu.decode_tokens_per_s)
        restore = cfg.get("restore_bytes_per_s")
        params = FlushParams(block_bytes=int(self.kv_bytes_per_chunk),
                             block_tokens=tokens,
                             tier_bytes_per_s=float(cfg.get("tier_bytes_per_s", 1e9)),
                             tier_setup_s=float(cfg.get("tier_setup_s", 0.3)), gpu=gpu,
                             restore_bytes_per_s=float(restore) if restore else None)
        self._manager = DeadlineTieringOffloadingManager.adopt(
            manager, mode=mode, control_path=Path(control) if control else None,
            params=params, batch_keys=int(cfg.get("flush_batch_keys", FLUSH_BATCH_KEYS)))
        return self._manager
