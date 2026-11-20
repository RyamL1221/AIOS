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

- **Access date.** Every URL below was fetched on 2026-11-20, except the
  links marked "not fetched". Each entry repeats the date. A "requested"
  URL redirected to the "served" one.

- **How a source was read.** arXiv pages were downloaded and read as
  text: the abstract page for the title, authors, versions, comments and
  abstract, and the HTML full text where an entry says so, searched for
  the passages quoted. GitHub issues, pull requests and advisories were
  read through GitHub's public REST API (an issue and its comments as
  JSON) and are cited by their page URL; one discussion was read as its
  page, and repository files through raw.githubusercontent.com. Other
  pages were downloaded and read as text. A translation from Chinese is
  marked "translated here" and is not a quote. A quote is verbatim from
  that text, with four exceptions: Markdown emphasis and links in an
  issue are dropped, curly quotation marks are written straight, the
  comment markers of a source file are dropped, and "[...]" marks a cut.
  Passages whose math the HTML renders badly are paraphrased, not
  quoted.

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
  Where a page shows no date but its own metadata gives one (schema.org
  `dateModified`), the entry says "page metadata: modified" and the
  date.

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
| 3 | Session-bound identity: for a request that carries a kernel session token, the user comes from the session; otherwise from the agent's claim, canonicalized | `STRESS_DIMENSIONS.md:387-402`, `aios/memory/manager.py:406-409` |
| 4 | Write-before-read ordering across writers: one barrier for every agent | `REPLICATED_LOGIC.md:72-79`, `STRESS_DIMENSIONS.md:266-273` |
| 5 | Deletion with tombstones: a forget removes every carrier of the fact, whoever wrote it, and a tombstone guards later reads | `DELETION_AND_SUPERSESSION.md:102-106`, `:160-182` |
| 6 | Supersession: a later statement retires the earlier rows of its slot | `DELETION_AND_SUPERSESSION.md:107-109` |
| 7 | Write quota per writer, user and session | `STRESS_DIMENSIONS.md:477-493` |

Three loci are compared: the kernel; the same library replicated in each
agent (`REPLICATED_LOGIC.md:67-88`); each backend used natively, the way
its documentation says (`NATIVE_USAGE.md:3-10`, `:62-69`).

**What no source below does, as far as read.** None compares one policy
layer with the same logic replicated in each agent. The nearest are one
live service measured with no comparand (S1); one architecture argued
without experiments (O2); one method compared with a centralized
baseline, for the currency of plans, not for memory policy (S12); one
benchmark that varies the topology (a coordinator or peer to peer) and
the memory regime (private per agent, shared, hybrid), where what is
shared is the model's judgment under privacy instructions, not a fixed
rule (B7); one study that compares enforcement outside the model with
the same rule given to each agent as an instruction, for tools, not
memory (A17); and one guard between the agent and any backend, compared
with a filter at the store, for revoked facts (B13). See "Not found".

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
  0.975 [0.929, 0.991]; cross-fleet leaks 0 of 80, 0.000 [0.000, 0.046];
  on 8 dedicated facts under strong write mode, a write-to-visible
  window of median 0.83 s and at most 1.97 s, which S1 reads as one
  search round-trip: "all 8 facts surfaced on the poller's first search
  after the write" (§8.3), and the window is "effectively zero [...] not
  as a post-write read-visibility lag" (§9.4). The cost shows as write
  latency: p50 1,840 ms, p95 4,861 ms and p99 19,319 ms over the 194
  writes that completed (§8.4). Reported in §8.4: supersession in 90 of
  90 fact-runs where both contradictory writes were admitted, 1.000
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
  "delet", "forget", "tombstone", "quota" or "flood". The service's own
  repository (caura-ai/caura-memclaw; S1's authors give Caura.ai as
  their affiliation) documents two differences from our kernel: each
  agent keeps its own retrieval defaults (`caura_tune`), where our
  kernel applies its own, and its delete is a soft delete (part (b),
  conditions 4 and 8).

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
  internal agents. The abstract reports QA benchmarks (it names LoCoMo,
  LongMemEval-S and document QA) and agent-task benchmarks for
  procedural memory (ALFWorld, WebShop and MetaClaw-Bench, where it
  "reaches 49.2% on MetaClaw-Bench, against 44.0% for MetaClaw's skill
  library"); none, as described, has several application agents sharing
  memory.

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
  their rollback. The abstract claims "per-step serializability" among
  the writing agents; it does not discuss a reader that is not one of
  them, users or visibility.

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
  No persistent store, users or policy layer. It measures whether a
  conflict between two statements is surfaced across a delegation. Our
  contradiction probe instead requires the later writer's statement to
  win (`BENCHMARK_V2.md:237-238`), so the two treat a reported conflict
  in opposite ways.

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

- **S17. Letta, shared memory: the legacy block design and the current
  repositories (vendor documentation).** Letta Docs, "Shared memory",
  the legacy page. No date on the page; it covers "Letta's legacy v1
  API". Requested
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
  on memory blocks anymore. Use shared memory repositories for new work,
  and make a best effort to migrate agents to MemFS." Differs (legacy
  blocks): sharing is attachment. Every attached agent reads the whole
  block: no rule per row, no user partition inside a block, no ordering
  beyond what each edit tool does.

  The current design, on the page the legacy one links: Letta Docs,
  "Shared memory", https://docs.letta.com/concepts/shared-memory, read
  as its page and its `index.md` copy. No date on the page. Accessed
  2026-11-20. "Each shared memory repository is a Git repository hosted
  in Letta Cloud and owned by your organization."; "Older Letta API
  guides use shared memory blocks [...] users should migrate to shared
  memory repositories instead."; "The agent must commit and push its
  changes. Other agents can then pull those commits into their own
  checkouts." Differs (repositories): sharing is a Git repository
  attached to agents of one organization. Another agent's write reaches
  a reader after the writer pushes and the reader pulls, so what a read
  sees rests on each agent's commits and syncs; as read, no rule per row
  and no user partition inside a repository. An instance in part (b),
  condition 5.

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

- **S19. MAP-Graph.** "MAP-Graph: Provenance-Aware Shared Memory for
  Multi-Agent Workflows". Yiqi Wang, Zihao Yan, Jiaqi Zhang, Zhangkai
  Wu, Mingkai Zheng, Zequn Sun, Yanming Zhu, Taotao Cai.
  arXiv:2608.10509, v1 11 Aug 2026, cs.AI; no venue on the page.
  https://arxiv.org/abs/2608.10509. Accessed 2026-11-20. Read: abstract.

  Does: "a provenance-aware memory layer that represents agents,
  sources, memories, claims, and actions in a typed execution graph. It
  traces ancestry, excludes permission-ineligible records, reranks
  eligible memories by semantic similarity and multiplicative path
  trust, and applies a risk-sensitive gate before action execution".
  Reported on 2,700 synthetic tasks per method across three domains:
  94.96% overall task success and 72.70% exact decision accuracy;
  "Ablations isolate the roles of permission filtering, path trust, and
  action gating". Differs: one layer that drops records an agent may not
  see before ranking, as our visibility rule does before selection; its
  permissions follow provenance through derived records such as
  summaries, where ours read the owner and sharing fields of each row.
  The abstract names no users, ordering across writers, deletion or
  quota.

- **S20. MAPLE-Guard.** "MAPLE-Guard: Memory-Aware Link Enforcement
  Against Memory-Link Poisoning in Multi-Agent Systems". Wenjun Xiong,
  Yijin Zhou, Jiaqian Wang, Shangding Gu, Bo Tang, Zhiyu Li, Feiyu
  Xiong, Ying Wen, Muning Wen. arXiv:2608.00426, v1 1 Aug 2026, v2 3 Oct
  2026, cs.MA; comments: "27 pages, 14 figures, 9 tables. Includes
  examples that may be misleading or harmful. Code: this https URL".
  https://arxiv.org/abs/2608.00426. Accessed 2026-11-20. Read: abstract.

  Does: against poisoning, where "a poisoned memory can be written once,
  continuously retrieved in later tasks, promoted into shared memory,
  and reused by other agents", it "places gates at write, retrieval,
  promotion, and cross-agent reuse". Reported: attack success "from
  38.2% to 0.9% on LongMemEval and from 34.7% to 0.2% on AppWorld".
  Differs: gates at the points where our layer acts (write, retrieval,
  sharing between agents), deciding on content risk; ours decide on
  owner, user, session, write count and forgotten values.

- **S21. Concurrency anomalies.** "Verified Detection and Prevention of
  Concurrency Anomalies in Multi-Agent Large Language Model Systems".
  Sajjad Khan (also the author of S8). arXiv:2606.17182, v1 15 Jun 2026,
  cs.LG; comments: "32 pages, 2 figures, 6 tables. Verus/TLA+
  verification artifact, reference Rust runtime, and Python harnesses,
  plus a supplementary appendix (Sections A-F, Tables S1-S6), included
  as ancillary files". https://arxiv.org/abs/2606.17182 and
  https://arxiv.org/html/2606.17182v1. Accessed 2026-11-20. Read:
  abstract; of the full text, §III-A and the deer-flow passages (§I-A,
  §VI-E).

  Does: "Multi-agent LLM systems share state through memory stores,
  vector indices, and tool registries." It formalizes "four concurrency
  anomalies in TLA+: stale-generation, phantom-tool, causal-cascade, and
  tool-effect reordering" and verifies detectors and runtimes against
  them; "We reproduce a silent lost update in ByteDance's deer-flow".
  Its stale-generation anomaly (§III-A, Definition 1, paraphrased: the
  HTML renders its math badly): agent A reads a cell; while A is
  generating, agent B writes a new value to the cell; A then commits on
  the value it read. Differs: anomalies of read-generate-write
  operations on shared state. Its stale-generation is a read made stale
  by another agent's write after it; ours is a read that misses a write
  accepted before it. No users, visibility or deletion in the abstract.
  The deer-flow lost update is an instance in part (b), condition 5.

- **S22. CAMA.** "Beyond Memory Majority: Latent-Source Reasoning for
  Multi-Agent Memory Arbitration". Chenchen Lin, Wenhao Yuan, Xuehe
  Wang, Edith Cheuk Han Ngai. arXiv:2608.19701, v1 20 Aug 2026, cs.AI;
  no venue on the page. https://arxiv.org/abs/2608.19701. Accessed
  2026-11-20. Read: abstract.

  Does: "memories written by different agents may inherit the same
  upstream source or shared bias, causing correlated evidence to be
  repeatedly counted and creating a false majority" ("Memory Correlation
  Bias"); CAMA estimates "the effective number of independent evidence
  sources" and retrieves alternative evidence before deciding. No
  numbers in the abstract. Differs: how a consumer weighs several
  agents' memories of one fact, by their sources. Our selector does not
  weigh agreement; under supersession it keeps the latest statement of a
  slot (responsibility 6). The same concern as B9.

- **S23. LEGOMem.** "LEGOMem: Modular Procedural Memory for Multi-agent
  LLM Systems for Workflow Automation". Dongge Han, Camille Couturier,
  Daniel Madrigal Diaz, Xuchao Zhang, Victor Rühle, Saravan Rajmohan.
  arXiv:2510.04851, v1 6 Oct 2025, cs.AI; no venue on the page.
  https://arxiv.org/abs/2510.04851. Accessed 2026-11-20. Read: abstract.

  Does: splits past task trajectories into memory units allocated
  "across orchestrators and task agents", "examining where memory should
  be placed, how it should be retrieved, and which agents benefit most";
  on OfficeBench, "orchestrator memory is critical for effective task
  decomposition and delegation, while fine-grained agent memory improves
  execution accuracy". Differs: where procedural memory sits between an
  orchestrator and its agents, for task success; our placement question
  is where the policy over a user's memory runs. No users, privacy or
  deletion in the abstract.

