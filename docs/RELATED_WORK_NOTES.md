# Related-work notes

Notes and citations for the paper's related-work, motivation and
limitations sections. Not paper prose, and no argument about which work
is better. Collected on 2026-11-20 by web search, then by fetching each
source. Part (a) lists work in four groups, each entry with what it does
and how it differs from a single shared policy layer. Part (b) lists
documented instances of each of our eight stress conditions. The file
ends with what was not found, what was not verified and the decisions
left open.

## How to read these notes

- **Access date.** Every URL below was fetched on 2026-11-20. Each entry
  repeats the date.

- **How a source was read.** arXiv pages were downloaded and read as
  text: the abstract page for the title, authors, versions, comments and
  abstract, and the HTML full text where an entry says so, searched for
  the passages quoted. GitHub issues, pull requests and the advisory
  were read through GitHub's public REST API (the issue and its comments
  as JSON) and are cited by their page URL. Other pages were downloaded
  and read as text. A quote is verbatim from that text, except that
  Markdown emphasis in an issue is dropped.

- **Read level.** "Abstract" means only the abstract page or the
  conference page was read. "Full text" says how much. A statement that
  a work does not do something holds only for what was read.

- **Primary sources only.** A paper's own page; a system's own
  documentation, repository, tracker or advisory; a vendor's own post.
  Searches and surveys led to some of them and are not cited as
  evidence. Leads that were not fetched are listed under "Not verified".

- **Numbers** are the source's own, with where they come from. None was
  recomputed here.

- **Dates.** A work first posted before 2025 is marked "background".

- **Tags.** Part (a) numbers its entries S (shared or multi-agent
  memory), A (memory access control), O (agent operating systems) and B
  (memory benchmarks). In part (b) each instance has a kind: P, a paper
  that measures it; A, a security advisory or CVE; V, a vendor's own
  documentation or report; T, an issue, pull request or discussion in a
  system's own tracker or forum.

- **Reports are reports.** An issue states what its author saw.
  "Confirmed" is used only where a maintainer's reply or a merged fix
  says so.

- **No ranking.** "Differs" states a difference of design or of
  evidence, not which is better.

## What "a single shared policy layer" means here

One place, the kernel, decides what every agent's memory request stores
and returns. The decisions are a library, `aios/memory/pipeline/`, which
the kernel runs for every agent and which each replicated agent runs for
itself (`REPLICATED_LOGIC.md:14-21`, `RETRIEVAL_PATH.md:3-16`). The
comparisons below use these seven responsibilities:

| # | Responsibility | Where ours defines it |
|---|---|---|
| 1 | User partition: no row of one user reaches another user's block | `RETRIEVAL_PATH.md:28`, `BENCHMARK_V2.md:38-44` |
| 2 | Visibility between agents: an agent sees its own rows and rows marked shared | `RETRIEVAL_PATH.md:29-31`, `SHARED_MEMORY_SYSTEM.md:250-260` |
| 3 | Session-bound identity: the user comes from the kernel session, not from the agent's claim | `STRESS_DIMENSIONS.md:387-402` |
| 4 | Write-before-read ordering across writers: one barrier for every agent | `REPLICATED_LOGIC.md:72-79`, `STRESS_DIMENSIONS.md:266-273` |
| 5 | Deletion with tombstones: a forget removes every carrier of the fact, whoever wrote it, and a tombstone guards later reads | `DELETION_AND_SUPERSESSION.md:102-106`, `:160-182` |
| 6 | Supersession: a later statement retires the earlier rows of its slot | `DELETION_AND_SUPERSESSION.md:107-109` |
| 7 | Write quota per writer, user and session | `STRESS_DIMENSIONS.md:477-493` |

Three loci are compared: the kernel; the same library replicated in each
agent (`REPLICATED_LOGIC.md:67-88`); each backend used natively, the way
its documentation says (`NATIVE_USAGE.md:3-10`, `:62-69`).

**What no source below does, as far as read.** None compares one policy
layer with the same logic replicated in each agent. The nearest are one
live service measured with no comparand (S1), one architecture argued
without experiments (O2), and one method compared with a centralized
baseline, for the currency of plans, not for memory policy (S12). See
"Not found".

## (a) 1. Shared or multi-agent memory

- **S1. Governed Shared Memory (the closest to ours).** "Governed Shared
  Memory for Multi-Agent LLM Systems". Yanki Margalit, Nurit
  Cohen-Inger, Erni Avram, Ran Taig, Oded Margalit. arXiv:2606.24535, v1
  23 Jun 2026, cs.AI; no venue on the page.
  https://arxiv.org/abs/2606.24535 and
  https://arxiv.org/html/2606.24535v1. Accessed 2026-11-20. Read:
  abstract; full text (HTML v1), searched.

  Does: names four failure modes of memory that a fleet of agents
  shares, "unauthorized leakage, stale propagation, contradiction
  persistence, and provenance collapse", and four primitives against
  them: "scoped retrieval, temporal supersession, provenance tracking,
  and policy-governed memory propagation". They run in MemClaw, "a
  production multi-tenant memory service", measured live with a harness,
  ArgusFleet. Reported in §8.3: fleet-sibling visibility 117 of 120,
  0.975 [0.929, 0.991]; cross-fleet leaks 0 of 80, [0.000, 0.046]; on 8
  dedicated facts under strong write mode, a write-to-visible window of
  median 0.83 s and at most 1.97 s. Reported in §8.4: supersession in 90
  of 90 fact-runs where both contradictory writes were admitted, 1.000
  [0.959, 1.000]; detection 98 of 200 overall, because the synchronous
  dedup gate rejected 206 of 400 writes; stale reads 0 of 200. Three
  production findings are instances in part (b): conditions 5, 6 and 7.

  Differs: one layer between the agents and the store, as ours, scoped
  by tenant, fleet, agent and trust level where ours has a user
  partition and an owner-or-shared rule. No comparand, §10: "We do not
  compare against a baseline (e.g., a long-context-only configuration,
  or an alternative memory implementation)." Self-evaluated, §10:
  "ArgusFleet and MemClaw are built by the same group; this is an
  evaluation of our own production service, not an independent audit."
  Each fact runs "a sequential writer pair separated by a small delay,
  and a concurrent pair dispatched simultaneously" (§7.2); as read, the
  counts are not reported apart. The full text has no occurrence of
  "delet", "forget", "tombstone", "quota" or "flood".

- **S2. Architecture perspective.** "Multi-Agent Memory from a Computer
  Architecture Perspective: Visions and Challenges Ahead". Zhongming Yu,
  Naicheng Yu, Hejia Zhang, Wentao Ni, Mingrui Yin, Jiaying Yang, Yujie
  Zhao, Jishen Zhao. arXiv:2603.10062, v1 9 Mar 2026, v2 30 Mar 2026,
  cs.AR; no venue on the page. https://arxiv.org/abs/2603.10062.
  Accessed 2026-11-20. Read: abstract.

  Does: "This position paper frames multi-agent memory as a computer
  architecture problem." It contrasts shared and distributed memory,
  proposes a three-layer hierarchy (I/O, cache, memory), and names "two
  critical protocol gaps: cache sharing across agents and structured
  memory access control." Its claim: "We argue that the most pressing
  open challenge is multi-agent memory consistency." Differs: a position
  paper with no system or measurement in the abstract. It names as open
  two things our layer implements for one case: access control on
  memory, and which writes a read sees.

