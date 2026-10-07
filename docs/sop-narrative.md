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
> discrete-event simulator and found that 55–63% of a node's resident KV is idle
> session state that none of these protect. I then framed the termination notice as a
> budget: a deadline-bounded knapsack that decides which sessions to evacuate, to
> where, outside the reclaim's failure domain. In simulation, evacuation recovers
> 44–52% of reclaim-induced recompute at a 2-minute notice, with zero steady-state
> cost. At equal memory it beats continuous replication, which ends up worse than
> doing nothing. I am now validating the cost model on AWS spot GPUs and prototyping
> the policy inside vLLM's tiered KV offloading.

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
     −30% at about 14× the egress ([phase1c-results.md](phase1c-results.md)).
   - Reuse prediction is second-order: a perfect oracle adds 6–8 points.
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
- "Deployed" or "production" for the vLLM plugin until it has run on a GPU.

## What would most strengthen the application, cheapest first
1. One real calibration run (Phase 2, about $2–3). It turns "assumed constants" into
   "measured on L40S".
2. The real AgentX trace replay (`--trace`). It removes "synthetic workload".
3. A two-node GPU demo of the plugin with output parity. Even one plot of returning
   session TTFT, evacuated vs. cold, is strong evidence.
4. A 4-page workshop submission (EuroMLSys / MLSys or NeurIPS systems workshops);
   positioning.md §5 lists the experiments.