- **S24. CrewAI, crew memory (vendor documentation).** CrewAI Docs,
  "Memory". Requested https://docs.crewai.com/en/concepts/memory, served
  at https://docs.crewai.com/v1.15.44/en/concepts/memory; read as its
  page and its Markdown copy. No date shown; page metadata: modified
  2026-11-19. Accessed 2026-11-20. Read: the page.

  Does: "All agents in the crew share the crew's memory unless an agent
  has its own."; "Agents can use the crew's shared memory (default) or
  receive a scoped view for private context." A memory can be marked
  private: "Private memories are only visible to recall when the
  `source` matches", and a recall with `include_private=True` carries
  the comment "Admin access: see all private records regardless of
  source". "When you call `remember()` without specifying a scope, the
  LLM analyzes the content and the existing scope tree, then suggests
  the best placement." The page offers private memories for "multi-user
  or enterprise deployments where different users' memories should be
  isolated." Differs: isolation is keyed on a `source` string the caller
  passes at recall, and one argument of a recall lifts it; where a
  memory without a scope goes is an LLM's choice. Ours keys the
  partition on the user id and visibility on the owner and sharing
  fields of each row (responsibilities 1 to 3).

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
  Differs: several users' personal agents over one shared store
  ("Personal AI agents in enterprise multi-tenant deployments share a
  common vector store for long-term memory"), with and without an
  ownership gate; not several agents of one user, and no rule between
  agents in the abstract. Its winning mitigation is the check our user
  partition makes after retrieval. An instance in part (b), condition 7.

- **A10. Mem0, entity-scoped memory (vendor documentation).** Mem0 Docs,
  "Entity-Scoped Memory". No date shown; page metadata: modified
  2026-08-03.
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
  "Isolate store data per user - Docs by LangChain". No date shown; page
  metadata: modified 2026-11-16.
  https://docs.langchain.com/langsmith/store-auth. Accessed 2026-11-20.
  Read: the page.

  Does: "By default, store namespaces are shared across all callers."
  "Store isolation requires a @auth.on.store handler." The handler
  "either validates that the namespace starts with that identity, or
  rewrites the namespace to prepend it." Differs: isolation is opt-in,
  written by the deployer as an authorization hook on the server. Ours
  partitions by the claimed user id by default; binding the id to an
  authenticated session needs the deployment to open kernel sessions
  (`STRESS_DIMENSIONS.md:387-402`), as LangSmith's isolation needs the
  deployer's handler. One rule per deployment on the server, as ours,
  but for users only, not visibility between agents.

- **A13. Graphiti, graph namespacing (vendor documentation).** Zep
  Documentation, Graphiti, "Graph Namespacing". No date shown; page
  metadata: modified 2026-09-23.
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
  when the request carries a session token (responsibility 3).

- **A14. MEXTRA.** "Unveiling Privacy Risks in LLM Agent Memory". Bo
  Wang, Weiyi He, Shenglai Zeng, Zhen Xiang, Yue Xing, Jiliang Tang,
  Pengfei He. arXiv:2502.13172, v1 17 Feb 2025, v2 3 Jun 2025, cs.CR;
  comments: "ACL 2025 (Main Conference)".
  https://arxiv.org/abs/2502.13172 and
  https://arxiv.org/html/2502.13172v2. Accessed 2026-11-20. Read:
  abstract; full text (HTML v2), §2.2 and the Limitation section.

  Does: a black-box Memory EXTRaction Attack on agents that store
  "private user-agent interactions in the memory module for
  demonstrations", tested on two agents. The attacker's goal is to
  extract as many past user queries from memory as possible (§2.2,
  paraphrased: the passage holds math). Its Limitation section: "the
  agent framework we consider does not incorporate session control:
  multiple users may share the same session, causing the memory module
  to store historical records from all users. Introducing user-level and
  session-level memory isolation would limit attackers' access to
  private data and mitigate the impact of memory extraction. However,
  since there is no standard method for integrating session control into
  agent frameworks, we leave its exploration for future work." Differs:
  one agent's memory pooled across users and attacked through queries.
  The mitigation it names and leaves untested, user-level and
  session-level isolation, corresponds to our responsibilities 1 and 3.
  An instance in part (b), condition 7.

- **A15. SPORE.** "Isolated but Exposed: Persistence-Based Memory
  Extraction Attack on LLM Agents". Xinyu Gao, Wenyu Chen, Xiangtao
  Meng, Li Wang, Chuanchao Zang, Jianing Wang, Zheng Li, Shanqing Guo.
  arXiv:2607.23444, v1 26 Jul 2026, cs.CR; no venue on the page.
  https://arxiv.org/abs/2607.23444. Accessed 2026-11-20. Read: abstract.

  Does: "Production systems mitigate extraction risks through memory
  isolation, binding each user's LTM to a unique identifier." A
  malicious tool reads memory that agents "embed [...] in tool
  invocation parameters", "without violating user-level isolation".
  Reported: "SPORE achieves an 80.0% record extraction rate with
  unlimited triggers and 47.0% with only 20 triggers." Its conclusion:
  "memory isolation alone is insufficient". Differs: the channel, tool
  parameters, lies outside what our layer controls; the user partition
  holds and the data leaves through the agent's tool calls.

- **A16. Microsoft Foundry Agent Service, memory scope (vendor
  documentation).** Microsoft Learn, "Create and use memory in Foundry
  Agent Service", last updated 2026-10-06,
  https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage;
  and "What is Memory?", last updated 2026-06-02,
  https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory.
  Accessed 2026-11-20. Read: both pages.

  Does: with the memory search tool, "set scope to {{$userId}} to enable
  per-user memory isolation without hard-coding identifiers". The user
  then comes from a header or from authentication: "x-memory-user-id
  request header: If present, the header value is used as the user ID.
  Use this in proxy or backend scenarios where your service calls the
  API on behalf of an end user."; "If the header isn't set, the system
  falls back to the caller's tenant ID (TID) and object ID (OID)."
  Elsewhere the caller sets it: "For low-level memory APIs, you must set
  scope explicitly in each request. Automatic scope resolution from the
  caller's identity is only supported when you use the memory search
  tool with scope set to {{$userId}}." The best practices say "Use the
  scope property to partition the memory store by user." Quotas include
  "Maximum memories per scope: 10,000". Differs: by default the scope
  comes from authentication, as our session binding; a header the
  backend sets overrides it, and the low-level APIs take it from the
  caller, as our claim path does. As read, no rule between agents of one
  user.

- **A17. Prompts Don't Protect.** "Prompts Don't Protect: Architectural
  Enforcement via MCP Proxy for LLM Tool Access Control". Rohith Uppala.
  arXiv:2605.18414, v1 18 May 2026, v3 27 Aug 2026, cs.CR; comments: "7
  pages, 4 tables, 2 figures. Camera-ready version accepted to the EMNLP
  2026 Industry Track; adds benign-utility and abstention evaluation,
  latency percentiles, and revised limitations".
  https://arxiv.org/abs/2605.18414. Accessed 2026-11-20. Read: abstract.

  Does: "when unauthorized tools are visible in an agent's context,
  models select them in 48-68% of adversarial scenarios, even when
  explicitly instructed not to"; "explicit per-tool allowlists reduce
  violations to as low as 4.0% but never to zero"; a proxy "filters tool
  registries at discovery time. Because unauthorized tools never reach
  the model context, UIR is 0% by design". Differs: tools, not memory.
  It compares enforcement outside the model with the same rule given to
  each agent as an instruction; ours compares one enforcement point with
  the same code run in each agent.

## (a) 3. Agent operating systems

- **O1. AIOS (background).** "AIOS: LLM Agent Operating System". Kai
  Mei, Xi Zhu, Wujiang Xu, Wenyue Hua, Mingyu Jin, Zelong Li, Shuyuan
  Xu, Ruosong Ye, Yingqiang Ge, Yongfeng Zhang. arXiv:2403.16971, v1 25
  Mar 2024, v5 12 Aug 2025, cs.OS; comments: "Published as a full paper
  at COLM 2025". https://arxiv.org/abs/2403.16971 and
  https://arxiv.org/html/2403.16971v5. Accessed 2026-11-20. Read:
  abstract; full text (HTML v5), §3.5, §3.8, A.5 and A.8. First posted
  in 2024: background.

  Does: "isolating resources and LLM-specific services from agent
  applications into an AIOS kernel", which provides "fundamental
  services (e.g., scheduling, context management, memory management,
  storage management, access control)". Reported: "up to 2.1x faster
  execution for serving agents built by various agent frameworks". Its
  access manager "assigns each agent to a specific privilege group" and
  validates requests against it, "ensuring agents can only access
  resources of other agents within their shared privilege domain"
  (§3.8); its interface has `check_access(self, sid, tid)`, which
  "Checks if the source agent is in the target agent's priviledge group"
  (A.8, the source's spelling). Its memory manager keeps each agent's
  memory in a memory block and evicts items to storage past a limit, by
  LRU-K (§3.5, Figure 5), for "transient session-specific data that
  clears when agent sessions end" (A.5). Differs: the system ours is
  built on. Its kernel checks access between agents by privilege group,
  agent to agent and per resource, and keeps a memory block per agent.
  As read, it has no user partition, no sharing policy per row, no
  identity binding, no ordering across writers, no deletion of carriers
  and no write quota (the block limit is a capacity limit).

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
  https://arxiv.org/abs/2507.03724 and
  https://arxiv.org/html/2507.03724v4. Accessed 2026-11-20. Read:
  abstract; full text (HTML v4), §5.4.2 and §5.5.1-5.5.2 read, §6
  searched.

  Does: "we propose MemOS, a memory operating system that treats memory
  as a manageable system resource", unifying plaintext, activation and
  parameter memories; "a MemCube encapsulates both memory content and
  metadata such as provenance and versioning." A central module,
  MemGovernance, "establishes a ternary permission model involving the
  user identity, the memory object, and the calling context, supporting
  private, shared, and read-only access policies", and "Each memory
  request undergoes identity authentication and contextual validation to
  prevent unauthorized access" (§5.5.1). MemVault keeps "namespaces such
  as user-private stores, expert knowledge bases, industry-shared
  repositories" (§5.5.2). The scheduler's dispatch is "governed by
  MemGovernance, which enforces user-role boundaries, rate limits, and
  lifecycle policies" (§5.4.2). Differs: our placement, one module that
  every memory request passes, naming visibility, identity
  authentication and a rate limit. As read, §5 describes these only in
  the sentences quoted; nothing found on ordering a read after other
  writers' writes or on a delete that removes every carrier of a fact.
  §6, the evaluation, has no occurrence of "permission", "access
  control", "MemGovernance", "governance", "privacy", "private" or
  "shared": it evaluates none of the governance. Its tracker's deletion
  bug is an instance in part (b), condition 8.

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

- **O9. Venues.** Three workshop pages, read for their programs. NeurIPS
  2026, "AgenticOS: Co-designing Systems and ML Foundations of an OS
  Layer for Agentic AI", Fri, Dec 11, 2026; it lists S10, A8 and S18.
  https://neurips.cc/virtual/2026/workshop/137493. "AgenticOS @ SOSP
  2026 | 2nd Workshop on OS Design for AI Agents", September 29, 2026,
  Congress Hotel Prague; its program lists O3, O8 and "Isolation in the
  Age of Agents" (Anjali, Michael Swift), which was not read.
  https://os-for-agent.github.io/. That page names "Previous edition:
  ASPLOS 2026": "The 1st Workshop on Operating Systems Design for AI
  Agents", March 23, 2026, Pittsburgh, USA; no paper title on its
  program is about memory.
  https://os-for-agent.github.io/asplos-2026.html. All three accessed
  2026-11-20.

- **O10. Cerebrum, the AIOS SDK (background to our setup).** "Cerebrum
  (AIOS SDK): A Platform for Agent Development, Deployment,
  Distribution, and Discovery". Balaji Rama, Kai Mei, Yongfeng Zhang.
  arXiv:2503.11444, v1 14 Mar 2025, cs.MA; comments: "Accepted to the
  2025 Annual Conference of the North American Chapter of the
  Association for Computational Linguistics (NAACL) - System
  Demonstration Track". https://arxiv.org/abs/2503.11444. Accessed
  2026-11-20. Read: abstract.

  Does: "a comprehensive SDK featuring a modular four-layer architecture
  for agent development, encompassing LLM, memory, storage, and tool
  management", with an Agent Hub and a web interface. Differs: the SDK
  through which our agents send their memory requests to the kernel; it
  describes an interface, not a policy over memory several agents share.

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
  the page. https://arxiv.org/abs/2607.05318 and
  https://arxiv.org/html/2607.05318v2. Accessed 2026-11-20. Read:
  abstract; full text (HTML v2), §1, §4.2 and §5.2.

  Does: information may leak "internally across users through
  inter-agent messages, shared memory and user-agent interactions"; each
  item has "dual CI annotations: whether a piece of information is
  appropriate for the task, and which users may legitimately access it".
  Finding: "results are bottlenecked by incorrect LLM judgment calls".
  The full text evaluates "three agentic system topologies: a single
  agent with access to all data, a centralized multi-agent system in
  which all communication routes through a coordinator, and a
  decentralized peer-to-peer system", under "three memory regimes:
  private per-agent memory, shared memory, and hybrid" (§1). Private
  memory is "readable and writable only by that agent"; shared memory
  has "universal read and write access"; hybrid tests "whether the
  backbone can tell what belongs in which" (§4.2). Reported in §5.2
  (paraphrased, the HTML renders the numbers as math): total visibility
  violations rise from 14.9 to 28.0% without memory to 35.6 to 50.0%
  with hybrid memory. Differs: it measures what models decide to pass
  on, under privacy instructions in the prompt; our layer removes that
  decision from the model for the user partition and visibility. Its
  centralized topology routes messages through a coordinator; it does
  not move a memory policy into one place. Close to our privacy probe
  and `cross_user_rows`.

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

- **B13. Revocation enforcement.** "Revoked but Still Authoritative: An
  Empirical Study of Revocation Enforcement in Agent-Memory Systems". Yi
  Ting Shen, Kentaroh Toyoda, Alex Leung. arXiv:2609.08258, v1 8 Sep
  2026, cs.AI; comments: "Code is available at this https URL".
  https://arxiv.org/abs/2609.08258 and
  https://arxiv.org/html/2609.08258v1. Accessed 2026-11-20. Read:
  abstract; full text (HTML v1), §1, §3.3, §4.1, §4.2 and §5.2 read, the
  rest searched.

  Does: loads five memory systems, "Graphiti and Zep [9], which share
  one engine, mem0 [2], langmem [6] and cognee [13]" (§1), with a
  revoked policy and its replacement, and measures whether the revoked
  fact is returned and acted on, over nine scenarios and nine models,
  under five defense conditions and a no-defense baseline. Abstract: "no
  system enforces revocation by default: the revoked fact is returned
  wherever the revocation label is visible to the retrieval layer,
  outranks its replacement, and leads agents to the unsafe action." §4.1
  (numbers paraphrased: the HTML sets them as math): on both exposed
  systems the revoked fact was returned in every scenario, 81 of 81
  each, and "ranked above the policy that replaced it"; it led agents to
  the unsafe action in 358 of 810 trials on Graphiti (44.2%) and 341 of
  810 on "mem0 (exp.)" (42.1%). "mem0 (exp.)" is "mem0 with the
  expiry-flag override enabled": by default mem0 "filters it at read
  time", "the shipped filter we disable in mem0 (exp.)" (§4.1). Under
  "the store-level filter" no unsafe action occurred (0 of 1,620). It
  proposes "a guard that sits between the agent and any memory backend
  and withholds records that are revoked or conflict with their
  replacement"; where the store exposes a mark, the guard "matches the
  store-level filter" (§5.2). Differs: one user's policy facts, measured
  on the backends themselves; it places its guard between the agent and
  any backend, where our selector's supersession stage sits
  (responsibility 6). It measures Graphiti and Mem0, two of our
  backends; no version of either is stated as read (no occurrence of
  "graphiti-core" or "mem0ai"), and we pin mem0ai 2.0.2 and
  graphiti-core 0.31.2 (`requirements.txt:41`, `:45`). Our Graphiti
  cells record Graphiti's own invalidations apart from the kernel's
  supersession and credit them to no locus
  (`GRAPHITI_BACKEND.md:307-313`). An instance in part (b), condition 8
  (supersession).

- **B14. AgentLeak.** "AgentLeak: A Benchmark for Internal-Channel
  Privacy Leakage in Multi-Agent LLM Systems". Faouzi El Yagoubi, Godwin
  Badu-Marfo, Ranwa Al Mallah. arXiv:2602.11510, v1 12 Feb 2026, v3 15
  Jun 2026, cs.AI; comments: "19 pages, 9 figures, 16 tables. Code and
  dataset available at this https URL".
  https://arxiv.org/abs/2602.11510. Accessed 2026-11-20. Read: abstract.

  Does: "sensitive data may pass through inter-agent messages, shared
  memory, and tool arguments"; it instruments "seven privacy-relevant
  communication pathways" over "1,000 scenarios". Reported: "multi-agent
  configurations reduce final-output leakage (C1: 27.2% vs 43.2% in
  single-agent mode) compared with single-agent baselines but introduce
  internal channels that raise total system exposure to 68.9%
  (aggregated across C1, C2, C5)". Differs: leakage by channel inside
  one coordinator-worker task, measured on execution traces; not one
  user's long-term memory shared by agents across sessions, and no
  policy layer. Shared memory is one of its channels.

- **B15. MemArena.** "MemArena: An Ego-Centric Benchmark for On-Device
  Agentic Personal Memory Assistants at Scale". Jiadong Zhang, Xiaosong
  Ma. arXiv:2608.02613, v1 20 May 2026, v2 2 Oct 2026, cs.CL; comments:
  "Accepted at NeurIPS 2026 (Evaluations & Datasets Track). 53 pages.
  Code: this https URL data: this https URL".
  https://arxiv.org/abs/2608.02613. Accessed 2026-11-20. Read: abstract.

  Does: "a single-world conversational benchmark built with its MASim
  agent simulator, for 50 agents over 15 days", with ground truth over
  "six recall, reasoning, and trustworthiness evaluation dimensions",
  and five open-weight readers over "Vanilla context, BM25-RAG, Oracle
  retrieval, Memobase, and MemSearch as memory backends". Reported:
  "Permission-aware access fails in two distinct modes: Oracle leaks
  heavily, while the other backends fail to surface the protected fact."
  Differs: a personal assistant's memory of its owner's conversations,
  with permission-aware access scored on answers; no layer between
  several agents and one store in the abstract.

- **B16. PersonaMem (a single-user analogue).** "Know Me, Respond to Me:
  Benchmarking LLMs for Dynamic User Profiling and Personalized
  Responses at Scale". Bowen Jiang, Zhuoqun Hao, Young-Min Cho, Bryan
  Li, Yuan Yuan, Sihao Chen, Lyle Ungar, Camillo J. Taylor, Dan Roth.
  arXiv:2504.14225, v1 19 Apr 2025, v2 27 Oct 2025, cs.CL; comments:
  "The 2025 Conference on Language Modeling (COLM)".
  https://arxiv.org/abs/2504.14225. Accessed 2026-11-20. Read: abstract.

  Does: "over 180 simulated user-LLM interaction histories, each
  containing up to 60 sessions of multi-turn conversations across 15
  real-world tasks"; the model must pick "the most suitable response
  according to the current state of the user's profile". Reported:
  frontier models "achieving only around 50% overall accuracy". Differs:
  one user and one model, with an evolving profile: the single-user
  analogue of our profile and task-context facts and of our recency
  probe. No memory shared by agents.

- **B17. PrefEval (a single-user analogue).** "Do LLMs Recognize Your
  Preferences? Evaluating Personalized Preference Following in LLMs".
  Siyan Zhao, Mingyi Hong, Yang Liu, Devamanyu Hazarika, Kaixiang Lin.
  arXiv:2502.09597, v1 13 Feb 2025, cs.LG; comments: "Accepted at ICLR
  2025 as oral presentation. Code and data at: this https URL".
  https://arxiv.org/abs/2502.09597. Accessed 2026-11-20. Read: abstract.

  Does: "3,000 manually curated user preference and query pairs spanning
  20 topics", in conversations of up to 100k tokens. Reported: "in
  zero-shot settings, preference following accuracy falls below 10% at
  merely 10 turns (~3k tokens) across most evaluated models." Differs:
  one user's stated preferences in one long conversation, the
  single-user analogue of our profile facts; no store shared by agents.

## (b) Documented instances of the stress conditions

For each condition: ours in brief, with where it is defined; each
instance found, with its kind (P, A, V, T), what happened, in which
system, the URL, the access date and how close it is to ours; then what
was searched for and not found. V1 to V5 are the agent variants of
`HETEROGENEITY.md`; `wrong_user`, `missing_metadata`, `flood10` and
`flood50` are the faulty agents of `STRESS_DIMENSIONS.md`. Issue authors
are not named. An entry of part (a) is cited by its tag.

## (b) 1. Identity mismatch

**Ours.** Two faults. An agent tags the user with another convention, an
email form `<user_id>@users.example` (V2, `HETEROGENEITY.md:138-163`). A
writer tags its requests with another user's id (`wrong_user`,
`STRESS_DIMENSIONS.md:379-432`). The kernel canonicalizes the first
(`HETEROGENEITY.md:76-104`) and, for the second, binds the user from the
kernel session that the harness opens (`STRESS_DIMENSIONS.md:387-402`).

- **V. Amazon Bedrock AgentCore, the actor id.** The FGAC page (A11):
  "The primary isolation pattern requires that the actorId on a request
  equal the caller's JWT sub claim", and "Existing deployments often use
  an internal user id as the actorId that does not match the sub value
  from their identity provider." It offers remedies, such as comparing
  against a custom claim that holds the internal id.
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-gateway-fgac.html,
  accessed 2026-11-20. How close: the vendor documents that two identity
  conventions for one user coexist in deployments, our V2. It names the
  mismatch as a migration problem for its isolation policy, not as an
  observed failure.

- **T. Hermes Agent, the Mem0 provider's read filter.**
  NousResearch/hermes-agent issue #38424, "Mem0 provider read filter
  misses agent-attributed memories", opened 2026-06-03, closed as not
  planned 2026-10-06. "The Mem0 memory provider writes memories with
  both `user_id` and `agent_id`, but reads them back with only
  `user_id`." The reporter's counts for one user id: 153 memories under
  the user-only filter; 3,379 with an OR filter that adds one agent's
  scope (`hermie`), rows that carry three agent ids, and 153 with none.
  The closing comment: the provider moved into Mem0's own plugin, where
  "reads still filter on `user_id` only, and their code now documents
  that as intentional".
  https://github.com/NousResearch/hermes-agent/issues/38424, accessed
  2026-11-20. How close: the same user id on both sides; the writer adds
  an agent scope that the reader's filter leaves out, so the reader
  misses rows. V2's effect (a miss, not a leak), caused by a scope
  convention, not a user-id convention.

- **T and V. Mem0, an AND of two identifiers.** mem0ai/mem0 issue #3218,
  "No memories are returned when filtering by both user_id and
  agent_id.", opened 2025-07-24, closed as not planned 2026-03-27 with:
  "This is expected behavior, and I understand it can be unintuitive at
  first." Mem0's own page (A10) calls it a "Common Pitfall": such a
  search "only matches records that have both fields set, which the
  default extraction path never produces."
  https://github.com/mem0ai/mem0/issues/3218 and
  https://docs.mem0.ai/platform/features/entity-scoped-memory, accessed
  2026-11-20. How close: the writer's convention (one identifier per
  extracted fact) and the reader's (both) disagree, and the read returns
  nothing.