- **S3. Mesh Memory Protocol.** "Mesh Memory Protocol: Semantic
  Infrastructure for Multi-Agent LLM Systems". Hongwei Xu.
  arXiv:2604.19540, v1 21 Apr 2026, cs.MA; no venue on the page; the
  comments name a specification, "MMP v0.2.3".
  https://arxiv.org/abs/2604.19540. Accessed 2026-11-20. Read: abstract.

  Does: a protocol for peer agents that share cognitive state across
  sessions: a fixed seven-field block schema (CAT7), acceptance by the
  receiver field by field (SVAF), lineage by content-hash keys, and
  storage of only "the receiver's own role-evaluated understanding of
  each accepted CMB, never the raw peer signal". "Each agent decides
  field by field what to accept from peers, not accept or reject whole
  messages." It says "MMP is specified, shipped, and running in
  production across three reference deployments"; the abstract reports
  no measurement. Differs: the opposite placement. The rule sits in each
  receiving agent, peer to peer, with no shared store and no central
  layer: in our terms a replicated design in which each agent's rule is
  its own on purpose.

- **S4. Shared Selective Persistent Memory.** "Shared Selective
  Persistent Memory for Agentic LLM Systems". Sanjana Pedada, Aditya
  Dhavala, Neelraj Patil. arXiv:2607.09493, v1 10 Jul 2026, v2 15 Sep
  2026, cs.AI; no venue on the page. https://arxiv.org/abs/2607.09493.
  Accessed 2026-11-20. Read: abstract.

  Does: keeps four kinds of reusable context across a coding agent's
  sessions (task specifications, data schemas, tool configurations,
  output constraints) and "packages them into workspaces transferable
  across users under role-based access control." Reported: with a
  formatting rule given once and then withheld, "no memory completes
  0/12 trials at 3.8K input tokens, selective memory completes 12/12 at
  3.9K, and full conversation history completes 8/12 at 7.7K"; on 24
  enterprise tasks, "selective memory completes 23/24 against 19/24 and
  17/24, though at that sample no pairwise difference reaches
  significance." Differs: it shares across users on purpose, inside a
  workspace, where our partition forbids it. Access is by role on a
  workspace; the abstract does not say where the rule is enforced, and
  names no ordering across writers, deletion or quota.

- **S5. ShareMem.** "Learning from Others, Acting for You: Cross-User
  Memory Sharing for LLM Agents". Jinming Hu, Haodong Zhao, Qi Jia, Die
  Chen, Tianhang Zhao, Sufeng Duan, Gongshen Liu. arXiv:2609.32511, v1
  26 Sep 2026, cs.AI; comments: "Work in progress".
  https://arxiv.org/abs/2609.32511. Accessed 2026-11-20. Read: abstract.

  Does: pools reusable experience across users and grounds its use in
  the receiving user's own preferences: consolidation in two stages, and
  "scope-first retrieval jointly selects local and shared experiences
  under a common entry budget". Its problem statement: "Pooling memories
  expands access but risks transferring preferences that conflict with
  the receiving user's requirements." Evaluated on Mind2Web, VitaBench
  2.0 and MemoryCode with four backbones; no numbers in the abstract.
  Differs: cross-user sharing is the goal. The risk it manages, one
  user's preference applied to another, is the benign contamination of
  part (b), condition 7, not a partition leak. No access rule between
  agents in the abstract.

- **S6. G-Memory.** "G-Memory: Tracing Hierarchical Memory for
  Multi-Agent Systems". Guibin Zhang, Muxin Fu, Guancheng Wan, Miao Yu,
  Kun Wang, Shuicheng Yan. arXiv:2506.07398, v1 9 Jun 2025, v2 16 Jun
  2025, cs.MA; no venue on the page. https://arxiv.org/abs/2506.07398.
  Accessed 2026-11-20. Read: abstract.

  Does: "a hierarchical, agentic memory system for MAS inspired by
  organizational memory theory", with a "three-tier graph hierarchy:
  insight, query, and interaction graphs", retrieval of insights and
  condensed collaboration trajectories for a new query, and an update
  after each task. Reported: up to 20.89% higher embodied-action success
  and 10.12% higher knowledge-QA accuracy, over five benchmarks, three
  backbones and three frameworks. Differs: it stores one team's task
  trajectories to raise task success. One team, one store: no users,
  visibility rule, ordering guarantee, deletion or quota in the
  abstract.

- **S7. MIRIX-2.0.** "MIRIX-2.0: Multi-Agent Memory System". Wei-Chieh
  Huang, Weizhi Zhang, Jiayan Nan, Peng Xia, Yu Wang. arXiv:2611.12068,
  v1 9 Nov 2026, cs.CL; no venue on the page.
  https://arxiv.org/abs/2611.12068. Accessed 2026-11-20. Read: abstract.

  Does: "Six typed memory agents keep complete records as the system of
  record", indexed by a provenance hypergraph. "Retrieval runs under
  explicit budgets, so the evidence a question inspects does not grow
  with the history." Reported: "It reaches 91.4% on LoCoMo and 72.6% on
  LongMemEval-S". Differs: "multi-agent" names the memory system's own
  internal agents. The abstract describes single-user QA benchmarks, not
  several application agents that share memory.

- **S8. S-Bus.** "S-Bus: Automatic Read-Set Reconstruction for
  Multi-Agent LLM State Coordination". Sajjad Khan. arXiv:2605.17076, v1
  16 May 2026, v2 22 May 2026, cs.LG; no venue on the page.
  https://arxiv.org/abs/2605.17076 and
  https://arxiv.org/html/2605.17076v2. Accessed 2026-11-20. Read:
  abstract; of the full text, §II-A only.

  Does: "S-Bus is an HTTP middleware whose central mechanism, a
  server-side DeliveryLog, reconstructs each agent's read set at commit
  time from observed HTTP GET traffic." It enforces an isolation
  property, ORI, with mechanised proofs. Reported: "zero Type-I
  corruptions across 884,110 commit attempts (427,308 under active
  contention)." Its own limit: "ORI is semantically neutral in
  dedicated-shard workloads but harmful in single-shard collaborative
  writing because preservation propagates concurrent contradictions."
  Differs: a layer outside the agents, as ours, for conflicts on shared
  mutable state in general. It validates read sets at commit; ours makes
  a read wait for the writes accepted before it. No users, visibility or
  deletion. Its lost-update measurement is an instance in part (b),
  condition 5.

- **S9. CoAgent.** "CoAgent: Concurrency Control for Multi-Agent
  Systems". Hongtao Lyu, Dingyan Zhang, Mingyu Wu, Xingda Wei, Haibo
  Chen. arXiv:2606.15376, v1 13 Jun 2026, cs.DC; comments: "14 pages, 7
  figures. Submitted to ATC 2026". https://arxiv.org/abs/2606.15376.
  Accessed 2026-11-20. Read: abstract.

  Does: concurrency control for agents that mutate one git tree, cluster
  or document: a serialization order fixed at launch, speculative writes
  in place, and a notification that asks an affected agent to repair its
  plan. "Locks block long inference intervals; OCC abort-and-retry
  discards minutes of work on every conflict." Reported on ten contended
  workloads: within 5% of serial correctness at a 1.4× speedup and
  near-serial token cost. Differs: shared task state, not a user's
  long-term memory, and the agents' own models take part in the control:
  "the LLM inside each agent can judge whether a conflicting write
  invalidates its plan". Ours involves no agent: the read waits.

