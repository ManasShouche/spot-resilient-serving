# Positioning against the state of the art (October 2026)

This doc answers one question: **what can this project honestly claim, and what has
to change before the claim is strong enough for a master's SOP or a workshop
paper?** It builds on [sota-2026.md](sota-2026.md) and checks the external
gap-analysis doc (SpotServe / Llumnix / SkyServe / Parcae era) against primary
sources.

**How this was checked.** Full text read for ShuntServe (2606.18600), KevlarFlow
(2601.22438), LUMEN (2606.17787), GhostServe (2605.00831), SkyServe (2411.01438),
CacheWise (2606.16824), the hazardserve README, vLLM RFC #24256, and the vLLM
Mooncake-store (May 2026) and AgentX (Sep 2026) blog posts. Everything else below
comes from abstracts and search excerpts and is marked *(abstract only)*.

## 1. Verdict in five lines

1. The gap analysis's proposed delta, *"request/KV-level serving migration driven by
   a correlation-aware predictor"*, is **no longer defensible**. Predictive
   pre-emptive migration has a published negative result (hazardserve), and
   in-flight request recovery is crowded (ShuntServe, KevlarFlow, LUMEN, GhostServe).
2. The project's current framing, **notice-bounded preservation of idle agent-session
   KV**, is still open. No paper found protects *idle session caches* against node
   loss, and none uses the termination notice as a budget. Section 3 has the evidence.
3. The most useful citation is **ShuntServe's own future work**: "a hybrid recovery
   scheme that tracks the progress of in-flight requests and the remaining grace
   period, and selects an appropriate request recovery mechanism for each request."
   The planner in `kvevac/planner.py` is that idea, generalised to idle sessions and
   failure domains.