- **T. LlamaIndex and CrewAI, the same AND in two integrations.**
  run-llama/llama_index issue #20492, "[Bug]: Mem0 integration does not
  work if both `user_id` and `agent_id` are provided", opened
  2026-01-16, closed as completed 2026-01-24: "memories from user chat
  messages are stored with the parameter `user_id`, while assistant chat
  messages are stored with the parameter `agent_id`. But on search, both
  these filters are applied and nothing is found." crewAIInc/crewAI
  issue #3220, "[BUG] Mem0 Memory Save / Search Issue", opened
  2025-07-25 by a member of the crewAI organization, closed as not
  planned by a bot after inactivity on 2025-09-04: "All the message
  which are sent to Mem0 are sent as `assistant` message. There memory
  will be tagged as `agent_id` only."; "`Agent_id` has been dropped, we
  don't send agent_id parameter while sending the mem0 search request."
  https://github.com/run-llama/llama_index/issues/20492 and
  https://github.com/crewAIInc/crewAI/issues/3220, accessed 2026-11-20.
  How close: integration reports of the AND of identifiers above: the
  writer files a turn under one identifier, the reader asks for another
  or for both, and the read misses rows. Reports, not measurements.

- **T. Mem0, scope set through metadata.** mem0ai/mem0 pull request
  #6656, "fix(memory): stop add() metadata from setting a memory's
  identity scope", merged 2026-08-04. Before it, metadata could carry
  `agent_id` and `run_id`: "A caller scoped by `user_id` alone could
  therefore write into scopes it never held", and the row then appeared
  to reads filtered on those scopes. After it: "Passing an entity param
  is unchanged and remains the only way to set scope."
  https://github.com/mem0ai/mem0/pull/6656, accessed 2026-11-20. How
  close: a claim of agent scope decided where the row was filed. In our
  terms that is the owner field, which the kernel fills from the request
  (`HETEROGENEITY.md:180`), not the user id; the user-id case is #6278,
  next. The fix closes one channel; scope still comes from the caller's
  arguments.