- **S10. AC-Saga.** "Recoverability-Conditioned Concurrency Control: A
  Transactional Layer for Agents That Share State". Kunal Jadhav,
  Siddhesh Vinayak More. Poster at the NeurIPS 2026 workshop "AgenticOS:
  Co-designing Systems and ML Foundations of an OS Layer for Agentic
  AI", Fri, Dec 11, 2026. https://neurips.cc/virtual/2026/166757 (it
  links OpenReview, https://openreview.net/forum?id=j3DZkJdmzh, not
  fetched). Accessed 2026-11-20. Read: the abstract on the virtual page.

  Does: a transactional layer for several agents that write one
  database: locking conditioned on whether a step can be undone, and
  deterministic log-based compensation. The failure it targets: "When
  several LLM agents write to one shared database, an agent that is
  rolled back after committing an irreversible step leaves the shared
  state quietly corrupted." Reported: "100% final-state correctness at
  zero recovery tokens, above a recovery-blind deterministic system
  (79.7%) and an LLM-recovery one (98.4%)"; "an optimistic baseline that
  abandons a conflicted transaction reaches 9.6 +/- 1.7% unrecoverable
  aborts"; "Every headline metric is measured on real PostgreSQL."
  Differs: a layer outside the agents for writes to shared state and
  their rollback. It gives no read-after-write guarantee to a consumer
  and has no users or visibility.

- **S11. Multi-Agent Memory Inconsistency.** "Multi-Agent Memory
  Inconsistency: Where Factual Conflicts Disappear in LLM Agents". Hejia
  Zhang, Zhongming Yu, Yimin Ding, Wei-Ting Chen, Hengjia Yu, Wentao Ni,
  Yijun Liu, Cong Xu, Xin Chen, Matrix Yao, Fan Zhao, Jishen Zhao.
  arXiv:2611.22245, v1 17 Nov 2026, v2 18 Nov 2026, cs.AI; no venue on
  the page. https://arxiv.org/abs/2611.22245. Accessed 2026-11-20. Read:
  abstract.

  Does: a benchmark and an evidence-flow profiler on controlled factual
  conflicts in Harvey LAB document-review tasks. Pooled over three
  models, "requiring delegation increases retrieval of both conflicting
  claims from 50.2% to 68.7% relative to single-agent execution, yet
  conflict detection falls from 16.2% to 13.2%"; "workers report both
  claims for only 35.2% of retrieved pairs". Differs: "memory" here is
  each worker's context and its handoff to a lead agent inside one task.
  No persistent store, users or policy layer. It shows a conflict
  between two statements getting lost between agents, which is what our
  contradiction probe asks of a store.

- **S12. Planfence.** "Fresh Memory, Stale Plans: Derivation Currency
  for Distributed LLM-Agent Memory". Evan Chen, Shiqiang Wang,
  Christopher G. Brinton. arXiv:2609.03340, v1 3 Sep 2026, v2 27 Sep
  2026, cs.AI; no venue on the page. https://arxiv.org/abs/2609.03340.
  Accessed 2026-11-20. Read: abstract.

  Does: before a protected action, follows a stored plan's links to the
  inputs it was derived from and asks each input's owner for its current
  head. "In 30 live five-agent workflows with a revision inserted after
  planning, a freshness-only executor acts on the stale plan every time,
  whereas Planfence, like a centralized-lineage baseline that requires a
  shared store, completes all 30 correctly." Differs: it argues the
  other placement: "Application code supplies the links and declares the
  scope; no shared memory service is required." It is the one source
  found that sets a design without a shared service against a
  centralized one, for the currency of plans, not for memory policy.

- **S13. memorywire.** "memorywire: A Vendor-Neutral Wire Format for
  Agent Memory Operations". Thamilvendhan Munirathinam.
  arXiv:2606.01138, v1 31 May 2026, v4 12 Aug 2026, cs.CR; no venue on
  the page. https://arxiv.org/abs/2606.01138. Accessed 2026-11-20. Read:
  abstract.

  Does: a JSON-Schema wire format for five operations (remember, recall,
  forget, merge, expire), a store interface, a fan-out router and an
  optional human-review channel, with adapters for sqlite-vec, mem0,
  Letta, Cognee and pgvector. Its motivation: "There is no shared wire
  format: every integration is bespoke, every migration rebuilds memory
  from scratch, and no framework ships a governance surface that lets a
  human review writes before they enter long-term storage." Reported: "a
  16-scenario cross-adapter conformance suite passing 68 of 80 cells
  with zero failures". Differs: it standardizes the interface to
  backends, the role of our provider contract (`PROVIDER_CONTRACT.md`),
  not a policy across agents: no visibility, identity or ordering in the
  abstract. It bears on version skew (part (b), condition 3).

- **S14. Mem0 (a backend of ours).** "Mem0: Building Production-Ready AI
  Agents with Scalable Long-Term Memory". Prateek Chhikara, Dev Khant,
  Saket Aryan, Taranjeet Singh, Deshraj Yadav. arXiv:2504.19413, v1 28
  Apr 2025, cs.CL; no venue on the page.
  https://arxiv.org/abs/2504.19413. Accessed 2026-11-20. Read: abstract.

  Does: extracts, consolidates and retrieves salient facts from
  conversations, with a graph variant. Reported on LoCoMo: "Mem0
  achieves 26% relative improvements in the LLM-as-a-Judge metric over
  OpenAI"; "Mem0 attains a 91% lower p95 latency and saves more than 90%
  token cost". Differs: a backend evaluated on one user's conversations.
  Its scope is the identifiers each caller passes (A10). In our design
  it sits under all three loci, not in place of the policy layer.

- **S15. Zep and Graphiti (a backend of ours).** "Zep: A Temporal
  Knowledge Graph Architecture for Agent Memory". Preston Rasmussen,
  Pavlo Paliychuk, Travis Beauvais, Jack Ryan, Daniel Chalef.
  arXiv:2501.13956, v1 20 Jan 2025, cs.CL; no venue on the page.
  https://arxiv.org/abs/2501.13956. Accessed 2026-11-20. Read: abstract.

  Does: a memory layer whose core is Graphiti, "a temporally-aware
  knowledge graph engine". Reported: on Deep Memory Retrieval against
  MemGPT, "Zep demonstrates superior performance (94.8% vs 93.4%)"; on
  LongMemEval, "accuracy improvements of up to 18.5% while
  simultaneously reducing response latency by 90% compared to baseline
  implementations". Differs: a backend. Its namespaces are a `group_id`
  that the application supplies and must authorize (A13).

- **S16. A-MEM (a backend of ours).** "A-MEM: Agentic Memory for LLM
  Agents". Wujiang Xu, Zujie Liang, Kai Mei, Hang Gao, Juntao Tan,
  Yongfeng Zhang. arXiv:2502.12110, v1 17 Feb 2025, v11 8 Oct 2025,
  cs.CL; comments: "Advances in Neural Information Processing Systems
  (NeurIPS 2025)". https://arxiv.org/abs/2502.12110. Accessed
  2026-11-20. Read: abstract.

  Does: "When a new memory is added, we generate a comprehensive note
  containing multiple structured attributes, including contextual
  descriptions, keywords, and tags." New memories "can trigger updates
  to the contextual representations and attributes of existing
  historical memories". Differs: a backend for one agent. No users,
  sharing rule or deletion semantics in the abstract. Its rewriting of
  older notes is why our forget also deletes notes whose generated text
  carries a forgotten value (`AMEM_BACKEND.md:268-282`).