4. The largest technical risk is not novelty but **regime**. On the planned testbed
   (g6e.xlarge, AWS's 120 s notice) ρ is well above 1, so everything fits in the
   notice and the planner has nothing to decide (section 4.1). The interesting
   regime has to be built deliberately.
5. Today this is a **simulator study with assumed constants and a synthetic
   workload**. It is SOP-worthy as research in progress. For a workshop paper it needs
   real traces, one real measurement campaign and a vLLM prototype (section 5).

## 2. Corrections to the gap-analysis doc

| Claim in the gap analysis | What the primary source says |
|---|---|
| vLLM RFC #24256 shows that request migration on failure is an open P0 item. | The RFC is **closed as not planned**. It is about *intra-instance* KV-pressure preemption on P/D decode nodes, not instance loss, so it doesn't support a spot-failure gap. |
| Deliverable A: KV-aware drain beats recompute, which makes a good "money chart". | ShuntServe measured both on g6/g6e, the instances this project uses. "Recomputation-based migration exhibits lower latency overhead in most cases." Transfer only wins for very large models, very long contexts, weak GPUs or fast networks; 70B on L40S crosses over at 64K. For 8B on L40S, a drain-vs-recompute chart on in-flight requests would likely show **no win**. |
| Claimable delta: a correlation-aware predictor drives migration. | hazardserve (v0.1, synthetic traces) found that its pre-emptive trigger "barely fires" and that the reason "is structural": a planned move costs about one re-prefill, which exceeds the risk it removes. Parcae and SkyNomad already hold "predicts spot", and SkyServe holds "exploits correlation". |
| Scale: 2–4 × g5.12xlarge, plus a 30B model on 4-GPU TP. | It doesn't fit the account's 5-vCPU spot G quota (one g6e.xlarge). Multi-GPU spot is also the capacity Parcae couldn't obtain. |
| SkyServe: in a GCP trace, 34–95% of the time other spot instances in the zone are preempted within 150 s; Pearson ≥ 0.3 within a region; 43% cost saving. | **Confirmed** from the full text. |
| Spot-and-Scoot F1 = 0.85 at 60 min; CloudSim Plus finds 92% co-interruption within 3 min; SpotVista. | **Not verified** (the papers weren't reachable). Don't cite these numbers until the papers have been read. |

## 3. Where the closest work stops

What each system protects, and when:

| System | Asset protected | When it pays | Uses the notice? | Idle session KV? |
|---|---|---|---|---|
| SpotServe (ASPLOS'24) | in-flight requests and parallel config | at notice (about 30 s) | yes, reactive | no |
| ShuntServe (2606.18600) | in-flight requests, by **recompute** | after loss; replacement init overlaps the 120 s notice | for init only. KV transfer was rejected because it needs a *new instance* ready within the grace period | no ("prefix" never appears in the paper) |
| KevlarFlow (2601.22438) | in-flight request KV, replicated to a peer's GPU | continuously; 2.3–4.0% latency overhead | no (sudden failure) | no. ShareGPT single-turn workload; replicas are **dropped under memory pressure** |
| LUMEN (2606.17787) | in-flight KV checkpoints on a load-aware holder | continuously | no | no. The holder is kept "until the request terminates" |
| GhostServe (MLSys'26) | streaming KV, as erasure-coded parity in host DRAM | continuously | no | no (in-flight long-context requests) |
| hazardserve (GitHub v0.1) | in-flight requests, via hazard-aware placement and migration | speculatively | no | no |
| Mooncake store in vLLM (May 2026) | session prefixes in a **distributed DRAM/SSD pool** | continuously (write on store) | no | yes, but the pool lives on the GPU nodes' DRAM. On spot, a reclaim deletes that node's shard. |
| Continuum / CacheWise / KVFlow / TokenCake | idle session KV against **eviction** (TTL, tool-duration prediction, step graph) | steady state | n/a | yes, but against capacity pressure, not node loss |

Two things follow.

- **The asset gap is real.** Every fault-tolerance system protects in-flight requests.
  Every agent-KV system protects idle sessions against eviction, not node loss. The
  intersection, *idle session KV under node loss with a notice*, is empty in
  everything found. This needs one more targeted search (TraceLab 2606.30560,
  "Learning Agent Execution for KV-Cache Management" 2608.14624, llm-d's P2P KV
  sharing post) before the claim is frozen. *(abstract only)*
- **Production is moving toward the problem.** vLLM's AgentX post lists
  "session-based KV cache management" and a "programmable KV cache" with
  "placement, retention, replication, and eviction policies" as next steps. A
  distributed pool sharded across spot nodes is exactly where a notice-triggered,
  planned **shard evacuation** applies. This is both a scoop risk (upstream could ship
  a naive version) and the best motivation available: the planner becomes a policy
  for an interface vLLM is about to expose.

## 4. Critical review of our own findings

### 4.1 The planned testbed sits in the trivial regime

The simulator's default node holds 4M tokens of session KV. For Llama-3.1-8B
(128 KiB per token) that is **about 512 GB per node**, and at 25GbE and W = 120 s,
ρ ≈ 0.6. A g6e.xlarge has 48 GB of GPU memory (about 16 GB of it for weights) and
32 GiB of host RAM, so its resident KV is about 40 GB. Even at a sustained 1 GB/s,
120 s moves 120 GB, so **ρ ≈ 3: everything fits, and every evacuation policy looks
the same.**

The regime where the planner matters (ρ < 1) is:
- **short notice**: 30 s on GCP and Azure (ShuntServe cites Azure at 30 s, AWS at
  120 s, Alibaba at 300 s);
- **big nodes**: 8-GPU instances with hundreds of GB to TBs of CPU tier;
- **correlated waves**: many victims evacuating into a few survivors or one shared
  store. Phase 1b already shows that whole-group bursts are hard for every policy.

**Change:** run Phase 4 with an emulated short notice (W = 15–30 s) and NIC
throttling (`tc`) chosen to hit ρ ∈ {0.25, 0.5, 1, 2}, and justify each point by
arithmetic on real instance types and clouds. Report g6e.xlarge's *sustained*
bandwidth over 120 s, not the "up to 20 Gbps" burst figure.

### 4.2 ρ is a good operator rule but not a research result

"Benefit rises with notice × bandwidth / resident KV and saturates near 1" is what a
reviewer expects. The findings that are **non-obvious and worth leading with** are:
- **At equal memory, write-through loses badly** (−50% for evacuation vs +90% for
  write-through, §3 of the results). Spending scarce DRAM on replicas costs more
  misses than replication saves.
- **Under a shared-store bandwidth budget, write-through silently degrades**
  (−57% → −25% at 83 MB/s per node), because drop-on-backpressure loses exactly the
  bursts, while **hybrid holds** (−51%). This mirrors vLLM's own `ThrottledDropPolicy`
  and KevlarFlow's drop-under-pressure.
- Shipping partial prefixes and drain-only are both useless. That is a negative
  result worth one sentence.

### 4.3 Write-through's steady-state cost needs a number, not an assertion

KevlarFlow reports only 2.3–4.0% latency overhead for continuous replication. If
that holds, "zero steady-state cost" is a weak selling point. The counter-argument is
specific to agentic workloads: KevlarFlow replicates *in-flight* KV for ShareGPT-sized
requests. A Claude Code session's median working set is about 89K tokens
(agentic-kv-cache trace), which is about 11 GB per session for an 8B model, and much
more for a 70B model. **Measure replication egress per node on a real agentic trace.**
If it is below what a shared store can absorb, write-through is fine and the paper
says so.

### 4.4 Reuse prediction is weaker on real traces than the oracle suggests

Phase 1b reports an 18-point gap between recency and oracle at W = 120 s and calls
reuse prediction "the main lever left". Two cautions:
- **It is taken as a standalone contribution.** CacheWise predicts reuse from tool-call
  metadata, Continuum sets TTLs from tool durations, and KVFlow uses an agent step
  graph. Use one of them as the reuse estimator; don't claim it.
- **On real traces, liveness prediction barely beats LRU.** On 68k requests from 393
  Claude Code sessions, a hazard-based liveness policy did *worse* than LRU-leaf
  (84.9% vs 93.9% hit rate), and TTL-300 s was identical to LRU. Those are eviction
  results, not evacuation results, but they predict that most of the oracle gap won't
  be captured.

### 4.5 Real traces now exist. Use them.

The "real AgentX trace replay" item is blocked, but three alternatives are public:
the agentic-kv-cache traces (Claude Code, Apache-2.0, `make data`, about 1.1 GB),
the Codex / SWE-bench Pro traces released with the vLLM Mooncake post (610 traces,
median 33 turns, inter-turn delay 5.2 s median and 81.4 s P99), and the CacheWise
coding traces (GitHub). HuggingFace is blocked from cloud sessions; check GitHub
first.

Inter-turn gaps of a few seconds also change the model. Most sessions are *hot*, so
"idle session" really means "between turns", and their KV is spread across GPU and
CPU tiers at notice time. The synthetic generator's idle-time distribution should be
checked against these traces.

## 5. What to change to make this SOP- and paper-worthy

**Narrow claim (use this wording):**

> Spot reclaims delete agent-session KV that no existing fault-tolerance system
> protects. We treat the termination notice as a budget and plan which session KV
> to save, and where, under deadline, bandwidth and failure-domain constraints. We
> map the regimes (notice, ρ, burst size, store bandwidth) in which on-notice
> evacuation matches or beats continuous replication at equal memory.

**Contributions, in order of how much they carry:**
1. **Characterisation:** how much KV value sits on a spot node under real agentic
   traces (GB per node, recompute GPU-seconds at risk, how it is split between hot
   and idle sessions). This survives a null result.
2. **The planner:** a deadline-bounded knapsack with failure domains. It generalises
   ShuntServe's stated future work from in-flight requests to sessions.
3. **The regime map with measured constants:** FIS notice timing, sustained NIC and
   store bandwidth, receiver slowdown, and the transfer/recompute crossover reproduced
   on g6e.
4. **A vLLM prototype:** deferred cascade plus `flush_for_deadline`
   ([phase3-design.md](phase3-design.md)), with an output-parity test.

**Experiments to add, cheapest first:**

| # | Experiment | Why | Cost |
|---|---|---|---|
| 1 | Re-run Phase 1b on the public traces (above) | Removes "synthetic workload", the first reviewer objection | CPU only |
| 2 | Reproduce ShuntServe's transfer-vs-recompute crossover for 8B on one g6e.xlarge | Anchors the cost model to a published number on the same hardware | inside the planned ~$2–3 run |
| 3 | Measure sustained NIC bandwidth over 120 s and FIS notice timing | Sets the real ρ (section 4.1) | same run |
| 4 | Add baselines: KevlarFlow-style in-flight replication; a Mooncake-style pool with 1 and 2 replicas; CacheWise as the reuse estimator | Turns the competitors into rows of the table | simulator |
| 5 | Add metrics: p99 TTFT of returning sessions, session completion time, steady-state replication egress | GPU-seconds alone hides the survivor overload a correlated wave causes | simulator |
| 6 | Two-node prototype with emulated W = 30 s and `tc`-throttled ρ ∈ {0.25 … 2} | The only experiment that makes the result "real" | on-demand quota (8 vCPU) allows 2 × g6e.xlarge |

**Realistic target.** A workshop paper (EuroMLSys, an MLSys or NeurIPS systems
workshop, HotCloud-style) is reachable with experiments 1–6. A main-track systems
paper would need multi-node scale and a production-trace partner, which this budget
can't buy. For the SOP, the strongest honest story is: *found the gap after two
reframings, built the simulator, found a counter-intuitive equal-memory result,
then validated the constants on real hardware.* The reframings are a strength if
the SOP says why each happened.

## 6. Claims to keep out of the SOP and README
- "First to predict" or "first to exploit correlated preemption" (Parcae, SkyNomad,
  hazardserve, SkyServe).
- "KV transfer beats recompute" (ShuntServe measured the opposite for 8B on these GPUs).
- "First fault-tolerant KV" (DéjàVu, KevlarFlow, GhostServe, LUMEN, ConServe).
- "Reuse prediction from agent semantics" as our contribution (CacheWise, Continuum,
  KVFlow).
- Any percentage from Phase 1b without "simulated, assumed constants".

## Sources
- ShuntServe, arXiv 2606.18600 (§5.1, §8.1)
- KevlarFlow, arXiv 2601.22438 (§3.2, §4.4)
- LUMEN, arXiv 2606.17787
- GhostServe, arXiv 2605.00831 (MLSys'26)
- SkyServe, arXiv 2411.01438 (§2, Fig. 3)
- CacheWise, arXiv 2606.16824
- Continuum, arXiv 2511.02230; KVFlow, arXiv 2507.07400; TokenCake, arXiv 2510.18586 *(abstract only)*
- hazardserve: github.com/lvlrSajjad/hazardserve
- agentic-kv-cache: github.com/gauravapiscean/agentic-kv-cache
- vLLM RFC #24256: github.com/vllm-project/vllm/issues/24256
- vLLM blog, "Serving Agentic Workloads at Scale with vLLM x Mooncake" (2026-05-06)
- vLLM blog, "vLLM x AgentX" (2026-09-08)

## 7. Novelty check, 7 October 2026 (closes the open item in section 3)

Targeted searches for any work that preserves *idle session / prefix KV* when a node
is about to be lost:

| Work | What it does | Node loss / notice? |
|---|---|---|
| CacheScout (arXiv 2608.14624, Jul 2026; vLLM) | Learns agent execution transitions online; uses them for eviction and prefetch. +10–18 pt hit rate, −18–45% mean TTFT. | No. Eviction under memory pressure on a live node. |
| TraceLab (arXiv 2606.30560) | Characterizes coding-agent workloads across providers: long loops, long contexts with short outputs, heavy-tailed tool calls, idle gaps. | No. Calls for "KV-cache management around human-paced gaps". That is our idle asset, but against eviction, not loss. |
| Continuum / CacheTTL (arXiv 2511.02230) | Pins KV for a TTL across tool calls. | No. |
| llm-d graceful shutdown (docs, v0.9) | On pod termination, stops routing and lets in-flight requests finish within `--shutdown-timeout`. | Drains in-flight requests only. Cached prefixes are not moved, and spot notices aren't mentioned. |
| llm-d P2P KV sharing (blog) | A consumer pulls prefix blocks from a peer's CPU offload tier over NIXL when the measured crossover favours it (GPT-OSS-120B on H200: pull wins below 2K tokens; GLM-5.2: break-even about 8.7K). | Assumes the peer stays alive. Nothing about peer loss. |

**Conclusion.** The intersection is still empty: *idle agent-session KV, protected
against node loss, using the termination notice as a budget*. Two of these results
also help the argument:
- llm-d's P2P pull is the **restore path** our evacuation needs. Blocks evacuated to a
  surviving peer's CPU tier are found by hash and pulled. It also sharpens the threat:
  a fleet that relies on P2P reuse loses every prefix held on a reclaimed peer.
- TraceLab and CacheScout show that the idle-gap asset is real and valuable. They
  defend it against eviction, and we defend it against reclaim. Cite both as
  complementary, and use CacheScout or Continuum as the reuse estimator rather than
  claiming one (section 4.4; `ReuseModel.HINTED` sweeps how much accuracy matters).

Sources: [CacheScout](https://arxiv.org/abs/2608.14624),
[TraceLab](https://arxiv.org/pdf/2606.30560),
[Continuum](https://arxiv.org/html/2511.02230v5),
[llm-d graceful shutdown](https://llm-d.ai/docs/dev/operations/graceful-shutdown),
[llm-d P2P KV sharing](https://llm-d.ai/blog/p2p-kv-cache-sharing-llm-d).
