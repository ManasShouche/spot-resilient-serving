# Research narrative for a master's SOP

Material to adapt, not to paste. Every claim below is backed by a file in this repo.
Keep the words "simulated" and "prototype" wherever they apply; admissions readers
in systems check.

## The one-paragraph version

> Agentic LLM workloads keep tens of thousands of tokens of KV cache per session
> alive between turns, and most providers now serve them partly on spot GPUs, which
> the cloud can reclaim with a short notice. I asked what happens to that idle session
> state when a node is reclaimed. Existing fault-tolerance systems (KevlarFlow, LUMEN,
> GhostServe, ShuntServe) protect only in-flight requests, and agent-KV systems
> (CacheScout, Continuum) protect idle sessions only against eviction. I built a
> discrete-event simulator and replayed 393 real Claude Code sessions. 75–78% of a
> large node's resident KV belonged to sessions between turns, which none of these
> protect. I then framed the termination notice as a
> budget: a deadline-bounded knapsack that decides which sessions to evacuate, to
> where, outside the reclaim's failure domain. In simulation, evacuation recovers
> 44–52% of reclaim-induced recompute at a 2-minute notice, with zero steady-state
> cost. At equal memory it beats continuous replication, which ends up worse than
> doing nothing. I calibrated the cost model on a real L40S, where the ranking held and receiver-side
> interference measured 0–3%. I built the policy as an out-of-tree plugin for vLLM's tiered
> KV offloading. On two AWS nodes it evacuated 10 GB of session KV to a peer's DRAM in
> under 7 s of a 120 s notice, and restored it with output identical to recompute.

## The story, in the order an SOP should tell it

1. **Problem I noticed.** Spot reclaims silently turn every later turn of an agent
   session into a full re-prefill. Nothing fails, so nobody measures it.
2. **Two honest reframings** (strengths, if you explain why they happened):
   - The first plan was *predictive, correlation-aware migration*. A literature
     check showed hazardserve had already found that pre-emptive migration "barely
     fires", and that SkyServe and Parcae own "correlation" and "prediction".
     ([docs/sota-2026.md](sota-2026.md)) I moved to *notice-bounded evacuation*.
   - The first simulator result (hybrid beats replication) came from a routing bug. I
     found it, reran at 12 and then 20 seeds, and published the correction
     ([phase1b-results.md §7](phase1b-results.md)).
3. **Findings that are not obvious:**
   - At equal memory, write-through replication makes things worse (+90%), while
     evacuation gives −50%. Spending DRAM on replicas causes more misses than the
     replicas save.
   - Under a shared-store bandwidth budget, write-through degrades silently (drops
     under backpressure lose exactly the bursts), while the hybrid holds.
   - KevlarFlow-style in-flight replication is the wrong unit for agents: −13% to
     −36% at 12–14× the egress ([phase1c-results.md](phase1c-results.md)).
   - Reuse prediction is second-order: on real sessions an oracle is no better
     than recency.
   - Checking against the real trace overturned one synthetic finding (pool fragility)
     and showed that equal session counts are not equal load. Both corrections are
     published. That habit is worth a sentence in the SOP.
4. **Engineering depth:** an AWS spot harness that injects real FIS interruptions, a
   one-command calibration runner that returns results over the serial console with
   checksums, and an out-of-tree vLLM plugin that adds deferred cascades and a
   deadline flush to vLLM's tiered offloading
   ([phase3-design.md](phase3-design.md)).
5. **What I would do in a master's:** close the loop on real hardware (calibrated
   regime map, two-node prototype with output parity), then the open question this
   raises: placement and evacuation that are aware of failure domains for distributed
   KV pools sharded across preemptible nodes.

## Claims to avoid (see positioning.md §6)
- "First to predict" or "first to use correlated preemption".
- "KV transfer beats recompute" in general.
- Any percentage without "in simulation".
- "Deployed" or "production" for the vLLM plugin. It is a prototype tested on one GPU.
- "Restore is faster than recompute" in general. It was slower on local NVMe; that
  depends on tier bandwidth.

## What would most strengthen the application, cheapest first
1. Done: the cost model is calibrated on a real L40S
   ([phase2-results.md](phase2-results.md)), and receiver interference is measured
   at 0–3%. Next: a spot run for FIS notice timing.
2. Done: the Phase 1c experiments now also run on the real AgentX trace.
3. Done (single node): the plugin ran on a real L40S under vLLM 0.31.0. The deadline
   flush matched its projection within 6%, and restore achieved output parity
   ([phase3-results.md](phase3-results.md)). Two nodes done too: the KV was evacuated to a
   peer's DRAM over the network in 6.6 s, and restore beat recompute on a 59k-token
   turn (8.3 s vs 9.1 s) with output parity.
4. A 4-page workshop submission (EuroMLSys / MLSys or NeurIPS systems workshops);
   positioning.md §5 lists the experiments.