- **S17. Letta, shared memory blocks (vendor documentation).** Letta
  Docs, "Shared memory". No date on the page; it covers "Letta's legacy
  v1 API". Requested
  https://docs.letta.com/guides/agents/multi-agent-shared-memory, served
  at https://docs.letta.com/v1-sdk/memory/shared-memory. Accessed
  2026-11-20. Read: the page.

  Does: one memory block attached to several agents, which all read and
  write it: "When one agent updates the block, all others see the change
  immediately." Access is one flag per block: "Read-only applies to the
  entire block, not per-agent. You cannot make a block read-only for
  some agents but writable for others." Its table of concurrent edits is
  an instance in part (b), condition 5. The page also says: "Memory
  blocks may be deprecated in the future. We do not recommend building
  on memory blocks anymore." Differs: sharing is attachment. Every
  attached agent reads the whole block: no rule per row, no user
  partition inside a block, no ordering beyond what each edit tool does.

- **S18. This project's own workshop paper (not independent work).**
  "Kernel-Managed Shared Memory for System-Wide Personalization". Ryan
  Lum, Yongfeng Zhang. arXiv:2609.10144, v1 9 Sep 2026, v3 21 Oct 2026,
  cs.AI; comments: "Accepted to AgenticOS Workshop @ NeurIPS 2026.
  Camera-ready version". https://arxiv.org/abs/2609.10144. Accessed
  2026-11-20. Read: abstract.

  Does: the workshop version of this project: "the agent-system kernel,
  not individual agents, governs retrieval, privacy enforcement, and
  prompt injection", evaluated "across three assistant models (GPT-4o,
  Llama-3.1:8B, Qwen-2.5:7B) and 1,800 total trials" (the trials of
  `DEV_STATUS.md:4202-4204`). Listed so that a search hit on it is not
  taken for independent work. It came up in a generic search on
  centralized and per-agent memory control; no search was made on names.
  The NeurIPS 2026 AgenticOS workshop page lists it (O9). How the
  main-track paper cites it is an open decision.

## (a) 2. Memory access control

- **A1. Collaborative Memory.** "Collaborative Memory: Multi-User Memory
  Sharing in LLM Agents with Dynamic Access Control". Alireza Rezazadeh,
  Zichao Li, Ange Lou, Yuying Zhao, Wei Wei, Yujia Bao.
  arXiv:2505.18279, v1 23 May 2025, cs.MA; no venue on the arXiv page.
  The ICML 2025 virtual page lists it as a poster in the workshop
  "Multi-Agent Systems in the Era of Foundation Models: Opportunities,
  Challenges and Futures". https://arxiv.org/abs/2505.18279,
  https://arxiv.org/html/2505.18279v1 and
  https://icml.cc/virtual/2025/49354. Accessed 2026-11-20. Read:
  abstract; full text (HTML v1), searched.

  Does: "asymmetric, time-evolving access controls encoded as bipartite
  graphs linking users, agents, and resources", two tiers (private
  fragments "visible only to their originating user" and shared
  fragments), "immutable provenance attributes" on each fragment, and
  read and write policies that transform fragments. Its read and write
  transformation modules are LLM components ("All LLM-based components
  [...] use gpt-4o"). Evaluated on MultiHop-RAG (609 articles, 2,556
  questions): "Under fully collaborative memory, accuracy remains above
  0.90 on average across all query indices"; "Resource usage decreases
  by up to 61% at 50% overlap and by 59% at 75% overlap compared to
  isolated memory." Its limits: large deployments "where concurrency is
  frequent" are "largely unexplored", and "the probabilistic nature of
  these models can lead to occasional hallucinations or policy breaches,
  despite our enforcement mechanisms." Differs: one framework that
  enforces read and write policies over a shared store, as ours; its
  policies are graph permissions applied in part by an LLM, where ours
  are fixed rules in code. As read, no ordering across writers or quota
  and no count of policy violations; the full text has no occurrence of
  "delet".