- **T. Mem0, update() metadata that sets the user id.** mem0ai/mem0 pull
  request #6278 (condition 7): before it, an update's metadata could set
  the `user_id` under which the memory is filed. How close: our
  `wrong_user`: the caller's own claim decided which user's scope the
  row is filed under. A merged fix, 2026-07-21.

- **T. Hermes Agent, one fixed id for every user.**
  NousResearch/hermes-agent pull request #5895 (condition 7): memory
  plugins filed every gateway user's memory under one static identifier.
  How close: the agent tagged memory with a fixed id instead of the
  user's, though the gateway knew the user (the fix passes
  `source.user_id`). A merged fix, 2026-04-07.

- **T. n8n with Zep, one user under many ids.** n8n community forum,
  "The N8N and ZEP memoyintegration is not accurately set up", posted
  2025-06-10. "The main problem is that ZEP is creating multiple userID
  unabling me to keep track of one specific user." "No error message."
  No reply from n8n staff on the page.
  https://community.n8n.io/t/the-n8n-and-zep-memoyintegration-is-not-accurately-set-up/130269,
  accessed 2026-11-20. How close: one user filed under many ids, our V2
  on the writer side, in an integration. A user's report, not confirmed.

- **Not found.** A measurement of how often agents of one deployment tag
  a request with another user's id, or with another convention for the
  same user. Two merged fixes (Mem0 #6278, Hermes #5895) document the
  mechanism of a misfiled user id; neither measures it. Searched
  (2026-11-20): reports of agent memory stored under the wrong user id,
  or of identity mismatch, for LangGraph, Letta, Zep and Mem0. The
  search returned vendor posts and forum threads; the primary ones are
  above.

## (b) 2. Missing metadata

**Ours.** V3: a writer omits `owner_agent` and `sharing_policy`, and a
consumer applies no visibility rule of its own
(`HETEROGENEITY.md:165-185`); the faulty `missing_metadata` agent is V3
on one agent (`STRESS_DIMENSIONS.md:434-451`). The kernel fills the
owner and defaults the policy to private, so it loses the memory as the
other loci do and is protected only from the leak
(`HETEROGENEITY.md:183-185`).

- **T. Mem0, an update drops custom metadata.** mem0ai/mem0 issue #5160,
  "_update_memory() still drops custom metadata on all non-MongoDB
  vector stores (follow-up from #4495 never completed, regressed in V3
  pipeline)", opened 2026-05-16, closed as completed 2026-06-15; a
  maintainer's triage note names two open fixes, #5179 and #5480.
  "Memory.update() and AsyncMemory.update() silently drop all custom
  metadata fields"; only "a hard-coded whitelist of 5 session
  identifiers" survives; "All custom metadata fields are silently
  dropped. No error or warning is raised." Chroma is among the stores
  listed. https://github.com/mem0ai/mem0/issues/5160, accessed
  2026-11-20. How close: metadata lost on the write path, by the backend
  rather than by an agent; owner and sharing fields are custom metadata
  in Mem0's terms. Whether our pinned mem0ai 2.0.2
  (`requirements.txt:41`) behaves so was not checked.

- **T. Mem0 Platform, identity fields reported missing.** mem0ai/mem0
  issue #5224, "[Bug] Platform v3 API: add() accepts user_id/agent_id
  but doesn't store them [...] get_all returns empty", opened
  2026-05-22, closed 2026-06-05. The reporter: "the stored memory
  records have `user_id=None` and `agent_id=None`". A maintainer
  narrowed it: "This means `user_id` and `agent_id` are being persisted
  correctly on the backend"; the list endpoint's filter was at fault,
  and the Platform team fixed it.
  https://github.com/mem0ai/mem0/issues/5224, accessed 2026-11-20. How
  close: rows that looked as if they had lost their identity fields,
  where the fault was a filter. It shows the symptom of missing metadata
  (rows not found), for the user field rather than V3's owner and policy
  fields.

- **T. mcp-memory-ts, rows without a user.** "Security Fix Report - NULL
  user_id in Entities Table", dated 2025-10-14, in the docs of the
  repository bobmatnyc/mcp-memory-ts (one star when read). "256 entities
  (7% of database) had NULL `user_id` values"; they were "Inaccessible
  to any user". Its listed causes include "Application code not
  enforcing NOT NULL constraints" and "Race conditions during entity
  creation".
  https://raw.githubusercontent.com/bobmatnyc/mcp-memory-ts/a04ead577ae9ed3342163e5d8266043205beccb5/docs/security/SECURITY_FIX_REPORT_20251014.md,
  accessed 2026-11-20. How close: rows written without the user field
  were unreachable, the outcome our partition gives a row with no
  `user_id` (`RETRIEVAL_PATH.md:28`) and the miss V3 predicts for a row
  with no owner or policy. A small project's own report.

- **Ours, a known limit.** The kernel's documented limitation: "Legacy
  unscoped memories are excluded" (`SHARED_MEMORY_SYSTEM.md:473`).

- **Ours, met at a backend.** The Zep Cloud provider, removed in Subtask
  16: "Zep stored text only, so the required metadata was lost and its
  rows failed the user partition and the visibility rule"
  (`PROVIDER_CONTRACT.md:175-177`). The outcome V3 predicts (rows lost
  to the partition and the visibility rule), caused by a backend that
  dropped the fields, not by an agent that omitted them.

- **Not found.** A published measurement of agents that omit ownership
  or sharing metadata. Searched (2026-11-20): agent memory records
  missing a user id or metadata after a write. The papers V3's grounding
  cites do not document it ("Our docs' own citations").

## (b) 3. Version skew

**Ours.** V1: the agent runs the pipeline one version back: as a writer
it keeps the old private default; as the consumer it builds the legacy
block (`HETEROGENEITY.md:114-136`). Every trial records
`pipeline_version` (`REPLICATED_LOGIC.md:62-65`).

- **T. Agno against Mem0 2.x.** agno-agi/agno issue #11340, "Mem0Tools
  search_memory and get_all_memories fail on Mem0 2.x: user_id must be
  passed in filters", opened 2026-10-27, open when read. "Since Mem0
  2.0, both the local `Memory` and the platform `MemoryClient` reject
  top-level entity parameters in `search()` and `get_all()` and take
  them in `filters` instead, so both tool functions always return Mem0's
  error text instead of memories." A reply: "Mem0 1.x does the
  opposite", and "agno doesn't pin `mem0ai`".
  https://github.com/agno-agi/agno/issues/11340, accessed 2026-11-20.
  How close: a component written for one backend version runs against
  another and recall fails. Between a framework and a backend, not
  between two agents of one deployment.

- **T. agent-os against Mem0 2.x, silently.** use-agent-os/agent-os
  issue #3918, "[Bug]: mem0 provider recalls nothing on mem0 2.x (search
  scope rejected)", opened and closed as completed by its reporter on
  2026-11-17. "The provider catches this, logs
  `mem0_provider.prefetch_failed`, and returns an empty recall block on
  every turn." "(`limit` was also renamed to `top_k`; on 2.x it is
  swallowed by `**kwargs` and ignored.)" The expected behavior: "It
  should not look the same as having no memories."
  https://github.com/use-agent-os/agent-os/issues/3918, accessed
  2026-11-20. How close: the skew is silent and looks like an empty
  store, as a stale writer's private rows look like missing memories
  under V1.

- **V. Mem0's migration guide.** Mem0 Docs, "Open Source: Migrating to
  the New Memory Algorithm". No date shown; page metadata: modified
  2026-08-05. Entity ids for `search()` and `get_all()` move inside
  `filters` ("top-level kwargs now raise ValueError"); defaults change:
  `top_k` 100 to 20, `threshold` None to 0.1, `rerank` True to False;
  "The new algorithm collapses this into a single call that only adds.";
  "Graph memory is removed from OSS."
  https://docs.mem0.ai/migration/oss-v2-to-v3, accessed 2026-11-20. How
  close: the documented changes behind the two issues above. Agents on
  the two sides of it, sharing one store, read with different defaults.

- **T. Mem0 Platform, an undocumented change.** In issue #5224
  (condition 2), a maintainer: "`search()` and `get_all()` now return a
  `400` error if `filters` is omitted entirely. This is a breaking
  change from v2 that isn't documented in the v2 → v3 migration guide."
  Its link is the Platform guide,
  https://docs.mem0.ai/migration/platform-v2-to-v3 (not fetched), not
  the open-source guide above.
  https://github.com/mem0ai/mem0/issues/5224, accessed 2026-11-20.

- **V. Mastra's memory defaults.** Mastra docs, the v1 migration guide
  for Memory. No date on the page. Requested
  https://mastra.ai/guides/migrations/upgrade-to-v1/memory.md, served at
  https://mastra.ai/reference/migrations/upgrade-to-v1/memory/llms.txt.
  "The default scope for both working memory and semantic recall has
  changed from `'thread'` to `'resource'`." Also: "The `lastMessages`
  default decreased from 40 to 10, `semanticRecall` is now disabled by
  default"; "The `topK` increased from 2 to 4". Accessed 2026-11-20. How
  close: a scope default that differs between two versions of one
  framework, so two agents on either side would search different scopes
  for one user. A documented change, not a failure report.

- **P. Memory across a model upgrade.** "Does Your Agent's Memory
  Survive a Model Upgrade? A Controlled Study of Memory Portability".
  Ankit Goyal, Jaideep Ray. arXiv:2609.05339, v1 4 Sep 2026, cs.AI;
  comments: "18 pages, 3 figures, 7 tables, under review".
  https://arxiv.org/abs/2609.05339, accessed 2026-11-20. Read: abstract.
  Over 48 synthetic histories and two open-weight models under 10B
  parameters: "fixed-schema structures transfer reliably"; compressed
  notes shift by +9.91 or −13.28 points depending on the direction of
  the migration; a 50/50 mixed embedding index captures 4.96 of the
  11.90 points that full re-embedding gains; "store-only repair of NOTES
  fails to reach a 90% performance recovery target in all 48 test
  cases". How close: skew of the model or the embedder over one store,
  not of the memory code. Our stores pin one embedding model
  (`PROVIDER_CONTRACT.md:82-83`).