- **A2. AIM and MUMBench.** "AIM: A Privacy-Aware Interoperable Memory
  Framework for Multi-Agent Multi-User LLM Systems". Zachary Johnson,
  Nigel Boachie Kumankumah, Somya Chatterjee, Tejas Sathyamurthi, Min
  Chen, Xinyi Alice Li, Xiao Wang, Emily Morgan Gelchie, Jessica Lin,
  Sadid A. Hasan, Sulaiman Vesal. arXiv:2609.12320, v1 11 Sep 2026,
  cs.AI; no venue on the page. https://arxiv.org/abs/2609.12320 and
  https://arxiv.org/html/2609.12320v1. Accessed 2026-11-20. Read:
  abstract; full text (HTML v1), searched.

  Does: "AIM runs as a portable, system-agnostic service that is
  designed to enable heterogeneous agents across different vendors and
  deployments to share a single memory registry while respecting
  user-level privacy constraints." An LLM classifies each memory as
  private or public; retrieval pushes the visibility predicate "into the
  vector index as a server-side filter"; "update and delete operations
  may be performed only by the creating user (or, absent user context,
  the creating agent)". MUMBench: "672 manually validated,
  chronologically ordered interactions across 93 users in four domains".
  Reported: "96.0% visibility classification accuracy, 58.8% strict
  operation accuracy, and 70.5% state-aware operation accuracy."
  Differs: the closest design to ours in placement: one service for
  heterogeneous agents. The user is an input to retrieval ("Given query
  q, user u, and agent a"); no binding of identity to a session was
  found. Visibility is decided by an LLM classifier, where ours is set
  by the writer. It motivates MUMBench by a gap ("No existing benchmark
  evaluates private versus shared memory classification, cross-session
  synchronization, or memory integrity under concurrent multi-agent
  updates."), and its interactions "are replayed sequentially through
  the full inference pipeline". Its own limit: "any individual can add
  or edit public memories with information that is not factual." No
  baseline locus with the same logic in each agent.

- **A3. Memory as a Service.** "Memory as a Service (MaaS):
  Purpose-Bound Memory Mediation for Cooperative Agents". Haichang Li.
  arXiv:2506.22815, v1 28 Jun 2025, v2 11 Jun 2026, cs.HC; comments:
  "Accepted to the KDD 2026 Workshop on Agentic Software Engineering
  (AgenticSE @ KDD 2026)". https://arxiv.org/abs/2506.22815. Accessed
  2026-11-20. Read: abstract.

  Does: a mediator for memory that many agents draw on: "each invocation
  is evaluated by owner, requester, recipient, task, and declared
  purpose", and the mediator withholds, abstracts or reveals each item.
  Diagnostic probes on MAGPIE: relevance-based retrieval reaches AUROC
  0.570 and leaks 53.0% of private items; contextual-integrity prompting
  cuts leakage by 21.8 points and leaves 32.6%. Differs: a position with
  diagnostic probes, not a system evaluation. The decision is
  purpose-bound and per item; ours is an owner-or-shared rule with a
  user partition. The numbers measure retrieval and prompting, not a
  mediator.

- **A4. Audience-Bound Persistent Memory.** "Audience-Bound Persistent
  Memory: Authorization Across the Memory Lifecycle". Sibo Liu.
  arXiv:2609.36373, v1 28 Sep 2026, cs.CR; no venue on the page.
  https://arxiv.org/abs/2609.36373. Accessed 2026-11-20. Read: abstract.

  Does: each memory item carries the audience present when it was
  recorded; derived items get the intersection of their sources'
  audiences or are suppressed; "an audience widens only by an explicit,
  object-specific grant"; unresolved viewers fail "closed to
  public-only". "Under explicit identity, provenance and
  complete-mediation assumptions, this admission is sound and
  policy-complete on the exact assembled context, enforced by exclusion
  rather than by model behavior." Reported over 10,000 multi-party
  histories: "no forbidden item entered any architecture's context,
  whereas unscoped retrieval exposed forbidden items in 82% of its
  contexts"; entitled recall "exceeded unscoped retrieval by 0.30
  Recall@5". Differs: one agent acting for one owner across audiences,
  not several agents of one user. It assumes the identity and complete
  mediation that our session binding and single locus provide, and does
  not test them.

- **A5. SSGM.** "Governing Evolving Memory in LLM Agents: Risks,
  Mechanisms, and the Stability and Safety Governed Memory (SSGM)
  Framework". Chingkwun Lam, Jiaxin Li, Lingfei Zhang, Kuo Zhao.
  arXiv:2603.11768, v1 12 Mar 2026, v2 19 May 2026, cs.AI; no venue on
  the page. https://arxiv.org/abs/2603.11768. Accessed 2026-11-20. Read:
  abstract.

  Does: "we propose the Stability and Safety-Governed Memory (SSGM)
  framework, a conceptual governance architecture." It "decouples memory
  evolution from execution by enforcing consistency verification,
  temporal decay modeling, and dynamic access control prior to any
  memory consolidation", argued "Through formal analysis and
  architectural decomposition". Differs: conceptual, with no
  implementation or measurement in the abstract, and about one agent's
  evolving memory rather than several agents'. Our
  `HETEROGENEITY.md:172-174` cites it; see "Our docs' own citations".

- **A6. MemTrust.** "MemTrust: A Zero-Trust Architecture for Unified AI
  Memory System". Xing Zhou, Dmitrii Ustiugov, Haoxin Shang, Kisson Lin.
  arXiv:2601.07004, v1 11 Jan 2026, cs.CR; no venue on the page.
  https://arxiv.org/abs/2601.07004. Accessed 2026-11-20. Read: abstract.

  Does: a five-layer abstraction of memory systems (Storage, Extraction,
  Learning, Retrieval, Governance) with a trusted execution environment
  per layer. Its premise: "centralization creates a trust crisis where
  users must entrust cloud providers with sensitive digital memory
  data." No numbers in the abstract. Differs: it protects a central
  memory from its operator with hardware; ours trusts the kernel and
  constrains the agents. Its threat is the provider, ours a faulty or
  differently built agent.

- **A7. TMA-NM.** "Securing LLM-Agent Long-Term Memory Against
  Poisoning: Non-Malleable, Origin-Bound Authority with Machine-Checked
  Guarantees". Yedidel Louck. arXiv:2606.24322, v1 23 Jun 2026, cs.CR;
  no venue on the page. https://arxiv.org/abs/2606.24322. Accessed
  2026-11-20. Read: abstract.

  Does: binds a memory item's authority to act to its origin at write
  time. "An attacker can launder an untrusted origin through three
  channels specific to LLM agents: the agent's own summarization, a
  trusted-tool echo, and manufactured corroboration." Reported over
  eight frontier models: "existing defenses fail exactly where the
  theory predicts (up to 68% laundering attack-success), while TMA-NM
  reaches 0% attack success on both direct and laundering attacks across
  all models and channels, at full legitimate utility." Differs:
  authority of content (what a memory may cause), not visibility or
  identity. Write-time origin binding resembles our stamping of owner
  and user at write time, for a different property.

- **A8. ClawMMU.** "ClawMMU: Protection-Coherent Virtual Memory for
  Stateful LLM Agents". Jinhao Hu, Bardia Mohammadi, Mofasshara B
  Rafique, Lars H Klein, Akhil Arora, Ashvin Goel, Laurent
  Bindschaedler. Poster at the NeurIPS 2026 AgenticOS workshop, Fri, Dec
  11, 2026. https://neurips.cc/virtual/2026/166769 (it links OpenReview,
  https://openreview.net/forum?id=VlYSoodm0z, not fetched). Accessed
  2026-11-20. Read: the abstract on the virtual page.

  Does: "Paging gives structure, provenance, identity, and addressing
  but no protection, so untrusted pages act as policy. Protection is the
  missing abstraction." It keeps "owner, scope, and authority coherent
  through context admission, durable derivation, and effect dispatch".
  "A forged instruction admitted as evidence stays evidence and cannot
  act." No numbers in the abstract. Differs: OS-style protection inside
  one agent's memory against untrusted content. Owner and scope are the
  fields our partition and visibility rule read; its subject is
  authority, ours visibility across agents.

- **A9. MemLeak, cross-user.** "MemLeak: Cross-User Semantic Leakage in
  Multi-Tenant AI Agent Memory". Priyanka Mudgal, Kai Zhao, Guilin
  Zhang, Andy Olsen, Ezekiel Miller, Xu Chu, Aletta J Blanken. Poster at
  the NeurIPS 2026 workshop "Personalized, Aligned, Long-Term Memory for
  AI Systems (PALM)"; the page gives a room, no date.
  https://neurips.cc/virtual/2026/169601 (it links OpenReview,
  https://openreview.net/forum?id=2yIq6e5Qak, not fetched). Accessed
  2026-11-20. Read: the abstract on the virtual page.

  Does: "a user's query can retrieve semantically adjacent memories
  belonging to another user through ordinary cosine-similarity
  retrieval, without any exploit." Reported: incidental, non-adversarial
  leakage of 70 to 100% under pooled same-team retrieval; crafted
  memories reach 90 to 100% top-k placement; and "only hard
  post-retrieval ownership gating consistently restores the clean
  baseline (1.00/5)", at a measured overhead of about 1.4 ms per query.
  Differs: one shared store with and without an ownership gate, not
  several agents. Its winning mitigation is the check our user partition
  makes after retrieval. An instance in part (b), condition 7.

- **A10. Mem0, entity-scoped memory (vendor documentation).** Mem0 Docs,
  "Entity-Scoped Memory". No date on the page.
  https://docs.mem0.ai/platform/features/entity-scoped-memory. Accessed
  2026-11-20. Read: the page.

  Does: four identifiers scope a memory (`user_id`, `agent_id`,
  `app_id`, `run_id`), passed by the caller on every write and as
  filters on every read. "each extracted fact is attributed to whoever
  stated it, so a record carries user_id or agent_id , not both."
  "Unmentioned entities are not constrained : Passing only {"user_id":
  "alice"} matches on user_id alone." Differs: the scope is whatever
  each caller sends, the per-agent convention our native locus follows
  (`NATIVE_USAGE.md:62-69`). Its documented pitfall is an instance in
  part (b), condition 1.

- **A11. Amazon Bedrock AgentCore, fine-grained access control for
  Memory (vendor documentation).** "Fine-grained access control for
  Memory - Amazon Bedrock AgentCore". No date on the page.
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-gateway-fgac.html.
  Accessed 2026-11-20. Read: the page.

  Does: Cedar policies on a gateway in front of Memory: "The gateway
  evaluates these policies before it forwards a request to Memory."
  "Evaluation is deny-by-default and forbid overrides permit." The
  isolation pattern binds the record's actor to the caller's token: "A
  caller can only access events where the request's actorId equals their
  JWT sub claim." Batch operations: "at the fine-grained access control
  layer, a batch operation is all-or-nothing". Differs: the nearest
  vendor design to our session binding: one enforcement point keyed on
  an authenticated identity rather than the caller's claim. It decides
  access per request and per actor, not visibility between agents of one
  user, ordering, deletion or quota. Its adoption caveat is an instance
  in part (b), condition 1.

- **A12. LangSmith, per-user store isolation (vendor documentation).**
  "Isolate store data per user - Docs by LangChain". No date on the
  page. https://docs.langchain.com/langsmith/store-auth. Accessed
  2026-11-20. Read: the page.

  Does: "By default, store namespaces are shared across all callers."
  "Store isolation requires a @auth.on.store handler." The handler
  "either validates that the namespace starts with that identity, or
  rewrites the namespace to prepend it." Differs: isolation is opt-in,
  written by the deployer as an authorization hook on the server; ours
  is on by default. One rule per deployment on the server, as ours, but
  for users only, not visibility between agents.

- **A13. Graphiti, graph namespacing (vendor documentation).** Zep
  Documentation, Graphiti, "Graph Namespacing". No date on the page.
  https://help.getzep.com/graphiti/core-concepts/graph-namespacing.
  Accessed 2026-11-20. Read: the page.

  Does: "Nodes and edges with the same group_id form a cohesive,
  isolated graph". "Your application must authorize each group_id and
  group_ids value before it passes the value to Graphiti. Derive the
  value from authenticated application state. Do not accept a namespace
  identifier from an untrusted request. A namespace filter does not
  replace application authorization." Differs: the backend leaves
  authorization to each caller, the per-agent convention our native
  Graphiti cell follows. Ours derives the user from the kernel session
  (responsibility 3).

## (a) 3. Agent operating systems

- **O1. AIOS (background).** "AIOS: LLM Agent Operating System". Kai
  Mei, Xi Zhu, Wujiang Xu, Wenyue Hua, Mingyu Jin, Zelong Li, Shuyuan
  Xu, Ruosong Ye, Yingqiang Ge, Yongfeng Zhang. arXiv:2403.16971, v1 25
  Mar 2024, v5 12 Aug 2025, cs.OS; comments: "Published as a full paper
  at COLM 2025". https://arxiv.org/abs/2403.16971. Accessed 2026-11-20.
  Read: abstract. First posted in 2024: background.

  Does: "isolating resources and LLM-specific services from agent
  applications into an AIOS kernel", which provides "fundamental
  services (e.g., scheduling, context management, memory management,
  storage management, access control)". Reported: "up to 2.1x faster
  execution for serving agents built by various agent frameworks".
  Differs: the system ours is built on. Its abstract names memory
  management and access control as kernel services; it does not describe
  a shared memory policy between agents.

- **O2. AgentKernel.** "AgentKernel: The Trust-Native Agentic Operating
  System". Zhenhua Zou, Sheng Guo, Qiuyang Zhan, Lepeng Zhao, Shuo Li,
  Zhuotao Liu. arXiv:2609.29647, v1 29 Aug 2026, cs.CR; comments: "38
  pages, 5 figures". https://arxiv.org/abs/2609.29647. Accessed
  2026-11-20. Read: abstract.

  Does: argues that "current governance stacks remain application-level
  middleware that share a process trust boundary with the agents they
  monitor", and that agents need "mandatory, non-bypassable services for
  identity, input mediation, memory governance, and execution control".
  Four pillars: Identity, Perception, Cognition, Execution;
  "Kernel-managed identity supports trustworthy cross-organization
  collaboration"; "information-flow-controlled memory improves retrieval
  fidelity while limiting poisoning". Evaluated by "systematic
  comparison and security analysis"; no measurement in the abstract.
  Differs: the same placement argument as ours (enforcement outside the
  agent, kernel-managed identity), made for security against attack. As
  read, no experiment and no comparison with the same logic inside each
  agent.

- **O3. Agent libOS.** "Agent libOS: A Runtime Substrate for
  Capability-Controlled Self-Evolving LLM Agents". Yingqi Zhang.
  arXiv:2606.03895, v1 2 Jun 2026, v3 18 Aug 2026, cs.OS; comments name
  a project page. Also on the SOSP 2026 AgenticOS workshop program (O9).
  https://arxiv.org/abs/2606.03895. Accessed 2026-11-20. Read: abstract.

  Does: separates operation admission, information-flow admission and
  causal evidence, against "authority-escalation and data-exfiltration
  risks when visibility is mistaken for permission". "Operation
  admission combines process identity, Task Authority ceilings, typed
  Capabilities, policy or Human approval, budgets, and concrete
  primitives." Reported: "33/33 deterministic full-runtime tasks pass
  both task and safety oracles". Its limits: "Agent libOS does not
  prevent prompt injection, provide kernel-grade sandboxing, or roll
  back irreversible external effects." Differs: a library OS for one
  self-evolving agent's authority, including its Object Memory, not a
  policy over memory several agents share.

- **O4. Towards an Agent Operating System.** "Towards an Agent Operating
  System - Lessons from Classical and Cloud OS". Gosia Steinder,
  Hubertus Franke. arXiv:2607.25076, v1 27 Jul 2026, cs.AI; no venue on
  the page. https://arxiv.org/abs/2607.25076. Accessed 2026-11-20. Read:
  abstract.

  Does: a position: "no community consensus exists on what the core
  abstractions are or what guarantees they carry"; the path forward is
  to "derive new agentic abstractions by extending classical OS and
  cloud OS primitives to stochastic, natural-language-mediated
  execution, specify their semantics precisely, and consolidate around
  them". Differs: a methodology argument without a system. Ours is one
  such abstraction (memory with stated guarantees) for one benchmark.

- **O5. AgentOS.** "AgentOS: From Application Silos to a Natural
  Language-Driven Data Ecosystem". Rui Liu, Tao Zhe, Dongjie Wang, Zijun
  Yao, Kunpeng Liu, Yanjie Fu, Huan Liu, Jian Pei. arXiv:2603.08938, v1
  9 Mar 2026, v2 11 Mar 2026, cs.AI; no venue on the page.
  https://arxiv.org/abs/2603.08938. Accessed 2026-11-20. Read: abstract.

  Does: a research agenda for a personal agent OS. It names "poorly
  structured permission management" and "severe context fragmentation"
  in today's agents, and proposes that "The system core becomes an Agent
  Kernel that interprets user intent, decomposes tasks, and coordinates
  multiple agents". Differs: a vision without a system or measurement.
  Its kernel coordinates tasks; it does not specify a memory policy.

- **O6. MemOS.** "MemOS: A Memory OS for AI System". Zhiyu Li, Chenyang
  Xi, Chunyu Li, Ding Chen, Boyu Chen and 34 more (39 authors on the
  page). arXiv:2507.03724, v1 4 Jul 2025, v4 3 Dec 2025, cs.CL;
  comments: "36 pages, 10 figures, 5 tables".
  https://arxiv.org/abs/2507.03724. Accessed 2026-11-20. Read: abstract.

  Does: "we propose MemOS, a memory operating system that treats memory
  as a manageable system resource", unifying plaintext, activation and
  parameter memories; "a MemCube encapsulates both memory content and
  metadata such as provenance and versioning." Differs: an OS for the
  kinds of memory one model uses. The abstract does not discuss
  visibility between agents, users or access control.

- **O7. MemoryOS.** "Memory OS of AI Agent". Jiazheng Kang, Mingming Ji,
  Zhe Zhao, Ting Bai. arXiv:2506.06326, v1 30 May 2025, cs.AI; in the
  Proceedings of EMNLP 2025, pages 25961-25970 (ACL Anthology
  2025.emnlp-main.1318). https://arxiv.org/abs/2506.06326 and
  https://aclanthology.org/2025.emnlp-main.1318/. Accessed 2026-11-20.
  Read: abstract; the anthology page.

  Does: "three levels of storage units: short-term memory, mid-term
  memory, and long-term personal memory", with OS-inspired updates
  between them (FIFO, segmented pages). Reported on LoCoMo: "an average
  improvement of 49.11% on F1 and 46.18% on BLEU-1 over the baselines on
  GPT-4o-mini". Differs: "OS" names the memory hierarchy of one agent.
  No sharing, users or access control in the abstract.

- **O8. Concord.** "When Agent Context Goes Stale: Incoherence in
  Volatile Agent Context". Yingying Liu, Junzhou Fang, Chenxiong Qian.
  arXiv:2610.05281, v1 4 Oct 2026, v2 6 Oct 2026, cs.AI; comments:
  "Accepted to the AgenticOS Workshop at SOSP 2026".
  https://arxiv.org/abs/2610.05281. Accessed 2026-11-20. Read: abstract.

  Does: sources an agent observed (files) may be "modified by users,
  other agents, or external tools, while the model retains only the
  stale content in its context window", "causing agents to reuse
  outdated observations and make incorrect claims about the current
  workspace state". Concord links observations to sources and updates,
  annotates or suppresses stale context; on its ConcordBench it matches
  the oracle "while using 46.4% fewer tokens than the strongest
  non-oracle baseline". Differs: staleness in the context window after
  another agent's change, not in a memory store. It is the runtime
  analogue of our concurrency condition.

- **O9. Venues.** Two workshop pages, read for their programs. NeurIPS
  2026, "AgenticOS: Co-designing Systems and ML Foundations of an OS
  Layer for Agentic AI", Fri, Dec 11, 2026; it lists S10, A8 and S18.
  https://neurips.cc/virtual/2026/workshop/137493. "AgenticOS @ SOSP
  2026 | 2nd Workshop on OS Design for AI Agents", September 29, 2026,
  Congress Hotel Prague; its program lists O3, O8 and "Isolation in the
  Age of Agents" (Anjali, Michael Swift), which was not read.
  https://os-for-agent.github.io/. Both accessed 2026-11-20.

## (a) 4. Memory benchmarks

- **B1. LoCoMo (background).** "Evaluating Very Long-Term Conversational
  Memory of LLM Agents". Adyasha Maharana, Dong-Ho Lee, Sergey Tulyakov,
  Mohit Bansal, Francesco Barbieri, Yuwei Fang. arXiv:2402.17753, v1 27
  Feb 2024, cs.CL; no venue on the page.
  https://arxiv.org/abs/2402.17753. Accessed 2026-11-20. Read: abstract.
  First posted in 2024: background.

  Does: very long conversations, "each encompassing 300 turns and 9K
  tokens on avg., over up to 35 sessions", with question answering,
  event summarization and multimodal dialogue tasks. Differs: one user's
  conversation with one memory; no agents that share, no access,
  deletion or ordering. S7, S14 and O7 report on it.

- **B2. LongMemEval (background).** "LongMemEval: Benchmarking Chat
  Assistants on Long-Term Interactive Memory". Di Wu, Hongwei Wang,
  Wenhao Yu, Yuwei Zhang, Kai-Wei Chang, Dong Yu. arXiv:2410.10813, v1
  14 Oct 2024, v2 4 Mar 2025, cs.CL; comments: "ICLR 2025".
  https://arxiv.org/abs/2410.10813. Accessed 2026-11-20. Read: abstract.
  First posted in 2024: background.

  Does: "five core long-term memory abilities of chat assistants:
  information extraction, multi-session reasoning, temporal reasoning,
  knowledge updates, and abstention", with "500 meticulously curated
  questions"; commercial assistants and long-context models show "a 30%
  accuracy drop on memorizing information across sustained
  interactions". Differs: single user, single assistant. Knowledge
  updates are the nearest to our recency probe; nothing on sharing,
  privacy or deletion.

- **B3. MemoryAgentBench.** "Evaluating Memory in LLM Agents via
  Incremental Multi-Turn Interactions". Yuanzhe Hu, Yu Wang, Julian
  McAuley. arXiv:2507.05257, v1 7 Jul 2025, v4 28 Jun 2026, cs.CL;
  comments: "Y. Hu and Y. Wang contribute equally".
  https://arxiv.org/abs/2507.05257. Accessed 2026-11-20. Read: abstract.

  Does: four competencies, "accurate retrieval, test-time learning,
  long-range understanding, and selective forgetting"; "no existing
  benchmarks cover all four competencies"; "current methods fall short
  of mastering all four competencies". Differs: one agent's memory. Its
  selective forgetting is about the agent's own updating, not a user's
  request to delete across agents.

- **B4. MemoryArena.** "MemoryArena: Benchmarking Agent Memory in
  Interdependent Multi-Session Agentic Tasks". Zexue He, Yu Wang, Churan
  Zhi, Yuanzhe Hu, Tzu-Ping Chen, Lang Yin, Ze Chen, Tong Arthur Wu,
  Siru Ouyang, Zihan Wang, Jiaxin Pei, Julian McAuley, Yejin Choi, Alex
  Pentland. arXiv:2602.16313, v1 18 Feb 2026, v2 17 Sep 2026, cs.CL;
  comments: "ICML 2026". https://arxiv.org/abs/2602.16313. Accessed
  2026-11-20. Read: abstract.

  Does: "Existing evaluations of agents with memory typically assess
  memorization and action in isolation." Tasks with interdependent
  subtasks across sessions, in web navigation, preference-constrained
  planning, progressive search and formal reasoning; "agents with
  near-saturated performance on existing long-context memory benchmarks
  like LoCoMo perform poorly in our agentic setting". No numbers in the
  abstract. Differs: one agent that learns from its own past; no sharing
  between agents or users.

- **B5. StateMemBench.** "Can Agent Memory Systems Track Evolving
  State?". Xinyi Fan, Miri Liu, Ruozhen Yang, Siru Ouyang, Jiawei Han.
  arXiv:2608.19652, v1 20 Aug 2026, cs.AI; no venue on the page.
  https://arxiv.org/abs/2608.19652. Accessed 2026-11-20. Read: abstract.

  Does: "234 multi-session scenarios"; "Its closed-pool grading scores
  whether an answer reflects the current state, the superseded state, or
  fails otherwise". Its method, StateMem, "improves current-state
  accuracy over the strongest same-backbone baseline by 1.8x (0.205 ->
  0.363) on DeepSeek-V4-Flash"; as a wrapper it lifts current-state
  accuracy "by +32 to +67 points on StateMemBench across six memory and
  retrieval backends". Differs: supersession for one user's memory,
  measured by answers. Close to our recency and contradiction probes
  (`BENCHMARK_V2.md:187-194`); no multiple writers or access control.

- **B6. GateMem.** "GateMem: Benchmarking Memory Governance in
  Multi-Principal Shared-Memory Agents". Zhe Ren, Yibo Yang, Yimeng
  Chen, Zijun Zhao, Benshuo Fu, Zhihao Shu, Bingjie Zhang, Yangyang Xu,
  Dandan Guo, Shuicheng Yan. arXiv:2606.18829, v1 17 Jun 2026, cs.LG;
  comments: "24 pages, 8 figures". https://arxiv.org/abs/2606.18829 and
  https://arxiv.org/html/2606.18829v1. Accessed 2026-11-20. Read:
  abstract; full text (HTML v1), searched.

  Does: "multiple principals write to a common memory pool and query it
  under different roles, scopes, and relationships". It jointly scores
  utility, access control and "agent-facing active forgetting after
  explicit deletion requests" over "91 long-form multi-party episodes
  and 2,218 hidden checkpoints". Baselines include RAG-Policy, which
  "augments retrieval with requester and access-policy metadata", and
  A-Mem and Mem0 configurations. Reported: "no method simultaneously
  achieves strong utility, robust access control, and reliable
  forgetting"; even long-context prompting shows leakage "sometimes
  exceeding 20% in access-control or active-forgetting failures". Its
  forgetting is "an interface-level criterion; GateMem does not certify
  physical erasure from internal databases, vector indexes, caches,
  summaries, or model parameters." Differs: the principals are people
  writing to one assistant, not several agents; the store is pooled by
  design. The nearest benchmark to our privacy and deletion probes. Our
  deletion check reads the store as well as the answer
  (`DELETION_AND_SUPERSESSION.md:102-106`).

- **B7. PiSAs.** "PiSAs: Benchmarking Contextual Integrity in Multi-User
  Agentic Systems". Shubham Gupta, Nazanin Mohammadi Sepahvand, Abhinav
  Kumar, Cem Subakan, Spandana Gella, Pierre-André Noël, Perouz
  Taslakian, Eugene Bagdasarian, Valentina Zantedeschi.
  arXiv:2607.05318, v1 6 Jul 2026, v2 19 Oct 2026, cs.MA; no venue on
  the page. https://arxiv.org/abs/2607.05318. Accessed 2026-11-20. Read:
  abstract.

  Does: information may leak "internally across users through
  inter-agent messages, shared memory and user-agent interactions"; each
  item has "dual CI annotations: whether a piece of information is
  appropriate for the task, and which users may legitimately access it".
  Finding: "results are bottlenecked by incorrect LLM judgment calls".
  No numbers in the abstract. Differs: it measures what models decide to
  pass on; our layer removes that decision from the model for the user
  partition and visibility. Close to our privacy probe and
  `cross_user_rows`.

- **B8. CoMemBench.** "CoMemBench: Benchmarking Collaborative Memory
  Boundaries across Multi-Agent Workflow Topologies". Sen Zhao, Ruiqi
  Kong, Zuyu Zhang, Lifeng Shen, Xinyu He, Ding Zou, Xu Zhang, Qinghua
  Zhang. arXiv:2609.32192, v1 26 Sep 2026, v2 29 Sep 2026, cs.AI; no
  venue on the page. https://arxiv.org/abs/2609.32192. Accessed
  2026-11-20. Read: abstract.

  Does: "It constructs 800 composite workflows across four domains",
  scoring completion, handoff reliability, "isolation robustness" and
  token cost. Finding: "broader context improves information
  availability but can weaken isolation". Differs: isolation of task
  artifacts by workflow topology inside one task, not of a user's
  long-term memory between agents. The same sharing-against-isolation
  tension as our visibility rule.

- **B9. Correlated Promotion Benchmark.** "A Benchmark and Diagnostic
  Study of Epistemic Admission in Shared Agent Memory". Xiaoyang Li,
  Yiqi Wang, Chencheng Zhu, KE XU, Wencheng Yang, Zequn Sun, Pingan
  Song, Yiqun Duan, Taotao Cai. arXiv:2609.30813, v1 25 Sep 2026, cs.AI;
  comments: "preprint". https://arxiv.org/abs/2609.30813. Accessed
  2026-11-20. Read: abstract.

  Does: whether claims should be admitted to a store that agent teams
  share, given that "repeated claims may be mistaken for independent
  evidence". Eight admission policies over four agent families: "Gating
  on declared source type reduces false adoption to 0.06--0.09, compared
  with 0.22--0.47 for other answering policies. Once an uncontested
  false belief enters memory, the consumer asserts it in 0.97--0.99 of
  probes across all families." Differs: admission by truth and source
  lineage, not by owner or user. Its consumer setting matches ours (one
  consumer answers from what writers stored).

- **B10. Bemula.** "Can Agents Forget When Asked? A Benchmark for Memory
  Unlearning in LLM Agents". Bofan Xie, Chaokun Wang, Guanchen Ge,
  Songyao Wang, Fang Niu, Hang Zhang, Wei Wang. arXiv:2610.18052, v1 13
  Oct 2026, cs.AI; no venue on the page.
  https://arxiv.org/abs/2610.18052. Accessed 2026-11-20. Read: abstract.

  Does: "50 multi-session dialogue instances, 135 forget requests of six
  types, and 1,742 test questions"; "Each dialogue has a control version
  without the requests, so that only systems that have stored the target
  can earn credit for forgetting." Six memory systems under three
  backbones: "no system passes more than 1.5% of forget requests end to
  end, and most pass none at all." Differs: one user, one agent;
  deletion by request, scored by answers and attacks. Our deletion
  involves several writers' rows and is checked in the store. An
  instance in part (b), condition 8.

- **B11. MemCut.** "MemCut: Every Secret Leaves a Trail in the Long-Term
  Memory of LLM Agents". Cheng Zhang, Xuanning Cao, Zhicheng Zheng, Hui
  Xiong. arXiv:2610.21405, v1 15 Oct 2026, cs.AI; comments: "17 pages, 4
  figures, 13 tables, including appendices".
  https://arxiv.org/abs/2610.21405. Accessed 2026-11-20. Read: abstract.

  Does: "456 hand-designed secrets in long-horizon conversations have
  fully annotated evidence trails to test recovery after deletion,
  including from messages that never state the secrets directly." Two
  metrics: "Native recovery measures reader success through the system's
  retrieval, whereas residual recovery measures the same reader's
  success when directly given surviving objects traced to annotated
  disclosures or evidence." Reported: "LLM-guided deletion of ten
  additional turns from twenty retrieval candidates leaves 39-76%
  residual recovery." Differs: residual recovery is our "carrier" notion
  taken further, to evidence that implies a fact without stating it; our
  matcher finds stated values and aliases only. Single user. An instance
  in part (b), condition 8.

- **B12. MemLeak, multimodal.** "MemLeak: Diagnosing Information Leaks
  in Multimodal Agent Memory". Kuan Wang, Chao Zhang. arXiv:2606.29788,
  v1 29 Jun 2026, cs.LG; comments: "23 pages, 3 figures, includes
  appendix". https://arxiv.org/abs/2606.29788. Accessed 2026-11-20.
  Read: abstract.

  Does: "When a multimodal AI agent is asked to forget a fact, current
  memory systems usually delete the text entry and report success."
  Reported: "retained correlated text enables 18.3% recovery, and
  retained images enable 12.0% recovery (0.0% blind baseline, 0.3%
  FPR)"; "Content-aware semantic deletion reduces the image residual to
  2.0%." Differs: carriers in other modalities; ours are text only.
  Single user. An instance in part (b), condition 8.

Part (b) and the closing sections follow in the next commit.