- **T. Mem0 server, an embedder switch.** mem0ai/mem0 issue #4985,
  "bug(server): switching embedding provider silently drops writes due
  to vector dimension mismatch", opened 2026-04-27, open, labelled
  "P1-high" and "accepted". "The API returns 200 with a memory ID as if
  the write succeeded, but nothing is persisted."
  https://github.com/mem0ai/mem0/issues/4985, accessed 2026-11-20. How
  close: a configuration change between writer and store makes writes
  vanish while reporting success.

- **Not found.** Two agents on different versions of one memory library
  writing one store, reported or measured. The instances are a framework
  against a backend version, or a model against a store. Searched
  (2026-11-20): default and API changes that broke agent memory recall.

## (b) 4. Per-agent tuning

**Ours.** V4: the consumer uses its own retrieval settings, k 5,
`relevance_threshold` 0.5 and a 1,500-token budget, against the kernel's
10, 0.0 and 2,000 (`HETEROGENEITY.md:187-210`), values this codebase
itself shipped (`HETEROGENEITY.md:193-196`). In the kernel the
consumer's settings have no channel, except under the ablation
`consumer_config: honor` (`HETEROGENEITY.md:68`, `ABLATION.md:34-48`).

- **V. Caura (MemClaw), per-agent retrieval defaults on a shared
  store.** The service S1 measures, in its own repository,
  caura-ai/caura-memclaw: the README (read as
  https://raw.githubusercontent.com/caura-ai/caura-memclaw/main/README.md)
  says "MemClaw is now Caura" ("same product, one name") and lists
  "Per-agent retrieval tuning": "each agent optimizes its own retrieval
  profile (top_k, min_similarity, graph_max_hops, blend weights) from
  feedback". The integration guide (`static/docs/integration-guide.md`
  on main) describes the tool `caura_tune`: "Persist per-agent retrieval
  defaults (top_k, min_similarity, fts_weight, freshness, recall boost,
  graph hops, similarity blend) until changed again".
  https://github.com/caura-ai/caura-memclaw, accessed 2026-11-20; the
  main branch when read, and S1 does not say which version it measured,
  as read. How close: our V4 built in by design: agents that share one
  store each keep their own retrieval settings. Our kernel applies its
  own (`HETEROGENEITY.md:68`). A documented feature, with no measurement
  of its effect as read.

- **V. Defaults an agent inherits.** Mem0's migration guide changes
  `top_k` 100 to 20 and `threshold` None to 0.1; Mastra's changes `topK`
  2 to 4 and `lastMessages` 40 to 10 (both in condition 3). How close:
  two agents built against different versions get different retrieval
  settings without choosing them.

- **T. Related: Mem0, a threshold applied to distances.** mem0ai/mem0
  issue #4453, "fix: threshold filtering broken for distance-based
  vector stores", opened 2026-03-20, labelled "P1-high", closed
  2026-06-05 by pull request #5391, whose body says "Closes #4453". "The
  threshold check assumes scores are similarity (higher = better), but
  many vector stores return raw distance (lower = better)." The result:
  "good matches get dropped and bad matches pass through." The fix
  "normalizes all 11 affected backends to return similarity scores";
  before it, "Distances > 1.0 get capped to 1.0 → all scores collapse to
  identical values, no ranking signal".
  https://github.com/mem0ai/mem0/issues/4453 and
  https://github.com/mem0ai/mem0/pull/5391, accessed 2026-11-20.
  Related, not an instance: a backend bug that makes one fixed setting
  mean different things on different backends. V4 meets the same
  problem: native Mem0's scores are "saturated near 1.0"
  (`HETEROGENEITY.md:205`), so a 0.5 threshold drops nothing there and
  most rows on in-house. Mem0 #7072, a k applied before the user filter,
  is under condition 7.

- **Not found.** A documented incident or measurement in which agents
  that share one store use different retrieval settings and so see
  different memories. Caura documents such settings as a feature
  (above), with no measurement of their effect as read. Searched
  (2026-11-20): changes of a retrieval threshold or top_k default that
  broke recall, in Mem0, Letta, LangMem and Zep. The other entries
  concern inherited defaults and a backend bug.

## (b) 5. Concurrent writers

**Ours.** Level `concurrent`: within a session every write is issued
without waiting for the earlier ones, and the consumer's probes are
issued once every write of the last session has begun
(`STRESS_DIMENSIONS.md:226-263`). The kernel's one barrier makes a probe
wait for every write accepted before it; a replicated agent's barrier
covers only its own writes (`STRESS_DIMENSIONS.md:264-293`,
`REPLICATED_LOGIC.md:72-79`). The failure measured is a read that misses
an accepted write still in flight, not a lost update.

- **V. Letta, concurrent edits of one block (the legacy block API).**
  Letta Docs, "Shared memory", the legacy page (S17). Its concurrency
  table, which belongs to the legacy block API, marks `memory_rethink`
  "No (last-writer-wins)", and the page says: "Anti-pattern : Multiple
  agents doing memory_rethink on the same block simultaneously leads to
  lost updates." Its advice: designate one agent as the owner for heavy
  edits and let the others append. Served at
  https://docs.letta.com/v1-sdk/memory/shared-memory, accessed
  2026-11-20. How close: lost updates between agents that write one
  block. A different failure from ours, and the remedy is a convention
  each agent must follow.

- **V. Letta, shared memory repositories: a write is seen after a push
  and a pull.** Letta Docs, "Shared memory", the current page (S17):
  "The agent must commit and push its changes. Other agents can then
  pull those commits into their own checkouts."; "Later synchronization
  fast-forwards the local checkout from its remote."
  https://docs.letta.com/concepts/shared-memory, accessed 2026-11-20.
  How close: our missed read, built into the design: another agent's
  write reaches a reader only through the writer's push and the reader's
  pull, so a read before them misses it. The page names no point that
  orders a read after other agents' writes, as read; each agent's own
  syncs decide, as in our replicated locus.

- **V. Graphiti, overlapping writes to one graph.** Zep Documentation,
  Graphiti, "Concurrent Ingestion". No date shown; page metadata:
  modified 2026-11-15. "Serial ingestion does not put overlapping calls
  in order. Await each add_episode call for one graph before you start
  the next call for that graph." The opt-in concurrent mode runs several
  episodes at once, and "Each episode then commits in the order of its
  call"; "The mode is not tested on Neo4j or Amazon Neptune."
  https://help.getzep.com/graphiti/core-concepts/concurrent-ingestion,
  accessed 2026-11-20. How close: the backend leaves the order of
  concurrent writers to the caller. The page addresses one caller; it
  does not say how two agents that write one graph should order their
  calls.

- **V. Mem0 Platform, an accepted write that is not done.** Mem0 Docs,
  "Add Memory", under "Add with Mem0 Platform": "Expect a `status:
  "PENDING"` response with an `event_id`. Poll `GET
  /v1/event/{event_id}/` to confirm completion." No date on the page.
  https://docs.mem0.ai/core-concepts/memory-operations/add.md, accessed
  2026-11-20. How close: the window our barrier covers, a write accepted
  and not yet complete. The event id goes to the writer; the page does
  not say how a reader in another agent would wait.

- **T. Mem0, duplicate rows from concurrent adds.** mem0ai/mem0 issue
  #6515, "bug(memory): hash-dedup TOCTOU race in add() creates permanent
  duplicate memories under concurrency", opened 2026-07-22, open. Its
  scenarios include "two parallel agent turns writing to the same
  `user_id`"; "There is no error, warning, or user-visible signal".
  https://github.com/mem0ai/mem0/issues/6515, accessed 2026-11-20. How
  close: concurrent writers of one user's scope; the effect is
  duplicates, not a missed read.

- **T. Mem0, concurrent writes corrupt the index.** mem0ai/mem0 issue
  #4892, "Bug: concurrent AsyncMemory writes corrupt Qdrant HNSW index
  ('index N is out of bounds')", opened 2026-04-19, open, labelled
  "P1-high" and "accepted". Twenty concurrent writers on embedded
  Qdrant; "Subsequent reads (`search()`, `get()`) either return wrong
  results or raise the same error until the process is restarted and the
  index is rebuilt." https://github.com/mem0ai/mem0/issues/4892,
  accessed 2026-11-20. How close: concurrent writers break later reads;
  a backend defect, not an ordering gap.

- **T. Mem0, no locking.** mem0ai/mem0 discussion #7303, "Handling
  concurrency race conditions and graph-vector consistency in hybrid
  Mem0 deployments", opened 2026-09-14. The answer marked as accepted
  (the page does not show its author's relation to Mem0): "Mem0 does not
  implement distributed locking internally at the library layer. If two
  concurrent agent runs write to the same user_id , both will read stale
  state, bypassing the UPDATE logic and producing duplicate vector
  embeddings." It advises a queue keyed by `user_id`.
  https://github.com/mem0ai/mem0/discussions/7303, accessed 2026-11-20.
  How close: the remedy it recommends is a point outside the agents that
  orders one user's writes; ours orders each read after the writes
  accepted before it (`STRESS_DIMENSIONS.md:266-273`). Not a
  maintainer's statement as far as read.

- **P. S-Bus, silent overwrites.** S8, §II-A of the v2 HTML: with four
  concurrent agents writing a shared key, "20/20 trials produce silent
  overwrites under last-write-wins" (a controlled microbenchmark).
  https://arxiv.org/html/2605.17076v2, accessed 2026-11-20. How close:
  lost updates on shared state; ours measures missed reads.

- **P. Governed Shared Memory, no missed read under strong writes, and
  the dedup race.** S1, §8.3: on 8 dedicated facts, each polled from
  write completion, under strong write mode, "all 8 facts surfaced on
  the poller's first search after the write", with a median
  time-to-visible of 0.83 s and at most 1.97 s, "itself essentially one
  search round-trip"; "its cost is paid in the write latency". §9.4:
  measured "with tight per-fact polling at low contention", the window
  "is effectively zero", and "the consistency cost is paid in the write
  latency, not as a post-write read-visibility lag": write latency p50
  1,840 ms and p99 19,319 ms over the 194 writes that completed (§8.4).
  §8.4 and §9.2: "concurrent writes race at the dedup gate", and "the
  synchronous gate can reject a write before the asynchronous detector
  ever sees it." https://arxiv.org/html/2606.24535v1, accessed
  2026-11-20. How close: S1 measured no missed read under strong mode,
  on 8 facts at low contention, with polling that starts when the write
  returns; a read issued while a write is still in flight, our case, was
  not measured. One service, self-measured, no comparand.

- **P. AC-Saga, CoAgent and Concord.** S10 and S9 control conflicting
  writers of a database or task state. O8 measures stale observations in
  an agent's context after another agent edits the source: the runtime
  analogue of our missed read, in the context window rather than the
  store.

- **P. deer-flow, a silent lost update.** S21 reproduces "a silent lost
  update in ByteDance's deer-flow" from the project's open issue #3123:
  "a todo list is visible during streaming but disappears once the run
  completes", which the project's regression test attributes to "a
  downstream node's partial state update with todos=None overwriting the
  accumulated value under the default last-write-wins channel" (§VI-E).
  https://arxiv.org/html/2606.17182v1, accessed 2026-11-20. How close: a
  lost update in an agent application's state, not in a memory store,
  and not a missed read. Issue #3123 was not read.

- **Not found.** A documented production instance in which one agent
  read before another agent's accepted memory write was searchable; S1
  measured none under strong mode. Searched (2026-11-20): Mem0's
  asynchronous add and the Platform's pending status; concurrent writes
  in Mem0, Letta and Graphiti.

## (b) 6. Flooding

**Ours.** `flood10` and `flood50`: a faulty writer stores F more rows in
each session where it writes, near-duplicates of its utterances and
irrelevant notes (`STRESS_DIMENSIONS.md:453-475`). The defense measured
is the write quota: per writer, user and session, at most `max_writes`
accepted writes, with duplicates by normalized text rejected first
(`STRESS_DIMENSIONS.md:477-493`). The flood is benign; poisoning is not
tested (`STRESS_DIMENSIONS.md:658-660`).

- **T. Mem0, one deployment's own audit.** mem0ai/mem0 issue #4573,
  "What we found after auditing 10,134 mem0 entries: 97.8% were junk",
  opened 2026-03-27, closed as completed 2026-06-05. "We've been running
  mem0 in production for 32 days. One AI agent, one human, daily
  conversations, Qdrant backend." "224 entries survived the full
  process. Out of 10,134." The largest category, "Boot file / system
  prompt restating", is 52.7% of the junk: "The same facts re-extracted
  every session." A feedback loop stored one hallucinated preference 808
  times ("191 exact copies of one sentence. Nobody in the system uses
  Vim."), because "Recalled memories get re-extracted and stored as new
  entries." https://github.com/mem0ai/mem0/issues/4573, accessed
  2026-11-20. How close: one writer (the extraction pipeline) storing
  the same facts again and again from benign operation: the
  near-duplicate half of our flood. A user's own audit; nothing read
  checks its numbers.

- **T. Mem0 TypeScript, near-duplicates.** mem0ai/mem0 issue #7123,
  "[mem0-ts] add() dedup search hardcoded to top-10 with no similarity
  threshold → duplicate memories on large corpora", opened 2026-08-26,
  open. "we captured 8 near-identical memories about a single fact in ~1
  hour." https://github.com/mem0ai/mem0/issues/7123, accessed
  2026-11-20. How close: near-duplicates from one writer that the
  backend's own dedup misses.

- **V. ai-memory, write quotas per agent.** The ai-memory crate, version
  0.7.1, source file `src/quotas.rs`: "Each `(agent_id, namespace)`
  tuple gets a single row in the `agent_quotas` table" with counters for
  memories written per day, storage bytes and links per day; write paths
  "consult [`check_and_record`] before committing" (quotes from the file
  drop its comment markers). The same file records a fix: "Pre-v50 the
  substrate keyed quota accounting on `agent_id` alone: an agent that
  wrote generously in a personal scratch namespace starved their writes
  against a shared namespace because the same daily cap applied to
  both." https://docs.rs/crate/ai-memory/0.7.1/source/src/quotas.rs,
  accessed 2026-11-20. How close: the one per-agent write quota read
  here; AgentCore's limit (next) is the other write limit read with a
  key finer than the tenant. Its key is agent and namespace, per day;
  ours is writer, user and session (`STRESS_DIMENSIONS.md:477-493`). Its
  own recorded flaw was a key too coarse for an agent that writes to
  several scopes.

- **V. Amazon Bedrock AgentCore, write limits per actor and session.**
  "Quotas for Amazon Bedrock AgentCore", section "AgentCore Memory
  Service Quotas". No date on the page. "Maximum CreateEvent requests
  per actor, per session, including conversational payloads": 5, not
  adjustable, described as "The maximum number of CreateEvent requests
  per second, per actor, per session, including conversational
  payloads"; the same limit without conversational payloads is 10, and
  IngestData has the same pair.
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html,
  accessed 2026-11-20. How close: keyed per actor and session, near ours
  (writer, user and session). Two differences: it limits a rate, not a
  count, and the actor is the identity the events are stored under, not
  necessarily the writing agent: the FGAC page (A11) says Memory "stores
  events and records under the actorId you supply", pairs it with "the
  authenticated user or agent", and says deployments "often use an
  internal user id as the actorId". Microsoft Foundry caps the count per
  scope instead: "Maximum memories per scope: 10,000" (A16).

- **P. Governed Shared Memory, a write ceiling.** S1, §8.2: "The server
  caps writes at 10 per second per tenant".
  https://arxiv.org/html/2606.24535v1, accessed 2026-11-20. How close: a
  rate per tenant, not a count per writer, user and session. It
  protected the service and made the authors pace their writes; it was
  not measured as a defense.

- **V. Microsoft, AI Recommendation Poisoning.** Microsoft Security
  Blog, "Manipulating AI memory for profit: The rise of AI
  Recommendation Poisoning", by the Microsoft Defender Security Research
  Team and Noam Kochavi, published 2026-02-10. "We identified over 50
  unique prompts from 31 companies across 14 industries"; hidden
  instructions in "Summarize with AI" buttons "attempt to inject
  persistence commands into an AI assistant's memory via URL prompt
  parameters". "Microsoft has implemented and continues to deploy
  mitigations against prompt injection attacks in Copilot."
  https://www.microsoft.com/en-us/security/blog/2026/02/10/ai-recommendation-poisoning/,
  accessed 2026-11-20. How close: unwanted writes into an assistant's
  memory by outsiders, found by reviewing AI-related URLs in email
  traffic over 60 days. Adversarial and targeted, where ours is a benign
  faulty agent bounded by a quota.

- **P. MINJA.** "Memory Injection Attacks on LLM Agents via Query-Only
  Interaction". Shen Dong, Shaochen Xu, Pengfei He, Yige Li, Jiliang
  Tang, Tianming Liu, Hui Liu, Zhen Xiang. arXiv:2503.03704, v1 5 Mar
  2025, v5 12 Feb 2026, cs.LG; comments: "Code released".
  https://arxiv.org/abs/2503.03704, accessed 2026-11-20. Read: abstract.
  "The attacker injects malicious records into the memory bank by only
  interacting with the agent via queries and output observations";
  "MINJA enables any user to influence agent memory". How close: writes
  an outsider causes through the agent; targeted, not a volume fault.

- **P. AgentPoison (background).** "AgentPoison: Red-teaming LLM Agents
  via Poisoning Memory or Knowledge Bases". Zhaorun Chen, Zhen Xiang,
  Chaowei Xiao, Dawn Song, Bo Li. arXiv:2407.12784, v1 17 Jul 2024,
  cs.LG. https://arxiv.org/abs/2407.12784, accessed 2026-11-20. Read:
  abstract. "AgentPoison achieves an average attack success rate higher
  than 80% with minimal impact on benign performance (less than 1%) with
  a poison rate less than 0.1%." First posted in 2024: background;
  `STRESS_DIMENSIONS.md:540-541` cites it. How close: a few poisoned
  rows suffice, the opposite of a volume fault; a quota does not bound
  it (`STRESS_DIMENSIONS.md:658-660`).

- **P. Experience-following.** "How Memory Management Impacts LLM
  Agents: An Empirical Study of Experience-Following Behavior". Zidi
  Xiong, Yuping Lin, Wenya Xie, Pengfei He, Zirui Liu, Jiliang Tang,
  Himabindu Lakkaraju, Zhen Xiang. arXiv:2505.16067, v1 21 May 2025, v2
  10 Oct 2025, cs.AI. https://arxiv.org/abs/2505.16067, accessed
  2026-11-20. Read: abstract. It studies "memory addition and deletion"
  and finds "error propagation, where inaccuracies in past experiences
  compound and degrade future performance". How close: the quality of
  what is added, not its volume or its writer.

- **Not found.** A measurement of what a flood of benign rows from one
  agent does to another agent's retrieval, or of a per-writer quota as a
  defense. Searched (2026-11-20): agent memory stores flooded with
  duplicate memories, write quotas or rate limits per agent, memory
  bloat incidents. The search returned design notes and blog posts; the
  primary sources are above.

## (b) 7. Cross-user contamination

**Ours.** No row of one user in another user's block: `cross_user_rows`
checks every probe's block (`BENCHMARK_V2.md:38-44`), and the user
partition fails closed on a missing `user_id` (`RETRIEVAL_PATH.md:28`).
Under `wrong_user`, misfiled rows leak into the victim's blocks in the
replicated and native loci (`STRESS_DIMENSIONS.md:411-419`).

- **T. Mem0, an update that refiles a memory under another user.**
  mem0ai/mem0 pull request #6278, "fix(memory): don't let update()
  metadata overwrite user_id/agent_id/run_id", merged 2026-07-21, whose
  body says "Closes #6277". "Concretely: `m.update(memory_id,
  metadata={"user_id": "someone_else"})` silently reassigns the memory
  into another tenant's scope"; "it disappears from the original
  tenant's `search()`/`get_all()`/`delete_all()` and appears under the
  new tenant's, without either tenant intending it." The PR reports unit
  tests that fail on `main` with the reassignment and pass with the fix.
  https://github.com/mem0ai/mem0/pull/6278, accessed 2026-11-20. How
  close: the mechanism of our `wrong_user`: a request's own metadata
  decided which user's scope a row landed in, so the row reached another
  user's reads. A merged fix; no leak was measured. Whether mem0ai 2.0.2
  (`requirements.txt:41`) has the behavior was not checked.

- **T. Hermes Agent, every gateway user's memory under one id.**
  NousResearch/hermes-agent pull request #5895, "fix: thread gateway
  user_id to memory plugins for per-user scoping", opened and merged
  2026-04-07 by its author, a collaborator. "Memory plugins (Mem0,
  Honcho) used static identifiers (`hermes-user`, config `peerName`)
  meaning all gateway users shared the same memory bucket."
  https://github.com/NousResearch/hermes-agent/pull/5895, accessed
  2026-11-20. How close: every user's memory filed under one fixed id,
  our `wrong_user` misfiling for all users at once, in an integration. A
  merged fix; the PR gives no count of leaked rows.

- **A. Open WebUI, CVE-2026-29071.** GitHub advisory
  GHSA-w9f8-gxf9-rhvw, "Open WebUI's Insecure Direct Object Reference
  (IDOR) allows access to other users' memories", published 2026-03-27
  in the GitHub Advisory Database; severity low, CVSS 3.1 score 3.1;
  CWE-639; affects open-webui <= 0.8.5, patched in 0.8.6. "Any
  authenticated user can read other users' private memories via
  `/api/v1/retrieval/query/collection`"; the handler "accepts a list of
  `collection_names` but performs no ownership validation"; memory
  collections are named `user-memory-{USER_UUID}`.
  https://github.com/advisories/GHSA-w9f8-gxf9-rhvw, accessed
  2026-11-20. How close: a store partitioned per user (a collection
  each) and one read path that did not check the owner. Our retrieval
  runs the partition check in one place, `retrieve_for_agent`, for the
  injector and SDK search alike (`RETRIEVAL_PATH.md:11-16`).

- **A. Open WebUI, CVE-2026-44570.** GitHub advisory
  GHSA-hmjq-crxp-7rjw, "Inconsistent authorization controls within
  memories API", published by the repository 2026-05-05 and in the
  GitHub Advisory Database 2026-05-11 (as "Open WebUI has inconsistent
  authorization controls within memories API"); severity high, CVSS 3.1
  score 8.3; CWE-639; affects open-webui < 0.6.19, patched in 0.6.19.
  "Authorization controls surrounding the memories API were
  inconsistent, resulting in the ability of a standard user to delete,
  restore, and view the contents of other users' memories."; "a call to
  `GET /api/v1/memories/` returns `[]` (as expected) but a call to `POST
  /api/v1/memories/query` reveals memories created by other users."
  https://github.com/open-webui/open-webui/security/advisories/GHSA-hmjq-crxp-7rjw
  and https://github.com/advisories/GHSA-hmjq-crxp-7rjw, accessed
  2026-11-20. How close: the listing filtered by user and a query path
  did not, the same pattern as CVE-2026-29071. Its restore of deleted
  memories is under condition 8.

- **A. LibreChat, CVE-2025-54868.** GitHub repository advisory
  GHSA-p5j8-m4wh-ffmw, "Reading of arbitrary Chats", published
  2025-08-04; severity high, CVSS 3.1 score 7.5; CWE-285; affects v0.0.6
  to v0.7.7, patched in v0.7.8. The GitHub Advisory Database's API
  answered 404 for it when read. "The endpoint `/api/search/test` allows
  for direct access to stored chats in the Meilisearch engine without
  proper access control. This results in the ability to read chats from
  arbitrary users."
  https://github.com/LibreChat-AI/LibreChat/security/advisories/GHSA-p5j8-m4wh-ffmw,
  accessed 2026-11-20. How close: a second read path, the search index,
  with no owner check. Conversation history, not a memory store, as with
  Cheshire Cat below.

- **T. Cheshire Cat, the episodic memory listing.** cheshire-cat-ai/core
  issue #1136, "Episodic Memory IDOR -- Authenticated Users Can Read Any
  User's Conversation History", opened 2026-06-30, open. "The `GET
  /memory/collections/{collection_id}/points` endpoint returns all
  vector memory points without filtering by the authenticated user's
  identity." "The recall endpoints correctly filter on this field."
  Tested on v1.9.2. A maintainer: "I have no intention of maintaining
  v1, and still have to port the vector memory to v2 as a plugin."
  https://github.com/cheshire-cat-ai/core/issues/1136, accessed
  2026-11-20. How close: the same pattern: recall filters by user, a
  second read path does not.

- **T. Mem0, graph search without the user filter (background).**
  mem0ai/mem0 issue #1805, "Filtering by user_id in graph memory search
  results does not work", opened 2024-09-04. "The vector memory search
  result (`memories`) is filtered by `user_id`, but the graph memory
  search result (`entities`) is not filtered by `user_id`": in the
  report, Alice's search returned a relation Bob had added ("charlie
  likes baseball"). A contributor the same day: "we knew about this
  issue and released a patch last week"; the issue was closed as stale
  on 2026-03-11. https://github.com/mem0ai/mem0/issues/1805, accessed
  2026-11-20. How close: two stores behind one memory API, one filtered
  by user and one not. Reported in 2024: background.

- **P. Governed Shared Memory, a read path that checked only the
  tenant.** S1, §8.1 and §9.1: on 2026-05-30 a GET-by-id read with an
  agent-scoped credential returned another fleet's rows "because the
  handler checked only the tenant", though "The gateway does resolve the
  agent identity" of such a credential. Fixed server-side on 2026-05-31;
  in a re-probe of 96 reads, 0 of 36 trust-1 cross-fleet reads returned
  a row (now HTTP 404). https://arxiv.org/html/2606.24535v1, accessed
  2026-11-20. How close: scope skipped on one read path of a governed
  service, with the identity known; across fleets of agents rather than
  users.

- **P. MemLeak, pooled retrieval.** A9: incidental leakage of 70 to 100%
  under pooled same-team retrieval; ownership gating after retrieval
  restores the clean baseline. https://neurips.cc/virtual/2026/169601,
  accessed 2026-11-20. How close: the leak a missing partition causes,
  measured, and our partition's check as the fix.

- **P. MEXTRA, memory pooled across users.** A14: without session
  control, "multiple users may share the same session, causing the
  memory module to store historical records from all users", and the
  attack extracts past user queries through queries of its own.
  https://arxiv.org/html/2502.13172v2, accessed 2026-11-20. How close:
  an attack on a store with no user partition; our partition removes
  other users' rows before the model sees them.

- **P. Unintentional cross-user contamination.** "No Attacker Needed:
  Unintentional Cross-User Contamination in Shared-State LLM Agents".
  Tiankai Yang, Jiate Li, Yi Nian, Shen Dong, Ruiyao Xu, Ryan Rossi,
  Kaize Ding, Yue Zhao. arXiv:2604.01350, v1 1 Apr 2026, cs.CL; no venue
  on the page. https://arxiv.org/abs/2604.01350 and
  https://arxiv.org/html/2604.01350v1, accessed 2026-11-20. Read:
  abstract; full text (HTML v1), searched. "In many deployments, a
  single agent serves multiple users within a team or organization,
  reusing a shared knowledge layer across user identities." It defines
  the failure as "a harmful cross-user transfer through persistent
  shared state in which the source interaction is benign". Rates of
  57.4% to 70.7% on EHRAgent (shared memory) and MURMUR (shared
  conversational context), all with GPT-4o; a write-time sanitizer cuts
  the Slack rate from 57% to 6% "but leaves substantial residual risk on
  EHRAgent". How close: not a partition leak. The state is shared across
  users on purpose, and the harm is a benign artifact misapplied. The
  full text has no occurrence of "partition" or "isolat".
  `HETEROGENEITY.md:144-147` cites it for V2 ("Our docs' own
  citations").

- **P. Audience-Bound memory, GateMem and PiSAs.** A4: "unscoped
  retrieval exposed forbidden items in 82% of its contexts". B6:
  retrieval-based and external-memory methods "still leak unauthorized
  or deleted information". B7: spillage across users through shared
  memory, "bottlenecked by incorrect LLM judgment calls". How close:
  measured leaks when nothing removes another principal's rows before
  the model sees them.

- **V. OpenAI, March 2023 (background).** OpenAI, "March 20 ChatGPT
  outage: Here's what happened", March 24, 2023. "We took ChatGPT
  offline earlier this week due to a bug in an open-source library which
  allowed some users to see titles from another active user's chat
  history." The bug was in the Redis client library, redis-py; the same
  bug may have exposed payment-related information of 1.2% of ChatGPT
  Plus subscribers active in a nine-hour window.
  https://openai.com/index/march-20-chatgpt-outage/, accessed
  2026-11-20. How close: an assistant's per-user history shown to
  another user, through a cache-client bug, not a memory policy. Before
  2025: background.

- **T. Related: Mem0 on MongoDB, k before the user filter.** mem0ai/mem0
  issue #7072, "bug(vector_stores/mongodb): search() applies filters
  after $vectorSearch's top_k limit, so scoped users get too few or zero
  results", opened 2026-08-22, open. "if the `top_k` vectors nearest the
  query all belong to user `bob`, then `search(top_k=5,
  filters={"user_id": "alice"})` returns 0 even when `alice` has many
  relevant memories". The report says the same class was reported for
  FAISS (#6998) and Cassandra (#6867), which were not read.
  https://github.com/mem0ai/mem0/issues/7072, accessed 2026-11-20.
  Related, not an instance: the user partition applied after k, so other
  users' vectors starve one user's reads (a miss, not a leak). What k
  does then depends on the backend, as V4's k 5 does on Mem0
  (`HETEROGENEITY.md:209`).

- **Not found.** No measured incident caused by one agent writing under
  another user's id (our `wrong_user` leak); two merged fixes document
  the mechanism (Mem0 #6278, Hermes #5895). The other instances are read
  paths without an owner check, pooled retrieval and intended sharing.
  Searched (2026-11-20): agent memory stored under a wrong user id that
  then appears in another user's memories; the results were blog posts,
  tutorials and sources already listed here. The two merged fixes were
  found by this file's review and read for this revision.

## (b) 8. Incomplete deletion

**Ours.** Complete deletion of a revoked fact: afterwards no row of the
user carries any form of any value it had, no later write brings one
back, and no read returns one, until a restatement
(`DELETION_AND_SUPERSESSION.md:102-106`). The forget deletes every
carrier, of any agent, after recording a tombstone
(`DELETION_AND_SUPERSESSION.md:160-182`); on Graphiti and A-MEM it also
scrubs derived text (`GRAPHITI_BACKEND.md:252-263`,
`AMEM_BACKEND.md:268-282`). The deletion probe forbids the revoked value
in the block and the answer (`BENCHMARK_V2.md:189`).

- **T. Mem0, the graph keeps a deleted memory.** mem0ai/mem0 issue
  #3245, "Memory deletion does not clean up Neo4j graph data", opened
  2025-07-29, closed as completed 2026-03-23. `Memory.delete(memory_id)`
  "only removes data from the vector store (Qdrant) and adds a history
  record, but fails to remove corresponding nodes and relationships from
  the Neo4j graph store" (emphasis dropped). mem0ai 0.1.115, Neo4j 5.23.
  https://github.com/mem0ai/mem0/issues/3245, accessed 2026-11-20. How
  close: a second carrier of the fact survives the delete, our notion of
  a carrier.

- **T. MemOS, a delete that answers success while the memory stays
  retrievable.** MemTensor/MemOS issue #2331, "删除记忆接口返回成功但记忆未实际删除"
  (translated here: the delete-memory API returns success, but the
  memory is not actually deleted), opened 2026-09-02 by an account that
  the API lists as a collaborator and that also posts the project's
  automated fix runs; open, labelled `types:bug` and
  `status:in-progress`, when read. Its body, translated here: after a
  delete returns success, the memory is still there and retrievable
  after a page refresh, in three deletes in a row. Two fix pull requests
  were closed unmerged: #2332 from that account (closed 2026-09-03) and
  #2533 from an outside contributor (closed 2026-11-09), whose body says
  "`Neo4jCommunityGraphDB.delete_node_by_prams()` deletes the matching
  graph nodes but never purges their embeddings from `vec_db`. Retrieval
  reads the vector store first, so a deleted memory stays retrievable
  while the delete API still answers success".
  https://github.com/MemTensor/MemOS/issues/2331,
  https://github.com/MemTensor/MemOS/pull/2332 and
  https://github.com/MemTensor/MemOS/pull/2533, accessed 2026-11-20. How
  close: a second carrier, the vector, survives the delete, as in Mem0
  #3245, in the system of O6. Not confirmed fixed: no fix was merged as
  read.

- **T. Mem0, stale links in the entity index.** mem0ai/mem0 issue #7226,
  "Entity-index cleanup is skipped in any process that has not written
  entities, so deletions leave permanent stale links", opened
  2026-09-04, open. "a deletion performed by a worker that only deletes
  leaves the entity index pointing at a memory that no longer exists";
  "The method returns normally: no exception, no warning, no counter."
  https://github.com/mem0ai/mem0/issues/7226, accessed 2026-11-20. How
  close: silent residue in a derived index; whether it reaches a read
  was not checked.

- **T. Graphiti, a deleted fact in a summary.** getzep/graphiti issue
  #1837, "[BUG] remove_episode leaves a deleted fact in a surviving
  entity summary after restart", opened 2026-09-05; fixed by pull
  request #2025, "fix(core): keep restated facts and rebuild summaries
  in remove_episode", merged 2026-10-19, whose body says "Fixes #1837".
  "A returned entity summary should agree with the surviving facts, or
  be invalidated"; "The summary is identical before removal and after
  removal plus client reconstruction." graphiti-core 0.30.1, Neo4j
  5.26.2. A later comment reports the same symptom when a fact is
  deleted directly: "We hit this in production (Neo4j + MCP server)".
  https://github.com/getzep/graphiti/issues/1837 and
  https://github.com/getzep/graphiti/pull/2025, accessed 2026-11-20. How
  close: derived text, a summary, carries the deleted fact: the case our
  Graphiti scrub blanks (`GRAPHITI_BACKEND.md:263`).

- **T. Graphiti, deleting too much.** getzep/graphiti issue #2024,
  "[BUG] remove_episode deletes a fact that another episode still
  supports", opened 2026-10-17 by a bot account, fixed by the same pull
  request #2025. "The method does not check the other entries in
  `edge.episodes`." https://github.com/getzep/graphiti/issues/2024,
  accessed 2026-11-20. How close: the opposite error, more deleted than
  asked, which Bemula also reports.

- **T. Graphiti, bulk episodes that a delete cannot find.**
  getzep/graphiti pull request #2030, "fix(core): record supported edges
  on episodes in add_episode_bulk", merged 2026-10-19.
  "`add_episode_bulk` saved each episode with `entity_edges=[]`.
  `remove_episode` reads `episode.entity_edges` to find the facts of an
  episode. Thus `remove_episode` did not remove the facts of an episode
  from bulk ingestion." "The change does not repair stored data."
  https://github.com/getzep/graphiti/pull/2030, accessed 2026-11-20. How
  close: a write path that left nothing for a later delete to find;
  stored data stays affected.

- **A. Open WebUI, a delete undone by a later write.** CVE-2026-44570
  (condition 7): "The `DELETE /api/v1/memories/{memory_id}` can also be
  used by any user to delete an existing memory. Deleted memories can
  then be restored by calling the `POST
  /api/v1/memories/{memory_id}/update` endpoint again."
  https://github.com/open-webui/open-webui/security/advisories/GHSA-hmjq-crxp-7rjw,
  accessed 2026-11-20. How close: a later write brings a deleted memory
  back, what our deletion forbids ("no later write brings one back",
  `DELETION_AND_SUPERSESSION.md:102-106`); here through an update path
  with no owner check.

- **V. Caura (MemClaw), a delete that keeps the row.** The service S1
  measures; its integration guide (`static/docs/integration-guide.md` on
  main, https://github.com/caura-ai/caura-memclaw): `caura_manage` with
  "`op=delete` soft-deletes"; "Soft-deleted rows (`include_deleted=true`
  on `GET /memories`, `GET /memories/stats`, `caura_list`,
  `caura_stats`) and `POST /ingest/undo/{run_id}` need level 3 for an
  agent credential"; a nightly job "Purges": "soft-deleted memories past
  the tenant's retention window are removed", and "A deployment that
  does not run `core-operations` runs none of these." Accessed
  2026-11-20. How close: a deleted row stays in the store, readable by
  an agent at trust level 3, until a purge after the tenant's retention
  window; our forget deletes the rows and keeps a tombstone
  (`DELETION_AND_SUPERSESSION.md:160-182`). A documented design, not a
  failure report.

- **V. OpenAI, deleting a remembered fact.** OpenAI Help Center, "Memory
  in ChatGPT". Requested
  https://help.openai.com/en/articles/8590148-memory-faq, served at
  https://help.openai.com/en/articles/8590148-memory-in-chatgpt; the
  page said "Updated: 19 hours ago" when read. "Deleting a chat alone
  does not necessarily delete a separate saved memory created from that
  chat." "To remove information saved as a memory, delete the saved
  memory and the chat where you first shared it. Also remove the
  information from any other sources where it appears". "OpenAI may
  retain logs of deleted saved memories for up to 30 days for safety and
  debugging purposes." Accessed 2026-11-20. How close: the vendor
  documents that one fact has several carriers and leaves deleting each
  to the user; our forget removes every carrier in one request.

- **P. Benchmarks that measure it.** Bemula (B10): "no system passes
  more than 1.5% of forget requests end to end", and "These systems
  either leave the requested information extractable under simple
  attacks or delete far more than requested." MemCut (B11): "39-76%
  residual recovery" after LLM-guided deletion of ten additional turns.
  MemLeak (B12): "current memory systems usually delete the text entry
  and report success". GateMem (B6) checks forgetting at the interface
  only and "does not certify physical erasure". How close: deletion
  failures measured by answers and residual objects, for one user's
  memory; ours adds several writers' rows and a check of the store.

- **P. Agentic unlearning.** "Agentic Unlearning: When LLM Agent Meets
  Machine Unlearning". Bin Wang, Fan Wang, Pingping Wang, Jinyu Cong,
  Yang Yu, Yilong Yin, Zhongyi Han, Benzheng Wei. arXiv:2602.17692, v1 6
  Feb 2026, v2 28 Feb 2026, cs.LG. https://arxiv.org/abs/2602.17692,
  accessed 2026-11-20. Read: abstract. It names "parameter-memory
  backflow, where retrieval reactivates parametric remnants or memory
  artifacts reintroduce sensitive content". How close: content that
  comes back after deletion, our "no later write brings one back", with
  model parameters as a second store.

- **T. Related, supersession: Mem0 keeps both values.** mem0ai/mem0
  issue #4896, "ADD-only architecture doesn't implement conflict
  resolution for semantically similar memories", opened 2026-04-20,
  closed as not planned 2026-04-21. With mem0 2.0.0, "My name is
  liguoyu" and then "My name is liguosong" were both stored. The closing
  reply: "Both memories being stored is intentional", and "Closing as
  the behavior is by design in v3."
  https://github.com/mem0ai/mem0/issues/4896, accessed 2026-11-20. How
  close: not deletion: a stale value kept by design, which our
  supersession (responsibility 6) retires.

- **P. Related, supersession: revoked facts returned first.** B13: on
  Graphiti by default, and on Mem0 with its shipped read-time filter
  disabled, the revoked fact was returned in every scenario, 81 of 81
  each, ranked above its replacement, and agents acted on it in 358 of
  810 trials on Graphiti and 341 of 810 on Mem0 so configured.
  https://arxiv.org/html/2609.08258v1, accessed 2026-11-20. How close:
  not deletion: the stale value our supersession retires (responsibility
  6), returned by two of our backends used as that study configured
  them; versions not stated as read (B13).

- **Not found.** An instance in which a deletion asked through one agent
  left the fact in another agent's rows. The instances are one system's
  own carriers: graph, index, summary, chat, vector, and rows kept on
  purpose (soft delete). Searched (2026-11-20): a deletion in one
  agent's memory that another agent's copy survives; a delete that
  answers success while the memory stays retrievable. The results were
  papers and vendor pages about one system's deletion; the leads not
  already here are under "Not verified".

## Our docs' own citations, checked

- **`HETEROGENEITY.md:144-147`, V2's grounding**, cites "Cross-user
  contamination in multi-agent memory (Yang et al. 2026)". The paper
  (2604.01350, condition 7) studies one agent serving several users
  through state shared on purpose, and benign artifacts misapplied. It
  is not about multi-agent memory or identity conventions.

- **`HETEROGENEITY.md:172-174`, V3's grounding**, cites "Agents that
  skip access control (the motivation of Collaborative Memory and
  SSGM)". Collaborative Memory's motivation (A1) is that most approaches
  "assume a monolithic, single-user context" (abstract), and that an
  earlier shared pool "still overlooks user-level privacy or access
  constraints" (§2, Related Work, full text). SSGM's (A5) is "critical
  concerns regarding memory governance, semantic drift, and privacy
  vulnerabilities". Neither documents agents that skip access control.

- **`STRESS_DIMENSIONS.md:540-541`** cites AgentPoison (Chen et al.
  2024) for memory poisoning: it matches the paper (condition 6).

- **`STRESS_DIMENSIONS.md:357`** cites Terry et al. 1994: not checked
  (before this job's dates).

## Not found

- **One policy layer against the same logic in each agent.** No paper,
  system or report compares them. Searched (2026-11-20, extended
  search): centralized against per-agent memory access control in
  multi-agent LLM systems, shared-memory comparisons. The nearest: S1
  (one layer, no comparand), O2 (argued, no experiment), S12 (plans, not
  memory policy), B7 (topology and memory regime, with the policy left
  to the models), A17 (enforcement outside the model against
  instructions, for tools) and B13 (a guard against a store filter, for
  revoked facts).

- **Per condition.** Identity mismatch: no measurement of how often
  agents tag the wrong user. Missing metadata: no measurement of agents
  omitting ownership or sharing fields. Version skew: no case of two
  agents on different library versions writing one store. Per-agent
  tuning: no incident or measurement of agents sharing a store with
  different retrieval settings; one service documents them as a feature
  (Caura). Concurrent writers: no production report of a cross-agent
  read that missed an accepted write (S1 measured none under strong
  mode). Flooding: no measurement of a benign flood across agents, and
  no evaluation of a per-writer quota. Cross-user contamination: no
  measured case caused by a write misfiled under another user's id; two
  merged fixes document the mechanism (Mem0 #6278, Hermes #5895).
  Incomplete deletion: no case of a deletion through one agent that left
  another agent's rows.

## Not verified

- **Vertex AI Agent Engine Memory Bank.** Two URLs for its overview
  redirected to an unrelated page ("Scale your agents | Gemini
  Enterprise Agent Platform"). Its scope and access rules are left out.

- **Surveys, leads only.** "Memory for Autonomous LLM Agents:
  Mechanisms, Evaluation, and Emerging Frontiers" (arXiv:2603.07670) and
  "Memory in the Age of AI Agents" (arXiv:2512.13564) came up in the
  search for the first "Not found" item; the search tool's summary
  attributes to one of them that frameworks either share all memory or
  keep a store per agent. Neither was read. The earlier attempt's notes
  name two more (arXiv:2604.16548, arXiv:2609.30909), not read.

- **Venue pages.** G-Memory's NeurIPS 2025 page and MINJA's NeurIPS 2025
  poster appear in the earlier attempt's search listings and were not
  fetched; the entries give only what the arXiv pages say. The
  OpenReview pages of S10, A8 and A9 were not fetched.

- **Issues named but not read.** Mem0 #6998 and #6867 (named in #7072);
  Mem0 #6277 (closed by #6278); deer-flow #3123 (named in S21); from the
  earlier attempt's search listings, Mem0 #7598, #7202, #4232, #7715,
  #4863 and #6531, and Graphiti #1489 and #2165.

- **Leads from this revision's searches for conditions 7 and 8, not
  read.** "Can Agents Truly Forget? Explore Machine Unlearning for LLM
  Agents" (arXiv:2610.17659; the title as the search listing gives it)
  and arXiv:2606.10062 (title not seen), which the search tool's summary
  connects to deletion residue and tombstone redaction; and Anthropic's
  API reference for deleting a memory from a memory store, which the
  summary says does not delete the memory's versions. None was fetched,
  so none is cited.

- **The Asana MCP server incident of June 2025.** The earlier attempt's
  notes say only secondary coverage was found; it was not searched
  again, and it concerns tool access, not agent memory.

- **The pinned backends.** Whether mem0ai 2.0.2 (`requirements.txt:41`)
  and graphiti-core 0.31.2 (`requirements.txt:45`) have the behaviors of
  Mem0 #5160, #6515, #4453 or #6278, of Graphiti #1837, or the
  revocation results of B13 was not checked. Where a bug is fixed or
  absent in the pinned version, our runs do not meet it.

- **Issue texts.** What an issue says is its author's report. A behavior
  counts as confirmed here only where a maintainer replied or a fix was
  merged, and each entry says which.

## Open decisions

1. **The workshop paper.** How the main-track paper cites S18, and
   whether review requires anonymizing it. Bears on the related-work
   section and any novelty claim.

2. **Run, not only cite.** Options: (a) cite only; (b) run our probes on
   an external benchmark's data, such as GateMem's access-control and
   forgetting checkpoints (B6), MUMBench (A2), StateMemBench (B5) or
   Bemula (B10); (c) build one external design as an extra condition,
   such as an ownership gate after pooled retrieval (A9). Bears on how
   our results relate to S1 and A2, which have no comparand with the
   logic in each agent.

3. **Our groundings.** `HETEROGENEITY.md:144-147` and `:172-174` cite
   papers for claims they do not make. Options: keep; reword; replace
   with part (b) instances (for example, for V2's effect, Hermes #38424,
   a scope convention rather than a user-id one, or the n8n with Zep
   report; for V3, Mem0 #5160, mcp-memory-ts or our own Zep provider).
   Bears on the heterogeneity section's motivation.

4. **Issue reports as evidence.** Options: cite user-filed issues; cite
   only maintainer-confirmed ones; cite only papers, advisories and
   vendor documents. Bears on how much of part (b) the paper can use.

5. **The pinned backends.** Whether to check mem0ai 2.0.2 and
   graphiti-core 0.31.2 against the issues of part (b) and the
   revocation results of B13 before citing them as motivation. Bears on
   whether the paper may say our backends have these failures.

6. **The entries read at abstract level.** Most entries added in this
   revision (S19, S20, S22, S23, A15, A17, O10 and B14 to B17) were read
   at abstract level only. Options: cite them as read; read the full
   text of the ones the paper will cite. Bears on any statement that a
   work does not do something.
