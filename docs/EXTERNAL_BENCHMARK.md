# External benchmark: a published memory benchmark, split across agents

A spec, written on 2026-11-20 during Subtask 20, before any code. It
asks whether a published long-term-memory benchmark, built for one
assistant, can be replayed through our three loci as a multi-agent
benchmark: which one, how its sessions are split across writer agents,
how its questions map to our probes, what is scored, and what it
costs. Nothing in it has run: no kernel, no model, no judge. It is not
a pre-registration: the subtask that runs it writes its cells and its
rules first, as `FULL_GRID.md` says of the grid.

**How to read the numbers.** "Counted" means counted here, on
2026-11-20, from the released file named with it (its sha256 is given
where the file is introduced), by a one-off script that is not
committed; each count states its rule. "Computed" is arithmetic on
figures given beside it. A source is cited by its key in "Sources". A
price or a time of ours names the stored run it comes from. An
extrapolation says so.

**Terms** (ours). A locus is where the memory logic runs: `kernel`
(one policy instance between the agents and the store), `replicated`
(each agent runs the kernel's library itself) or `native` (each agent
uses the backend as its documentation shows); `REPLICATED_LOGIC.md`,
`NATIVE_USAGE.md`. Writers are agents that store what the user tells
them. The consumer, `assistant_agent`, answers from the block, the
memory text injected into its turn. H is how many agents deviate from
the reference build (`HETEROGENEITY.md`). The matcher is the exact
rule that scores our probes (`METRICS.md`, "Conventions"). "Amendment
n" is `BENCHMARK_V2.md`'s.

## Why an outside benchmark

Our benchmark is ours. `BENCHMARK_V2.md` ("What v2 does not show")
lists what follows from that: the writers are scripted, a user has four
probed slots and one private fact, and the 150 users are built on
`users_v1`. Two more properties are by design: every probed value is a
distinctive proper name, so that exact matching suffices
(`BENCHMARK_V2.md`, "Facts"), and a user's history is short: 15 to 23
events, mean 18.44 (counted from Cerebrum
`benchmarks/shared_memory/data/users_v2.jsonl`, revision 4, sha256
`64d5e4fc…`).

An outside benchmark can add what we cannot give ourselves: histories
and questions we did not write, in ordinary language, and stores an
order of magnitude larger. It cannot test what only our script
contains: a revoked fact, a private fact, a labelled slot. So it is a
second source of questions for the locus comparison, not a replacement
for any probe.

## Sources

All accessed 2026-11-20. A repository's last commit and its date are
the GitHub API's (`/repos/<owner>/<repo>/commits`).

| Key | What | URL | Read |
|---|---|---|---|
| S1 | LoCoMo paper (Maharana et al.; arXiv v1, 2024-02-27; ACL 2024 by its repository's README) | https://arxiv.org/abs/2402.17753 | abstract page, HTML full text |
| S2 | LoCoMo repository (last commit `3eb6f2c`, 2024-08-13) | https://github.com/snap-research/locomo | `README.MD`, `LICENSE.txt`, `data/locomo10.json`, `task_eval/evaluation.py`, `task_eval/gpt_utils.py`; issues 2, 6, 23, 27 (with its comments), 35, 43, 44 and 45 |
| S3 | LongMemEval paper (Wu et al.; arXiv v2, 2025-03-04; ICLR 2025) | https://arxiv.org/abs/2410.10813 | abstract page, HTML full text |
| S4 | LongMemEval repository (last commit `9e0b455`, 2026-05-11) | https://github.com/xiaowu0162/LongMemEval | `README.md`, `LICENSE`, `src/evaluation/evaluate_qa.py`, `src/evaluation/print_qa_metrics.py`, `src/evaluation/print_retrieval_metrics.py`, `src/retrieval/eval_utils.py`, `src/generation/run_generation.py` |
| S5 | LongMemEval data on the Hugging Face Hub: the cleaned release (revision `98d7416`, 2025-09-19) and the deprecated first release | https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned and https://huggingface.co/datasets/xiaowu0162/longmemeval | both cards; the cleaned release's file list with sizes and sha256 (the Hub API); `longmemeval_oracle.json` and `longmemeval_s_cleaned.json`, downloaded, each matching the sha256 the Hub lists at the revision |
| S6 | LongMemEval-V2 repository (created 2026-05-11; Apache-2.0) | https://github.com/xiaowu0162/LongMemEval-V2 | `README.md` |
| S7 | Mem0 paper (Chhikara et al.; arXiv v1, 2025-04-28) | https://arxiv.org/abs/2504.19413 | abstract page, HTML full text |
| S8 | Mem0's 2025 LoCoMo evaluation code, at the commit S12 cites (`2b58775`) | https://github.com/mem0ai/mem0/tree/2b58775c17eb1c1b7532242b7154af6744102280/evaluation | `src/memzero/add.py`, `metrics/llm_judge.py`, fetched at the commit |
| S9 | Mem0's benchmark repository (last commit `4b61c5d`, 2026-05-13) | https://github.com/mem0ai/memory-benchmarks | `README.md`, `benchmarks/locomo/prompts.py`, `benchmarks/longmemeval/run.py`, `results/platform/locomo_results.json`, `results/platform/longmemeval_results.json`, `results/oss/longmemeval_gpt5.json` |
| S10 | Zep paper (Rasmussen et al.; arXiv v1, 2025-01-20) | https://arxiv.org/abs/2501.13956 | abstract page, HTML full text |
| S11 | Zep's blog post on Mem0's paper (2025-05-06, corrected; the page says updated 2026-06-03) | https://www.getzep.com/blog/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/ | the page |
| S12 | Zep's papers repository: issue 5 (Mem0's co-founder and CTO, 2025-05-08), Zep's reply (2025-05-12), and the last commit (`4b7f26c`, 2025-07-11, "fix category mapping") | https://github.com/getzep/zep-papers/issues/5 | the issue, its three comments, the commit's diff; at `4b7f26c`, `kg_architecture_agent_memory/locomo_eval/`: `README.md`, `zep_locomo_responses.py`, `zep_locomo_eval.py` |
| S13 | Zep's blog post on retrieval size (2025-12-09) | https://www.getzep.com/blog/the-retrieval-tradeoff-what-50-experiments-taught-us-about-context-engineering/ | the page |
| S14 | Zep's benchmark page (undated) | https://www.getzep.com/research/memory-benchmarks/ | the page |
| S15 | A-MEM paper (Xu et al.; arXiv v11, 2025-10-08; NeurIPS 2025) | https://arxiv.org/abs/2502.12110 | abstract page, HTML full text |
| S16 | A-MEM's reproduction repository, `WujiangXu/AgenticMemory`, now `WujiangXu/A-mem` (GitHub redirects; last commit `f9a173d`, 2026-10-28) | https://github.com/WujiangXu/AgenticMemory | `README.md`; commit `b31a1dd` and pull request 31, both of 2026-10-22, by the repository's owner, `WujiangXu`; issue 29 |
| S17 | FlexA-Mem paper (Xu et al.; arXiv v1, 2026-10-23), by A-MEM's first author | https://arxiv.org/abs/2610.33274 | abstract page, HTML full text |
| S18 | LightMem paper (Fang et al.; arXiv v4, 2026-02-28; ICLR 2026) | https://arxiv.org/abs/2510.18866 | abstract page, HTML full text |
| S19 | "Memory in the LLM Era" (Wu et al.; arXiv v3, 2026-08-06) | https://arxiv.org/abs/2604.01707 | abstract page, HTML full text |
| S20 | Mem0 repository, issue 3944, "Failed to reproduce the accuracy on LOCOMO via Mem0 platform" (opened 2026-01-28, closed 2026-03-27) | https://github.com/mem0ai/mem0/issues/3944 | the issue and its two comments (the GitHub API) |

**Not fetched, or not verified.**
- LongMemEval's M file (2.7 GB): only its size and sha256 (S5). Its
  figures below are the paper's and the README's.
- The statistics image in LoCoMo's README: the counts below are from
  the file.
- The change log of LongMemEval's cleaning, a spreadsheet the README
  and the card link.
- Tokens: no tokenizer was run here (it would fetch its vocabulary
  from the network). Sizes are in words. Every token figure is its
  source's, or the library's estimate of 1.3 tokens a word
  (`aios/memory/pipeline/formatter.py`, `estimate_tokens`).
- Which LoCoMo file the A-MEM paper's runs used: its text gives the
  first release's figures (9K tokens, up to 35 sessions, 7,512
  questions), its reproduction README runs `data/locomo10.json` (S15,
  S16). The repository's correction says the paper's numbers used its
  pipeline's earlier scoring and counts 446 category-5 questions, the
  released file's number (S16, commit `b31a1dd`), so the released file
  is the likelier.
- Which LoCoMo file S18 used (it describes the first release: "roughly
  300 turns and around 9K tokens"), and how many questions S18 and S19
  scored: neither gives a count. S19 describes 198.6 questions, 27.2
  sessions and 588.2 turns a conversation: the released file's figures,
  category 5 included (counted).
- Which LongMemEval file S17, S18 and S19 used. S19 describes 50.2
  sessions a question where the cleaned S file has 47.7 (counted), so
  S19 may be on the first release; S17 describes "about 48 sessions".
- The models behind the platform figures in Mem0's README: the README
  does not name them; its result files name GPT-5 (S9).
- How LightMem feeds a session to each system it compares, and which
  roles it stores (S18): not found in its text.
- How Zep's page forms its four LoCoMo categories (S14).
- The model version of our Azure `gpt-4o` deployment: the config was
  not read.
- How much of a long row our embedder reads: the kernel's embed call
  sets no context length (`aios/memory/embedding.py`,
  `Embedder.embed`), so it is Ollama's default for the model, not
  checked here.
- BEAM, a third benchmark in S9, and the outside statements quoted in
  LoCoMo's issue comments: seen by name only.

## LoCoMo

**Size.** Two releases.
- The paper's: 50 conversations; on average 19.3 sessions, 304.9 turns
  and 9,209.2 tokens a conversation; 7,512 questions (S1, Tables 1 and
  5).
- The repository's, `data/locomo10.json` (2,805,274 bytes, sha256
  `79fa87e9…`): 10 conversations, "a subset of the conversations
  released previously", sampled "to retain the longest conversations
  with high-quality annotations" (S2, README). Counted (sessions are
  the `session_<n>` keys, words are whitespace-separated words of
  `text`): 272 sessions (19 to 32 a conversation, mean 27.2), 5,882
  turns (369 to 689, mean 588.2), 133,772 words (8,019 to 16,165 a
  conversation; 22.7 a turn), 1,226 turns with an image caption
  (`blip_caption`), 910 of them with `img_url`, 1,986 questions (105
  to 260 a conversation). Mem0's paper gives "26000 tokens on average"
  (S7).

The results below that give a question count give 1,540, this file's
categories 1 to 4 (S9, S14, S17; S18 and S19 name four categories and
give no count).

**Record.** One object per conversation (S2, README): `sample_id`;
`conversation` (the names `speaker_a` and `speaker_b`; each session as
`session_<n>` with `session_<n>_date_time`, the numbers giving the
chronological order; a turn has `speaker`, `dia_id` such as `D3:5`,
`text`, and for an image `blip_caption`); generated `observation` and
`session_summary`; annotated `event_summary`; and `qa`, each item with
`question`, `answer`, `category` and `evidence` (dia ids). The README
says an image turn also has `img_url` and `query`; of the 1,226 turns
with a caption, 910 have `img_url` and 888 also `query` (counted). The
images are not released.

**License.** One file for data and code, `LICENSE.txt`:
"Attribution-NonCommercial 4.0 International", CC BY-NC 4.0. The
paper's Appendix B.2: "The LoCoMo dataset will be released under the
CC BY-NC 4.0 DEED license." Non-commercial use only.

**Question types.** The paper numbers its five types (1) single-hop
to (5) adversarial (S1, section 4.1), but does not tie these numbers
to the file's `category`, and they are not its coding: under the
mapping below only 5 coincides. A-MEM's paper repeats the numbered
list, while its Table 1's columns follow the file's codes (S15,
section 4.1 and Table 1). The README names a `category` label and
does not map it. Issue 6 has asked since 2025-05-02, is open, and has
no answer from a maintainer (S2). The mapping below is
the one A-MEM's README and Mem0's 2026 code state (S16; S9,
`benchmarks/locomo/prompts.py` lines 25 to 31). LoCoMo's own code
agrees where it says anything: `task_eval/evaluation.py` comments
category 1 as multi-hop and 5 as adversarial (lines 212 to 217), and
the reader adds a date instruction to category 2 only
(`task_eval/gpt_utils.py` lines 243 and 244).

| Category | Type | Paper, 50 conversations | Released file, counted | Sessions holding the evidence, counted |
|---|---|---:|---:|---|
| 4 | single-hop | 2,705 | 841 | one in 840 |
| 1 | multi-hop | 1,104 | 282 | two or more in 270 |
| 2 | temporal | 1,547 | 321 | one in 293 |
| 3 | open-domain knowledge | 285 | 96 | one in 58; none listed in 4 |
| 5 | adversarial | 1,871 | 446 | one in 446 |
| | total | 7,512 | 1,986 | |

**Session and speaker.** Two named people talk to each other. There is
no assistant and no single user. Both speakers are LLM agents, each
with a persona and a timeline of events; annotators then edited
"nearly 15% of the dialog turns" (S1, section 3). A session is one
dated chat between the two. A question is in the third person, about
either speaker ("When did Melanie run a charity race?").

**Metric and protocol.** Judge-free, by their code (S2):
- the score is an F1 over stemmed tokens after normalization (commas,
  punctuation, the articles and "and" removed, lowercased):
  `evaluation.py` lines 75 to 92 and 126 to 138;
- a multi-hop answer is split at commas and the parts' F1 averaged
  (lines 141 to 145, 212 to 214); an open-domain answer keeps its part
  before the first `;` (lines 203 and 204); an adversarial question
  scores 1 when the output holds "no information available" or "not
  mentioned" (lines 216 to 221);
- the reader is asked for "a short phrase", "with exact words from the
  context whenever possible" (`gpt_utils.py` lines 25 to 29); a
  temporal question gets the suffix "Use DATE of CONVERSATION to
  answer with an approximate date." (line 244); an adversarial one is
  a choice between two options (lines 245 to 256);
- retrieval runs also report the recall of the `evidence` ids
  (`evaluation.py` line 228 on).

The judged accuracy most papers now report on LoCoMo, "J", is not the
benchmark's. It is Mem0's: `gpt-4o-mini` labels an answer CORRECT or
WRONG and is told to "be generous with your grading" (S8,
`metrics/llm_judge.py` lines 11 to 52).

**Known problems**, each public.
- Category 5 cannot be scored as released: 444 of its 446 items have
  no `answer`, only `adversarial_answer` (counted; issue 2, open since
  2024-08-31), and the released reader code reads `qa['answer']` for
  it (`gpt_utils.py` lines 248 to 252). Mem0 and Zep leave it out (S7,
  S11). A-MEM's paper scored it, against the trap: its runners took
  `adversarial_answer`, the wrong option offered in the prompt, as the
  reference, so picking the trap scored high. A-MEM's repository
  corrected this on 2026-10-22 and keeps the paper's scoring as
  `--legacy_c5_reference` (S16, pull request 31, commit `b31a1dd`;
  issue 29, which reported it, is still open).
- Wrong gold answers: issue 27 and its comments, 35 and 44 list them
  (a wrong weekday, a statement credited to the wrong speaker, a book
  title that is in no turn). Issue 43 reports two category 5 questions
  that the transcript answers, issue 45 two evidence ids that name no
  turn. All are open; the last commit is of 2024-08-13 (S2). An audit
  posted in issue 27's comments (2026-02-18; an outside party's, not
  checked here) counts 99 score-corrupting gold errors among the 1,540
  questions of categories 1 to 4 (6.4%; 4.3% to 9.9% by category),
  which caps a correct reader at 93.6%; S14's 94.7% is above that.
- A conversation fits a context window. In Mem0's own table the reader
  given the whole conversation (26,031 tokens) scores 72.90 against
  Mem0's 66.88 (S7, Table 2).
- LongMemEval's comparison marks LoCoMo as covering abstention but not
  knowledge updates (S3, Table 1). Its abstention questions are
  category 5, the one that cannot be scored as released.

## LongMemEval

**Size.** 500 questions, each with a history of its own (S3, S4).

| Variant | File | Sessions a question | Turns a question | Text a question |
|---|---|---|---|---|
| S | `longmemeval_s_cleaned.json` (277,383,467 bytes, sha256 `d6f21ea9…`) | 38 to 62, mean 47.7 (counted) | 396 to 616, mean 493.5, of which the user's 244.8 (counted) | "roughly 115k tokens" for Llama 3 (S4); 78,427 words, of which the user's 10,613 (counted) |
| M | `longmemeval_m_cleaned.json` (2,737,100,077 bytes; S5) | "roughly 500" (S4) | not counted | "around 1.5 million tokens" (S3) |
| oracle | `longmemeval_oracle.json` (15,388,478 bytes, sha256 `821a2034…`) | the evidence sessions only: 1 to 6, mean 1.90 (counted) | mean 21.9 (counted) | 4,239 words (counted) |

All of S: 23,867 sessions (19,195 distinct ids, since questions share
filler sessions), 246,750 turns, 39.2 million words (counted). Each
oracle history is its S history's evidence sessions, under the same
ids (500 of 500, counted).

The files changed once. Since 2025-09 the "cleaned" files replace the
first release; the new card says it "removes noisy history sessions
that interfere with the answer correctness" (S4, S5). A result from
before then, such as Zep's paper's, is on the first release.

**Record.** `question_id` (ending in `_abs` for an abstention
question), `question_type`, `question`, `answer`, `question_date`,
`haystack_session_ids`, `haystack_dates`, `haystack_sessions` (each a
list of turns `{role, content}`; an evidence turn also has
`has_answer: true`) and `answer_session_ids` (S4, README). The README
says the S and M histories are sorted by timestamp. In the cleaned S
file 211 of the 500 are not, within a day only: every pair of
adjacent sessions out of date order is on one calendar day (3,167 of
3,167), so the days are in order and the times of day are not. In 76
the question's date is before some session's, by less than 24 hours
(counted). Their reader sorts the sessions it is given by date (S4,
`src/generation/run_generation.py` lines 224 and 225).

**License.** MIT, for the code (`LICENSE`) and for the data (both
cards: `license: mit`; S4, S5; the paper planned it, S3). The filler
sessions come from ShareGPT (Apache 2.0) and UltraChat (MIT), as the
paper states them (S3).

**Question types** (counted from the oracle file; an abstention
question keeps the type it was made from; the paper counts abstention
as a seventh type, S3, Figure 1):

| Type | Questions | Abstention among them | Evidence sessions | Evidence turns flagged: user, assistant |
|---|---:|---:|---|---|
| single-session-user | 70 | 6 | 1 | 64, 2 |
| single-session-assistant | 56 | 0 | 1 | 5, 51 |
| single-session-preference | 30 | 0 | 1 | 44, 0 |
| knowledge-update | 78 | 6 | 2 | 144, 0 |
| multi-session | 133 | 12 | 2 to 5 | 326, 1 |
| temporal-reasoning | 133 | 6 | 1 to 6 | 259, 0 |
| total | 500 | 30 | one: 176 questions; two: 250; three to six: 74 | 842, 54 |

**Session and speaker.** One user and one assistant. A session is one
timestamped chat between them, a list of turns whose `role` is `user`
or `assistant`; a round is a user turn and the reply. People wrote the
questions and the evidence statements; an LLM simulated the evidence
sessions from them, and people screened and edited those (S3, section
3.2). The other sessions are drawn from ShareGPT, UltraChat and
simulated sessions about other attributes, 25%, 25% and 50% (S3,
Appendix A.2). The user asks the question, in the first person, after
the last session.

**Metric and protocol.** Judged, by their code (S4):
- `evaluate_qa.py` maps `gpt-4o` to `gpt-4o-2024-08-06` (lines 11 to
  15) and asks it, at temperature 0 and at most 10 tokens, "Is the
  model response correct? Answer yes or no only."; a reply that
  contains "yes" is correct (lines 101 to 113);
- the prompt depends on the type (lines 24 to 43). The general one
  says yes to a response that contains the answer, or all the steps to
  it, and no to one that has "only ... a subset of the information";
  temporal-reasoning forgives an off-by-one count of days, weeks or
  months; knowledge-update accepts a response that also names the old
  value "as long as the updated answer is the required answer";
  single-session-preference checks the response against a rubric; an
  abstention question is correct when the model "correctly identifies
  the question as unanswerable";
- reported: accuracy per type, the mean over types, the overall
  accuracy and the abstention accuracy (`print_qa_metrics.py` lines 16
  to 33, which refuse a log judged by any other model: line 20);
- the paper reports more than 97% agreement of this judge with human
  experts (S3, section 3.3). That is an average over 30 long-context
  answers a type, from `gpt-4o` and from Llama 3.1 8B; the worst is
  0.90 (27 of 30), on single-session-preference with `gpt-4o`'s
  answers and on abstention with Llama's, where the paper says the
  judge "slightly deviates from human experts" (S3, Appendix A.4,
  Table 6).

Judge-free, beside it: the recall and NDCG of the evidence among the
retrieved items, by session and by turn (`recall_any@k`,
`recall_all@k`, `ndcg_any@k`: `src/retrieval/eval_utils.py`), with the
abstention questions left out (`print_retrieval_metrics.py` line 12).

**Known problems.** The cleaning and the order, above. A history
belongs to one question, so a system stores about 494 turns to answer
one question (cost, below). A successor exists since 2026-05,
LongMemEval-V2, on histories of web-agent trajectories (S6): another
task, not considered here.

## Published results

A number is the named party's. Unless a row says otherwise, LoCoMo
numbers are over categories 1 to 4, which in the released file hold
1,540 questions: S9, S14 and S17 give that count, S7 the file's ten
conversations, and S11, S12, S13, S18 and S19 no count. LongMemEval
numbers are over the 500 questions of S unless a row says otherwise.
"J" is Mem0's judged accuracy (above); "Acc" and "ACC" are each
source's own judged accuracy; F1 is a token F1.

**LoCoMo.**

| System | Result | Reported by | Where | Model and settings |
|---|---|---|---|---|
| Mem0 | J 66.88 ± 0.15; with graph memory 68.44 ± 0.17; the whole conversation as context 72.90 ± 0.19 | Mem0's authors | S7, Table 2 | Mem0's hosted platform, with extraction instructions written for these conversations (S8, `src/memzero/add.py`; "Disputes" below); `gpt-4o-mini` for every call and as the judge (S8, `metrics/llm_judge.py` line 39); 10 runs; 1,764 context tokens a question (3,616 with the graph) |
| Mem0 | 92.5% (1,425 of 1,540); the repository's result file holds 1,410 of 1,540 (91.6%) | Mem0 | S9, README and `results/platform/locomo_results.json` | the platform's "v3" pipeline; 200 memories retrieved; the result file names GPT-5 on Azure as reader and judge |
| Mem0 | ACC 61.69 | LightMem's authors | S18, Table 3 | `gpt-4o-mini` as backbone and judge; four categories, the question count not stated |
| Mem0 | Acc 62.86, F1 34.55 | Wu et al. | S19, Table 4 | Qwen3.5-9B backbone, `all-MiniLM-L6-v2` embedder; judge GPT-5.4-mini; four categories, the question count not stated |
| Zep | J 65.99 ± 0.16 | Mem0's authors | S7, Table 2 | Zep's platform as Mem0 set it up; `gpt-4o-mini`; 3,911 context tokens |
| Zep | 75.14 ± 0.17 | Zep | S11; S12, reply of 2025-05-12 | Zep's own answer prompt; `gpt-4o-mini` answers and grades, at temperature 0, in Zep's released code beside the result (S12, at `4b7f26c`: `zep_locomo_responses.py` line 63, `zep_locomo_eval.py` line 52); 10 runs; replaces a first claim of 84% |
| Zep | 58.44 ± 0.20 | Mem0's CTO | S12 | Zep's evaluation code with Mem0's system prompt; Zep disputes it |
| Zep | 80.32 ± 0.43 with 1,997 context tokens; 77.06 ± 0.41 with 756; 69.62 ± 0.47 with 347 | Zep | S13 | `gpt-4o-mini` answers and grades; 10 runs each; the question count is not stated |
| Zep | 94.7% (1,459 of 1,540) | Zep | S14 | `gpt-5.4` (reasoning medium) reads, `gpt-5.4` judges with chain-of-thought grading; median context 5,760 tokens |
| Zep, the open-source code of its paper | Acc 77.84, F1 42.89 | Wu et al. | S19, Table 4 | Qwen3.5-9B; judge GPT-5.4-mini; built on Graphiti, by S19's account (Appendix H); four categories, the question count not stated |
| A-MEM | F1 by type: multi-hop 27.02, temporal 45.85, open-domain 12.14, single-hop 44.65, adversarial 50.03 | A-MEM's authors | S15, Table 1 | `gpt-4o-mini`; k 10, adjusted per category; no judge; adversarial scored against the trap option (`adversarial_answer`), which A-MEM's repository corrected on 2026-10-22, keeping the paper's scoring as `--legacy_c5_reference` (S16, pull request 31, commit `b31a1dd`) |
| A-MEM | J 48.38 ± 0.15 | Mem0's authors, their re-run | S7, Table 2 | `gpt-4o-mini`, temperature 0; 2,520 context tokens |
| A-MEM | ACC 64.16 | LightMem's authors | S18, Table 3 | `gpt-4o-mini` as backbone and judge; four categories, the question count not stated |
| A-MEM | Acc 52.21, F1 27.62 | Wu et al. | S19, Table 4 | Qwen3.5-9B; judge GPT-5.4-mini; four categories, the question count not stated |
| A-MEM | J 45.5, 55.8 and 68.8 with a reader budget of 2k, 4k and 8k tokens | A-MEM's first author, in a later paper | S17, Table 1 | GPT-5.4 mini; Mem0's reader and judge prompts; judge Claude Sonnet 4.6 |

**LongMemEval.**

| System | Result | Reported by | Where | Model and settings |
|---|---|---|---|---|
| Zep | 63.8% with `gpt-4o-mini`, 71.2% with `gpt-4o`; the whole history in context 55.4% and 60.2% | Zep's authors | S10, Table 2 | Zep's service; the first release's S file (115k tokens a history); the 20 most relevant facts and entities, about 1.6k context tokens; readers `gpt-4o-mini-2024-07-18` and `gpt-4o-2024-11-20`; judge GPT-4o with the benchmark's prompts |
| Zep | 90.2% (451 of 500) | Zep | S14 | `gpt-5.4` reads and judges; median context 4,408 tokens |
| Zep, the open-source code of its paper | no result: building the memory did not finish in two days | Wu et al. | S19, Appendix H | 8 A100 GPUs; Qwen3.5-9B |
| Mem0 | 94.4% (472 of 500); the repository's result file holds 467 of 500 (93.4%) | Mem0 | S9, README and `results/platform/longmemeval_results.json` | the platform's "v3" pipeline; the cleaned S file, user and assistant turns added in pairs (`benchmarks/longmemeval/run.py` lines 91 to 96); 200 memories; the result file names GPT-5 |
| Mem0, open source, self-hosted | 91.0% with GPT-5 extracting; 88.6% to 89.8% with three open models | Mem0 | S9, README | GPT-5 answers and judges; 200 memories retrieved |
| Mem0 | ACC 53.61 with `gpt-4o-mini`, 39.51 with Qwen3-30B | LightMem's authors | S18, Table 2 | LongMemEval-S, the release not stated; judge `gpt-4o-mini` |
| Mem0 | F1 34.20 | Wu et al. | S19, Table 3 | Qwen3.5-9B; the table has no judged accuracy |
| A-MEM | none by its paper, whose second dataset is DialSim | | S15 | |
| A-MEM | 52.0, 71.6, 84.5 and 88.6 with a reader budget of 4k, 8k, 16k and 32k tokens, on 440 of the questions | A-MEM's first author, in a later paper | S17, Table 1 | GPT-5.4 mini; judge Claude Sonnet 4.6, the primary (GPT-5.4, the second judge, agrees on 96.2% to 99.0% of the answers); the other 60 questions chose the settings |
| A-MEM | ACC 62.60 with `gpt-4o-mini`, 65.20 with Qwen3-30B | LightMem's authors | S18, Table 2 | judge `gpt-4o-mini` |
| A-MEM | F1 26.81 | Wu et al. | S19, Table 3 | Qwen3.5-9B |

No number here is for Graphiti as its authors ship it. Zep's own
numbers are its service's. The one outside run, S19's, used "the
open-source implementation released for the Zep paper", which by S19's
account "incrementally updates a temporal knowledge graph through
Graphiti" (Appendix H, with a footnote to `getzep/graphiti`), inside
S19's own framework with Qwen3.5-9B. Building LoCoMo's index took
"several hours" there, and LongMemEval's did not finish in two days
(S19, Appendix H; 8 A100 GPUs, its setup). So S19's Acc 77.84 and F1
42.89 on LoCoMo are the one outside measurement of a Graphiti-based
memory here, and there is none on LongMemEval.

**Disputes, corrections and caveats.**
- **Zep on LoCoMo.** Mem0's paper gave Zep 65.99 (S7). Zep answered
  with 84%, which counted category 5's correct answers over a
  denominator without category 5, as Mem0's CTO reported with a re-run
  of 58.44. Zep corrected its number to 75.14, added a correction note
  to its post, and kept its criticism of Mem0's setup of Zep (S11,
  S12). Zep closed the issue "due to inactivity" on 2025-05-19, with
  the two numbers apart.
- **Mem0's platform run.** In 2026-01 a user ran Mem0's evaluation
  code (its `main` branch) on Mem0's platform with `gpt-4o-mini` and
  got an LLM score of "around 0.20". The platform had stored an event
  of May 2023 as "early January 2026", which the reporter read as the
  platform using the current date. The account of Mem0's CTO (the
  author of S12's issue) closed the issue on 2026-03-27 as "fixed
  now", with no new number (S20). So the 66.88 is the 2025 platform's:
  it depends on what the hosted platform did when it ran, not only on
  the pinned code (S8).
- **A-MEM's category 5.** A-MEM's paper scored category 5 against
  `adversarial_answer`, the trap option, so picking the trap scored
  high. Its repository corrected the scoring on 2026-10-22, saying that
  "This changes category-5 and overall averages", and keeps the paper's
  scoring as `--legacy_c5_reference` (S16, pull request 31 and commit
  `b31a1dd`). The adversarial 50.03 above is the paper's.
- **Mem0's instructions.** The extraction instructions of Mem0's 2025
  run name personal topics ("Identity and self-acceptance journeys",
  "Family planning and parenting") and give as their example "charity
  race for mental health" (S8, `src/memzero/add.py` lines 15 to 44).
  That phrase is turn D2:1 of the file's first conversation, which
  three of its questions ask about (counted).
- **Category names.** Mem0's paper prints A-MEM's published F1 of
  27.02, 12.14 and 44.65 under "Single Hop", "Multi-Hop" and "Open
  Domain"; A-MEM's own table has them under multi-hop, open-domain and
  single-hop (S7, Table 1; S15, Table 1). Zep's papers repository moved
  each of its four LoCoMo category scores to another category on
  2025-07-11 ("fix category mapping": 79.79% from temporal to
  single-hop, and the other three in turn; S12). Mem0's 2026 code uses
  the mapping of the table above (S9).
- **A README and its files.** Mem0's README and the result files
  beside it differ by about one point on both benchmarks (the rows
  above).
- **Zep's page.** Its four LoCoMo categories hold 670, 325, 323 and
  221 questions, 1,539 in all, and their correct answers sum to 1,436,
  against the headline's 1,459 of 1,540 (computed from S14's figures).
  The released file has 841, 321, 282 and 96 (counted). The page does
  not say how its categories are formed.
- LoCoMo's gold errors and category 5, and LongMemEval's cleaning, are
  above.

**What the numbers share.** Under one reader and one judge, the choice
among these three systems moves a number by up to about 26 points:
Zep − A-MEM is 25.63 on LoCoMo (S19, Table 4, Qwen3.5-9B), and
A-MEM − Mem0 is 25.69 on LongMemEval-S (S18, Table 2, Qwen3-30B). By
the same sources' figures, three other things move it by 11 to 37
points.
- **The reader's context.** A-MEM goes from 52.0 to 88.6 on
  LongMemEval as its budget goes from 4k to 32k tokens (S17); Zep from
  69.62 to 80.32 on LoCoMo as its context goes from 347 to 1,997
  tokens (S13).
- **The reader and the judge.** Zep reports 71.2% on LongMemEval in
  2025 with `gpt-4o` (S10) and 90.2% with `gpt-5.4` on an undated page
  (S14); Mem0 66.88 on LoCoMo with `gpt-4o-mini` (S7) and 91.6% with
  GPT-5 (S9's result file; the README's 92.5% names no model). Each
  pair also differs in the system's version.
- **Who ran it.** A-MEM on LoCoMo gets 48.38, 52.21 and 64.16 from
  three other groups, each with its own judge; Zep 58.44, 65.99 and
  75.14 from two parties.

Only Zep's smallest configuration in S13 (347 context tokens) is near
v2's 300-token budget; v1's is 2,000. No number above uses our
embedder (`nomic-embed-text`) or our local model (`qwen2.5:7b`). One
reads with `gpt-4o` (S10, `gpt-4o-2024-11-20`), whose relation to our
Azure deployment is not checked.

## The split: sessions to writer agents

The rule is given for LongMemEval, the benchmark recommended below;
LoCoMo follows at the end.

**What a writer is.** In LongMemEval a session is one chat of the user
with "the assistant". The split says which assistant: each session
belongs to one writer agent, as if the user had talked to a different
assistant that day. The question goes to the consumer,
`assistant_agent`, which held none of the sessions. So every answer
must come from rows that other agents wrote and shared: the
cross-agent path of `BENCHMARK_V2.md`, on their data. In the original,
the assistant that answers is the one that held every session.

**The rule.** For each question, number its sessions 1 to S in the
file's order (`haystack_sessions`), which the README calls
chronological and which differs from the dates only within a day
(above). Session j belongs to `WRITERS[(j - 1) mod 3]`, with
`WRITERS = (profile_agent, task_agent, calendar_agent)`, v2's three
writers (`BENCHMARK_V2.md`, "A user"), so that v2's agents, schedule and
variant channels apply unchanged. The question is asked at session
S + 1. The rule reads no label (`answer_session_ids`, `has_answer`),
no text and no model. The derived dataset records each session's
writer and keeps its date as metadata, which no row prints; a shorter
history (the oracle sessions) keeps the writers its sessions have in
S.

**Rejected.**
- **By date** (`haystack_dates`, ties in the file's order), the order
  their reader sorts its sessions in (S4, `run_generation.py` lines
  224 and 225). Where it differs from the file's order for a
  question's evidence, the gold follows the file. In knowledge-update
  question 618f13b2 (gold "six"), the user says "four times already"
  in the 18th of 49 sessions, dated 2023/05/30 22:16, and "six times
  now" in the 33rd, dated the same day at 17:45 (counted). By date the
  stale count would be the newer statement, and the session ages in
  every block would point away from the gold. Of the questions that
  are not abstention questions, it is the one of the four types kept
  below whose evidence sessions the two orders put in a different
  order; the others are 35 temporal-reasoning questions (counted),
  whose gold is not checked here.
- **A hash of the session id** (`sha256(session_id) mod 3`). Stable
  without a file, but uneven: within a question the largest and the
  smallest writer's share differ by 6.8 sessions on average and by up
  to 20 (counted on S). A deviating writer's share of a user's store
  would vary from question to question.
- **By era** (the first third of the sessions to one writer, and so
  on). Writer and age would be one variable, and a deviating writer
  would remove a whole period.
- **By topic** (a travel agent, a health agent). The realistic
  deployment (`STRESS_DIMENSIONS.md`, "Grounding"), but it needs a
  classifier, an LLM or a clustering, whose choices a reviewer cannot
  check and whose output is not in the data. Our agent-count split is
  by topic because we wrote the slot catalog (`STRESS_DIMENSIONS.md`,
  "The writers").
- **By the evidence labels** (a question's evidence sessions on
  different writers, or on one). It would make every multi-session
  question cross-writer, but the split would be built from the
  answers, and the benchmark would no longer be an outside one.
- **Within a session** (the user's turns to one agent and the replies
  to another, or alternate rounds). No deployment looks like it, and
  it separates a statement from its context.
- **The consumer keeps a share of the sessions.** Its own rows are
  never subject to another agent's deviation or to visibility, so the
  questions would mix two regimes.

**What the split does to each type** (counted on the cleaned S file
with the rule):

| Type | Questions (abstention) | Writers holding the evidence, all questions: one, two, three | The same, abstention questions left out | What the question becomes |
|---|---:|---|---|---|
| single-session-user | 70 (6) | 70, 0, 0 | 64, 0, 0 | the consumer recalls one writer's row |
| single-session-preference | 30 (0) | 30, 0, 0 | 30, 0, 0 | the same, judged against a rubric |
| single-session-assistant | 56 (0) | 56, 0, 0 | 56, 0, 0 | the same, but the evidence is the assistant's turn |
| knowledge-update | 78 (6) | 28, 50, 0 | 27, 45, 0 | one writer hears the fact and its change, or another writer hears the change |
| multi-session | 133 (12) | 23, 92, 18 | 20, 83, 18 | most need rows of two or three writers |
| temporal-reasoning | 133 (6) | 56, 71, 6 | 53, 68, 6 | as multi-session, and it needs dates |

- **At H = 0 the split changes only who wrote each row.** The consumer
  owns no row, so in the kernel and replicated loci every row comes
  from the shared fetch, whoever wrote it, and every row here is
  shared. The block prints no writer (`STRESS_DIMENSIONS.md`, "The
  writers"). So on the in-house backend, with one memory type for
  every row (below), the block should be the one a single writer would
  have given. `STRESS_DIMENSIONS.md` predicts the same for the agent
  count, and its functional check found it: in-house at H = 0, every
  block was byte-equal at N = 3, 6 and 12 in all three loci (30 of 30;
  `DEV_STATUS.md`, Subtask 18). The subset's single-writer cell checks
  it on this data.
- **On Mem0 the split itself changes what is stored.** Mem0 shows its
  extraction model up to 10 of the user's memories with the writing
  agent's own `agent_id` and that agent's last 10 messages for the
  user, and every locus passes the writer as `agent_id`
  (`DEV_STATUS.md`, known issue 53). So each of three writers extracts
  without what the other two were told.
- **Under H > 0 the split decides what a deviating writer takes with
  it.** A single-writer question loses all of its evidence or none. A
  multi-session question can lose part, and a count ("How many ...?")
  can then be wrong. A knowledge-update question whose newer
  statement is hidden gets the stale value; one whose older statement
  is hidden gets easier.
- **An abstention question has nothing to lose.** A consumer with no
  memory can answer it correctly. Accuracy on those 30 can rise as
  memory is lost, so they are never pooled with the rest.

**LoCoMo under the same rule.** The conversation would be the user,
both speakers' facts in one partition, and session n would go to
`WRITERS[(n - 1) mod 3]` (the numbers are the sessions' order, S2).
Counted: the evidence of 215 of the 282 multi-hop questions then lies
with two or three writers, and that of 840 of the 841 single-hop
questions with one. The writers would be observers of a chat between
two friends: the data has no assistant for them to be.

## Mapping to our probe types

| Their type (questions) | Our probe | What matches, and what does not |
|---|---|---|
| LongMemEval single-session-user (70) | recall | one fact, told to one writer, asked of the consumer. Their answers are ordinary phrases and numbers, not distinctive names: the matcher alone cannot score them |
| LongMemEval single-session-preference (30) | none exact: single-writer recall, judged against a rubric | under the split all 30 have their evidence with one writer. Our integration probe is defined by two writers' rows (the base profile and task context) and scored 1 to 5 by our judge (`BENCHMARK_V2.md`, "Probes") |
| LongMemEval knowledge-update (78) | none exact: the same or another writer, with no labelled stale value and no lean control | one writer hears the fact and its change (28 under the split), or two writers do (50). Our recency and contradiction probes are defined and scored by a labelled stale value, which the scorer requires (Cerebrum `benchmarks/shared_memory/probes.py`, `_validate`); a record here carries only the new `answer`, so neither the strict pass nor the split into stale-asserted and named-as-past can be computed. Ours balance their lean between the two statements, since a question's wording could not be told from its slot otherwise (Amendment 3, revision 3 of `users_v2`); theirs have no such control. No slot is labelled, so supersession retires nothing (Risk 5). Their judge accepts a response that names both values, as our lenient rate (`expected_present`) would |
| LongMemEval multi-session (133) | none exact; the nearest is integration | counting and comparing over two to five sessions. v2 has no probe that needs several facts of one kind |
| LongMemEval temporal-reasoning (133) | none | v2 probes no date or time, on purpose (`BENCHMARK_V2.md`, "Facts"). A block carries ages in sessions, not dates |
| LongMemEval single-session-assistant (56) | none | the evidence is what the assistant said. Our writers store what the user said; an assistant's own turn is its private conversation memory |
| LongMemEval abstention (30) | none | the fact was never stated; nothing was revoked or private, so it is not deletion or privacy. Its floor is the `no_memory` control's |
| LoCoMo single-hop (841) | recall | as single-session-user, in the third person |
| LoCoMo multi-hop (282) | none exact; the nearest is integration | several sessions |
| LoCoMo temporal (321) | none | dates |
| LoCoMo open-domain (96) | none | needs world knowledge |
| LoCoMo adversarial (446) | none usable | unanswerable questions, meant to be declined; unscorable as released |

**Ours with no counterpart in either benchmark.** Deletion, privacy
and the decision items (Amendment 10), and the dimensions around them
(a faulty agent, concurrent writers); recency and contradiction as v2
scores them, against a labelled stale value; integration over two
writers' rows. Neither benchmark has a revoke, a private fact, a
labelled slot or a second user to be confused with.
They could be added on top of the text (revoking a single-session fact
turns its question into an abstention question), but that would be
our benchmark on their sessions. It is not proposed.

## How each locus runs it

**The derived dataset.** An offline converter, with no model, turns
the pinned file into records of `users_v2`'s shape, so that the v2
harness path replays them (Cerebrum
`benchmarks/shared_memory/history.py`, `run_history`: the sessions in
order, each one writer turn, then the consumer's turns). One record
per question:
- `sessions`: one per session of the history, with its number, its
  writer by the rule, and one `add` event per user turn, whose
  `utterance` is the turn's text and whose `event_id` names the
  question, the session and the turn. Each event's `fact_key` is its
  own `event_id`: every v2 writer refuses an event without a
  `fact_key` (Cerebrum `cerebrum/example/agents/shared_memory_utils.py`,
  `_event_problem`), and one key shared by several events would let
  supersession, which the v2 pre-flight requires for the kernel and
  replicated loci, retire every earlier row of the key on each write
  (`aios/memory/pipeline/deletion.py`, `_supersede`). With a key per
  event no row is retired, but each write still lists the user's
  partition (`after_write`);
- `probes`: one, the question, with a probe type of its own (the
  scorer refuses any type outside its six: Risk 12), the gold
  `answer`, the evidence sessions and the flagged turns;
- no base events (the user has no v1 profile), so no integration
  probe and no decision items;
- a header with the source file's name and sha256, the rule and the
  converter's sha256, as `agents_v1.py` writes `derived_from` and
  `generator_sha256` for the agent-count files.

A question is a user: trial i is question i, with a user id of its
own, so cells pair by question as they pair by user in v1 and v2.

**What the writers store.** One row per user turn, shared, with the
metadata of a v2 write (`owner_agent`, `user_id`, `sharing_policy`,
`session`, `event_type`, the provenance fields) and one memory type
for every row, one the library does not know (`history`, say): the
formatter passes plain text through unchanged and ranks every row of
an unknown type alike, so the block stays in score order
(`aios/memory/pipeline/memory_formatter.py`, `format_memory`;
`formatter.py`, `TYPE_ORDER` and `type_rank`). That needs a writer
setting: each writer stores its own type today (Risk 12), and with
three types the kernel and replicated blocks would be sorted by
writer while native keeps score order. No writer calls a model, as in
v2: every locus is handed the same text.
- **The user's turns only.** Of the 581 flagged evidence turns of the
  four types kept below, 578 are the user's (counted). The assistant's
  turns are 86% of a history's words (67,814 of 78,427, counted), and
  in our model what an assistant said is its own private memory.
- **A turn longer than 300 words is cut to its first 300.** That is
  895 of the 122,416 user turns of S (counted); no flagged user turn of
  the four types has more than 163 words. Uncut, 128 user turns have
  more than 1,538 words, which by the library's estimate of 1.3 tokens
  a word (`formatter.py`, `estimate_tokens`) exceed a 2,000-token
  budget alone. The budget stage drops rows from the tail until the
  block fits (`formatter.py`, `truncate_by_token_budget`): if the
  best-ranked row is over the budget, the kernel and replicated blocks
  are empty, while native, which has no budget, keeps its rows.
- **So two types are left out.** single-session-assistant (56), whose
  evidence is not stored, and temporal-reasoning (133), since no row
  carries a date. Four types remain: 311 questions, 24 of them
  abstention questions.

**The three loci**, each as `BENCHMARK_V2.md` ("Loci and backends")
defines it:

| | Kernel | Replicated | Native |
|---|---|---|---|
| A write | the SDK's `create_memory`; the kernel's one pipeline stores it | the writer's own `MemoryPipeline.write` | the backend's documented call: `collection.add` on Chroma for in-house (Mem0 `add` with `infer=True`, Graphiti `add_episode`, A-MEM `add_note`; `NATIVE_USAGE.md`) |
| The read | the kernel injects the block into the consumer's chat (`auto_inject` on, `auto_extract` off) | the consumer's own pipeline builds the block | the consumer asks the backend for k rows and applies the sharing convention itself |
| The block | rows by score, capped at k, fitted to the budget, each with its age in sessions; header "Known about this user:" | the same library, the same block | the backend's k rows in its order (nearest first on Chroma), with the same ages and no budget; header "Relevant memories about this user:" |

**The consumer.** v1's `assistant_agent` with its system prompt
unchanged: one fresh turn, the question as written, the current
session S + 1, storing nothing (Amendment 3). The benchmark's reader
prompt and its "Current Date" line (S4, `run_generation.py`) are not
used: the loci must differ in memory only, and this is the consumer
every other cell of the paper has.

**Settings.** v1's: k 10, a 2,000-token budget, threshold 0.0, the
compact block, with ages in sessions on. Not v2's k 30 and 300 tokens
(Amendment 6), which the v2 pre-flight requires (Risk 12). v2's
budget was set to bind on one-sentence rows
(Amendments 3 and 6); a user turn here has 43.5 words on average, 56.6
estimated tokens (counted on the four types). At 300 tokens the kernel
and replicated blocks would hold about five rows against native's ten,
and a multi-session question has up to six flagged turns (counted).
With v1's settings every locus holds at most ten rows.

**Backends.** In-house (Chroma, verbatim, cosine) in all three loci.
The three extracting backends are costed below and are not in the
proposed subset.

**Heterogeneity.** H = 0 and H = 2 with the catalog of
`HETEROGENEITY.md` unchanged: `profile_agent`, `task_agent` and
`assistant_agent` can deviate, `calendar_agent` never does (v2). V5's
raw payload would be the turn as a JSON object, which needs a change:
today V5 writes the event's `fact_key`, `value` and type, none of
which holds a turn's text (Risk 12). A scored run at H > 0 needs
a committed schedule that names the dataset (`run_evaluation.py
--schedule`), as `pilot_v1_schedule.json` is for the pilot.

**Controls.** `no_memory` (the sessions are skipped): the floor per
type, and the check that a public dataset's questions are not answered
from what the model already knows. A single-writer kernel cell at
H = 0, every session written by one of the three writers: the check
that the split alone changes no block, read on block identity with
the three-writer kernel cell, unjudged. Both are cells of the subset.

**What the design predicts**, written before any run.
- **H = 0, in-house.** Kernel and replicated run one library on the
  same rows, so their blocks should be identical, as in v2 (180 of 180
  paired probes; `BENCHMARK_V2.md`, Amendment 7). Native asks Chroma
  for the ten nearest rows of the user, and none is private, so it
  should hold the same ten in the same order, under another header,
  unless the budget binds in the other two (which needs ten rows
  averaging about 150 words; how often is not known) or a repeated
  text ranks in the ten: kernel and replicated selection drops a row
  whose text an earlier row has (`aios/memory/pipeline/selector.py`,
  `merge_and_deduplicate`), and native does not (`NATIVE_USAGE.md`,
  "Diagnostics parity"). In 143 of the 287 histories of the four types
  that are not abstention questions, some user turn's text occurs more
  than once (391 extra rows, many of them "continue"; counted). The
  prediction is about rows: with the other header, a greedy answer,
  and so its label, can differ even on the same rows.
- **H = 2.** Re-derived here from the schedule's code (Cerebrum
  `cerebrum/example/agents/variants/schedule.py`, seed 20261106), over
  one cycle of 15 users: evidence that `profile_agent` or `task_agent`
  holds is hidden from every locus for 4 of the 15 (V1 or V3 on that
  writer: its rows are private), and lost outside the kernel only for
  up to 5 more (V2 on that writer, or a V2 or V4 consumer). Evidence
  that `calendar_agent` holds is lost outside the kernel only, for up
  to 4 (the consumer's V2 or V4). "Up to": a V4 consumer (k 5,
  threshold 0.5) loses the evidence only when it ranks below fifth or
  scores below 0.5. One exception: native with a V3 consumer reads a V1
  or V3 writer's private rows (1 of the 15 users, for `task_agent`).
  Native alone can lose more: it fetches k rows and applies visibility
  afterwards, so another writer's private rows take its slots
  (`BENCHMARK_V2.md`, "Loci and backends"), where kernel and replicated
  fetch 4k shared rows before they filter. That is up to 4 more users
  for `calendar_agent`'s evidence (users 2, 5, 10 and 14 of the cycle;
  in user 2 about two thirds of the store is private) and 1 each for
  `profile_agent`'s (user 5) and `task_agent`'s (user 10), leaving out
  user 12, whose V3 consumer applies no filter. Not counted: a V1
  consumer's legacy block, which is longer and may lose rows to the
  budget in replicated; and V5 writers (users 0, 1 and 8), whose rows
  would be JSON, which can change their rank in every locus, and which
  kernel and replicated print as fields but native verbatim
  (`HETEROGENEITY.md`, V5). The
  141 single-writer questions of the four types that are not
  abstention questions are 42, 56 and 43 by writer (counted; 19, 37 and
  23 of the subset's 79). So for about 0.19 of them every locus should
  lose the evidence; for up to about 0.31 more replicated and native
  should lose evidence the kernel keeps; and for up to about 0.13 more
  again native alone, up to about 0.44 in all (computed). This is
  arithmetic on the schedule, not a measurement. Part of it is the
  kernel's advantage by definition: it ignores a consumer's own
  settings (`STRESS_DIMENSIONS.md`, "Why these dimensions").

## What is scored

**Their metric, the judge-free part.** The recall of the evidence in
the block, as `eval_utils.py` defines it, with the block's rows as the
retrieved list (k is the number of rows in the block, at most ten): by
session (`recall_any`, `recall_all` over `answer_session_ids`) and by
turn (over the flagged turns), with the abstention questions left out
as theirs are. It is exact: a row carries its turn as
`provenance_event`. Each of the 287 other questions of the four types
has a flagged user turn (counted). For knowledge-update both evidence
sessions are labelled (2 in each of the 72 questions; in 70 both hold
a flagged turn: counted on the oracle file), so `recall_any` is met by
the stale statement's session alone; the recall of the later evidence
session is reported on its own line for that type.

**Their metric, the judged part.** Accuracy per type with
`evaluate_qa.py`'s prompts, unchanged. Their judge model is
`gpt-4o-2024-08-06`. Ours are `gpt-5.4` on Azure and Claude Sonnet 5.5
(`METRICS.md`, "The judges"). Proposed: each of ours labels each
distinct (question, answer) text once, with their prompt for the
question's type, and every cell with that answer gets that label; at
this size the second judge needs no 30% subset. Cells whose blocks
are identical should, with greedy decoding, give identical answers
(the three `no_memory` cells of Amendment 10's functional check gave
the same ten), and labels judged apart could differ. So the H = 0 tie
is read judge-free, on block and answer identity. Reported: accuracy
per type with a Wilson interval under each judge; the two judges'
agreement on the label (the share of equal labels and Cohen's kappa);
every paired difference under each judge, and whether the two give it
the same direction.
- It is their prompt with another judge model, so not their metric to
  the letter. Their agreement with human experts (more than 97% on
  average, 0.90 at worst, on single-session-preference: above) was
  measured for `gpt-4o-2024-08-06`. single-session-preference is 30 of
  the subset's 120 questions.
- A label is one sample of a judge that is not repeatable (`METRICS.md`,
  "The judges": 5 of 10 identical answers got a different profile
  score within one pass). How repeatable each of ours is on this prompt
  is not known: `calibration_v1` and the k rule are about a 1 to 5
  score.
- Their code caps the reply at 10 tokens (`evaluate_qa.py` line 109).
  Whether our two deployments accept that cap, or need a larger one,
  is not checked.
- **Cost.** A judgment of ours costs about $0.006 (`gpt-5.4`: 1,037
  tokens in and 215 out, at $2.50 and $15 a million, OpenAI's list
  price) and $0.004 (the second judge: 1,711 in and 415 out, at the
  Batch API's $1 and $5 a million), from 2,000 judgments each (Cerebrum
  `results/judge_reliability_s20/PROVENANCE.md`). Their prompt is
  shorter and its reply is one word: about 430 tokens in and 5 out with
  an answer as long as our consumer's (assumed, not measured), so about
  $0.0012 and $0.0005 (computed). The first pair is the bound used
  below.

**Judge-free readings beside it** (ours; they decide nothing).
- **The matcher on the gold answer**, where the answer is a name or a
  short phrase: about 43 of the 287 questions. 233 answers have at
  most five words; 114 of those are only digits and signs (counted on
  the oracle file). Of the other 119, classified by hand here, 64 are
  quantities and times with a unit or in words ("8 days.", "four",
  "Three times a week."), 2 dates, 2 weekdays, which v2 never probes,
  5 "Yes", and 3 first-person phrases ("under my bed", "in my
  bedroom", "my sister") that a consumer answering in the second
  person cannot match. A number or a "Yes" matches wherever the answer
  names it, so those are not read this way.
- **What a v2 cell records** (`METRICS.md`) needs the same harness
  change as the scoring (Risk 12): `cross_user_rows` and
  `private_rows_from_others` are computed on the integration probe's
  block, and `cap_bound`, `budget_bound` and the block's rows and
  estimated tokens by the probe scorer. On the question's one block
  they keep their meaning. `memories_missing` is not used: a writer
  holds about 81 of a user's rows (29,314 / 120 / 3, computed) and a
  block at most ten, so a writer can be missing with the evidence kept,
  or present with it lost. The evidence recall above measures the
  loss.

**Not scored.** LoCoMo's F1, if LoCoMo were run instead: it is
judge-free, but it compares words, and our consumer answers in
paragraphs (161 to 196 completion tokens a v2 probe; `BENCHMARK_V2.md`,
Amendment 7) where their reader is asked for a short phrase.

## The smallest convincing subset

**The subset.**
- **Data.** The cleaned S file; the four types; the 287 questions that
  are not abstention questions; of each type, the first 30 of its
  sorted question ids after `random.Random(20261120).shuffle` (one
  generator, the types in the order single-session-user,
  single-session-preference, knowledge-update, multi-session):
  120 questions. single-session-preference has exactly 30. With this
  rule the evidence of 41 of the 120 lies with two or three writers (18
  of the 30 knowledge-update and 23 of the 30 multi-session questions),
  and they hold 29,314 user turns, 244.3 a question (counted).
- **Cells**, 8: kernel, replicated and native, in-house, at H = 0 and
  H = 2; the single-writer kernel cell at H = 0, read on block
  identity and not judged; and `no_memory` once. In Amendment 10's
  functional check the three `no_memory` cells gave the same ten
  answers, since the consumer sees no memory and Qwen decodes greedily
  (`BENCHMARK_V2.md`, Amendment 10).
- **One consumer model**: Qwen (`qwen2.5:7b`), local.

**Its size and cost.**

| | Amount | From |
|---|---|---|
| Questions a cell | 120 | |
| Writes a cell | 29,314 | the subset's user turns (counted) |
| Writes, 7 cells | about 205,000 | 29,314 × 7 (computed); `no_memory` writes nothing |
| Consumer calls, 8 cells | 960 | one a question, Qwen on Ollama |
| Judge calls | at most 840 to each judge | one per distinct answer of the seven judged cells; fewer where answers repeat, how many fewer not known |
| Backend LLM calls | 0 | in-house stores the text |
| Embedding calls | at least one a write and one a question | local, on Ollama; not counted here |
| Dollars, backend and consumer | 0 | local |
| Dollars, judges | at most $5.04 and $3.36; about $0.97 and $0.38 by tokens | 840 × $0.006 and × $0.004; 430 tokens in and 5 out assumed |
| Laptop hours | 5 to 10 | extrapolated, below |

**The time is extrapolated.** No LongMemEval cell has run. In the
in-house cells of `stress_smoke_s18` (Qwen, 30 users, 2026-11-17;
Cerebrum `results/stress_smoke_s18`, the `n6h0` cells; read from each
event's `issued_at` and `completed_at`), a write took a median 0.040 s
in the kernel locus for a one-sentence row (8.5 words on average) and
0.221 s for a base row (53.0 words on average, and each the first
write of its session); 0.027 and 0.060 s replicated; 0.024 and 0.054 s
native. A probe took a mean 11.2 s, 9.7 s and 11.2 s (counted). A user
turn here has 43.5 words, so the two write times bracket it: a kernel
cell 0.7 to 2.2 hours, a replicated or native cell 0.5 to 0.8, the
`no_memory` cell 0.4, the eight cells 4.7 to 10.1 (computed). Not in
the estimate: the listings the v2 harness takes after every session
(48 a user here, 6 in v2); the listing of the user's partition that
every write makes under `supersession: exclude` (`after_write`), of
up to about 244 rows here against v2's 18; a prompt up to 2,000 tokens
of block against v2's 300; and Qwen's speed, which moved between 48
and 131 ms a token within one run (`BENCHMARK_V2.md`, Amendment 7).

**What it could show.**
- Whether the three loci tie at H = 0 on histories and questions we did
  not write, with about 244 rows a user where v2 has 18.
- Whether kernel − replicated and kernel − native open at H = 2 in the
  direction `HETEROGENEITY.md` predicts ("The dimension"). The subset
  has one test for each: the exact McNemar test (two-sided, at 0.05)
  on the 120 paired questions, the four types pooled. It finds a gap
  of 0.12 in accuracy with probability 0.87, 0.73 or 0.59 if 3%, 6%
  or 10% of the questions are won by the other cell; one of 0.15 with
  0.96, 0.87 or 0.77; one of 0.10 with 0.76, 0.58 or 0.45 (computed).
  That share is not known on this data, and the design makes a large
  one likely: identical answers judged apart can get different labels
  (avoided by labelling each distinct answer once, "What is scored");
  a knowledge-update question gets easier when its older statement is
  lost (Risk 7), which a deviating writer causes outside the kernel;
  and a changed block moves greedy answers both ways (in v2, k 30
  against k 10 moved Mem0's recency probe for 3 users up and 2 down in
  the kernel, 4 up and 6 down in replicated, of 30: `BENCHMARK_V2.md`,
  Amendment 7). Nor is the gap predicted: it is the share of questions
  whose evidence one cell loses and the other keeps (up to about 0.31
  of the single-writer ones, above) times Qwen's accuracy with the
  evidence minus without it, and neither accuracy is known.
- Which judged difference is a lost row: the evidence recall is
  measured on the same questions without a judge.
- Per type, a description only: 30 questions give a Wilson interval of
  ± 0.17 around 0.5 (computed), and no per-type gap can be tested (at
  30 paired questions the same test finds a gap of 0.20 with
  probability 0.46 if 3% go the other way; computed).

**What it could not show.**
- Anything about Mem0, Graphiti or A-MEM on this data.
- A comparison with any published number (Risks, 1).
- Deletion, privacy, supersession, the decision items, a faulty agent,
  concurrency: no counterpart, or not run.
- Temporal reasoning and what the assistant said: 189 of the 500
  questions are left out with their two types.
- A second model; a gap under about 0.10; a gap of 0.12 if many
  questions go the other way; any gap within a type.

**The next sizes** cost only time and judge calls.

| Subset | Questions | Laptop hours, 8 cells | Judges, at most |
|---|---:|---|---|
| The smallest | 120 | 5 to 10 | $5.04 and $3.36 |
| The four types, whole | 311, with the 24 abstention questions | 12 to 26 | $13.06 and $8.71 |

With the 287 that are not abstention questions the same test finds a
gap of 0.06 with probability 0.81, 0.63 or 0.47 and one of 0.08 with
0.95, 0.84 or 0.70, with 3%, 6% or 10% won by the other cell
(computed), and no question is sampled. `gpt-4o` as a second consumer
would add 840 turns over the seven judged cells:
$2.98 to $6.30, at 700 to 2,200 tokens in (ten rows, or a block at its
budget) and 180 to 200 out a turn (assumed from v2's measured
answers), at $2.50 and $10 a million; and 840 more judgments by each
judge, at most $5.04 and $3.36 (computed).

**An extracting backend is a different order of cost.** By our
measured price per v2 user ($0.36 on Mem0, $0.42 on Graphiti and $0.10
on A-MEM, a user of 17.8 writes: `AMEM_BACKEND.md`, "Measured in the
smokes") and our measured time per write (Mem0 1.9 s with `gpt-4o` in
the extraction check, on whole profile and task renderings:
`NATIVE_USAGE.md`, "Mem0 extraction check"; Graphiti 6.4 s and A-MEM
3.33 s in the v2 smokes: `GRAPHITI_BACKEND.md`, `AMEM_BACKEND.md`):

| Backend | A write | A question in one cell, S history (244.3 writes) | 120 questions in 6 cells (175,884 writes) | The same on the oracle history (1,167 writes a cell, 9.7 a question, counted) |
|---|---|---|---|---|
| Mem0 | $0.020, 1.9 s | $4.94, 8 minutes | $3,557, 93 hours | $142, 3.7 hours |
| Graphiti | $0.024, 6.4 s | $5.76, 26 minutes | $4,150, 313 hours | $165, 12 hours |
| A-MEM | $0.0056, 3.33 s | $1.37, 14 minutes | $988, 163 hours | $39, 6.5 hours |

The prices extrapolate from v2's writes (one sentence of 8.5 words on
average, and two base rows a user) to turns of 43.5 words, so they are
likely low. Two outside measurements bear on them. LightMem's authors
count, per LongMemEval-S question, 812 model calls and 1.15 million
tokens to build Mem0's memory and 987 calls and 1.61 million tokens
for A-MEM's (S18, Table 2, `gpt-4o-mini`, averaged over the dataset):
$4.14 and $5.77 at `gpt-4o`'s price (computed). For Mem0 that is near
ours ($4.94); for A-MEM it is about four times ours ($1.37), and it
ranks A-MEM above Mem0 where ours ranks it far below. Which roles
LightMem stored is not known ("Sources"), so the two counts may
differ in what was stored as well as in the price of a write. At
LightMem's count, A-MEM's cells above would cost about $4,150 on the
S history (5.77 × 720, computed) and its oracle cells about $165
(computed at the same ratio), as much as Graphiti's. Wu et al. could
not finish building the memory of Zep's open-source code on
LongMemEval in two days on 8 A100 GPUs (S19, Appendix H). The oracle
history has no filler session: it tests what a deviating writer hides,
not selection.

## Risks

1. **Published numbers are not comparable, with the split or
   without.** The split is the smallest reason: at H = 0 on in-house it
   should change no block (checked by the single-writer cell). The
   larger ones: we
   store the user's turns only, cut at 300 words, where Mem0's own run
   adds both roles' turns (S9); our embedder, our consumer and its
   prompt; a block of at most ten rows and 2,000 tokens where the
   published readers get 1.6k to 32k tokens; another judge model; two
   of six types left out; and the cleaned files, where the 2025 numbers
   are on the first release. No published number is from a setup we
   reproduce, the vendors' least of all (hosted services, tuned prompts
   and instructions). Our numbers must not sit in a table beside
   theirs. What can be reported: paired differences between our own
   cells.
2. **Questions that need one session only.** 100 of the 311 are
   single-session types (176 of all 500 have one evidence session; in
   LoCoMo, 840 of the 841 single-hop questions). With the rule, the
   evidence of 151 of the 311 lies with one writer (141 of the 287 that
   are not abstention questions; 79 of the subset's 120). For these the
   split decides only which writer holds the evidence. They test the
   cross-agent path (the consumer never wrote the row) and, under
   H > 0, they are the cleanest to read, all or nothing. They cannot
   show integration across writers: that rests on the 160 questions
   whose evidence two or three writers hold (110 multi-session, 50
   knowledge-update; 146 without the abstention questions, 41 in the
   subset).
3. **Cost.** In-house it is hours. An extracting backend on the S
   history is $988 to $4,150 and 93 to 313 hours for the smallest
   subset, by likely-low extrapolations (A-MEM's $988 is about $4,150
   at LightMem's count). The subset therefore has one backend, the one
   that stores text as it is.
4. **The judge.** Their metric needs one, and with our judges it is
   their prompt, not their metric. A yes or no from a judge that is not
   repeatable is one sample; two judges on every distinct answer bound
   the problem and do not remove it. Their 10-token cap may not suit
   our deployments (not checked).
5. **What the data cannot reach in the kernel.** Every row's
   `fact_key` is its own (its event id), so supersession retires
   nothing and no forget runs. A tie between kernel and replicated on
   knowledge-update questions says nothing about supersession, and the
   paper would have to say so.
6. **Part of the H = 2 gap is by definition.** The kernel ignores a
   consumer's own retrieval settings and canonicalizes an id (V4, V2).
   On outside data the gap shows the size of that effect, not a new
   mechanism.
7. **Accuracy is not monotone in memory.** An abstention question can
   be answered best with no memory, and a knowledge-update question
   gets easier when its older statement is hidden. Accuracy is reported
   per type always, as a description (30 questions a type in the
   subset are too few to test a gap); the subset's one test pools its
   four types; abstention is never pooled.
8. **Our consumer is not their reader.** Its system prompt tells it to
   "explicitly reference" the user's details when it has them (Cerebrum
   `cerebrum/example/agents/assistant_agent/config.json`), and nothing
   tells it that it may not know. Abstention accuracy may be low for a
   reason that is the prompt's.
9. **Long rows.** The 300-word cut is our change to their text. Without
   it a row over the budget can empty a kernel or replicated block.
   How much of a long row the embedder reads is not checked
   ("Sources").
10. **Public data.** Both benchmarks are on the web since 2024, and a
    model may have seen them. `no_memory` measures what it answers
    without memory.
11. **The files move, and do not match their README.** LongMemEval was
    cleaned once, and 211 of its 500 S histories are not in the
    timestamp order the README states, within a day; in one
    knowledge-update question of the subset (618f13b2) the dates
    contradict the gold, which follows the file's order. Their own
    reader sorts by date, so in their protocol that question's reader
    sees the stale count last. LoCoMo has open reports of wrong
    answers. The derived dataset pins a sha256 and keeps the file's
    order, and a result names it.
12. **The v2 harness assumes v2.** Each of these needs a change:
    - its probe session is 7, and a probe whose diagnostics show
      another fails (Cerebrum `benchmarks/shared_memory/history.py`,
      `PROBE_SESSION` and its check); it lists every agent's rows after
      each session (`_sessions`);
    - its pre-flight requires k 30, a 300-token budget, threshold 0.0
      and the compact block, and supersession `exclude` for the kernel
      and replicated loci (`run_evaluation.py`, `V2_SETTINGS`,
      `check_v2_settings`, `expected_supersession`);
    - a v2 user requires a profile, a task context and a follow-up
      query (`models.py`, `V2UserData`), which an outside record does
      not have;
    - every writer refuses an event without a `fact_key` (Cerebrum
      `cerebrum/example/agents/shared_memory_utils.py`,
      `_event_problem`), hence a key per event, and every write then
      lists the user's partition (above);
    - each writer passes its own memory type to the v2 session handler
      (`MEMORY_TYPE_PROFILE`, `MEMORY_TYPE_TASK_CONTEXT`,
      `MEMORY_TYPE_CALENDAR` in each agent's `agent.py`), so one type
      for every row needs a writer setting.
      Without it the kernel and replicated blocks are sorted by type
      (`aios/memory/pipeline/formatter.py`, `TYPE_ORDER`; the default
      `block_order` "type") and native's are not, which breaks the
      H = 0 predictions and the single-writer check;
    - the scorer refuses a probe type outside its six (`probes.py`,
      `_validate`), so the outside questions need a probe type and a
      scorer of their own;
    - the trial builder takes the integration probe by `next(...)`
      and computes its judge-free measures from it (`run_evaluation.py`,
      `run_single_trial_v2`), so a record without one stops there;
    - V5's raw payload is the event's `fact_key`, `value` and type
      (`shared_memory_utils.py`, `v2_structured`), which for these
      events holds none of the turn's text;
    - the primary judge's route asks for a JSON object and reads 1 to 5
      scores (`METRICS.md`, "The judges"); their yes or no prompt needs
      a route of its own.

    The outside path needs its own values and checks. Not designed
    here.
13. **Most rows are requests, not statements about the user.** 20,600
    of the subset's 29,314 user turns contain a question mark (0.70; a
    crude rule, not a classifier: counted). v2's rows are first-person
    facts ("I live in Tallinn."; `BENCHMARK_V2.md`, "Events"), and the
    consumer's prompt tells it to "explicitly reference" what it knows
    (Risk 8). A block headed "Known about this user:" that lists ten of
    the user's earlier requests changes what the consumer reads in
    every locus, and a 7B consumer may answer them. It bears on every
    cell's floor and ceiling and on reading a difference in block size.
    It is the same in every locus at H = 0, so it does not by itself
    make the loci differ, and the evidence recall does not depend on
    it.
14. **LoCoMo, if it were chosen instead.** Ten users: variants are
    drawn per user, so the heterogeneity contrast would rest on ten
    draws however many questions share them. And CC BY-NC, unfixed gold
    errors, one unusable category.

## Recommendation

**LongMemEval, the cleaned S file, not LoCoMo.**
1. **The unit of analysis.** Our design draws variants per user and
   pairs cells by user. LongMemEval has 500 users with one question
   each. LoCoMo has 10, with 105 to 260 questions each that share a
   store and a variant draw: 10 independent units, fewer than the
   pilot's 30.
2. **The shape.** A user and an assistant in dated sessions: a session
   becomes a writer's session and the question a consumer turn, with
   no modelling choice. LoCoMo is two people talking; "the user" would
   be a pair, and the writers observers.
3. **The types, on the full benchmark.** knowledge-update asks about a
   fact that changed, within one writer or across two; abstention
   gives a check on answering from nothing. LoCoMo has no knowledge
   update, and its abstention category cannot be scored as released
   (S3, Table 1; S2, issue 2). The recommended subset tests neither
   abstention nor our recency rule: it has no abstention question, and
   its knowledge-update questions can be scored as neither our recency
   nor our contradiction probe and exercise no supersession (Risk 5).
4. **The state of the data.** MIT; cleaned in 2025-09; evidence
   labelled by session and by turn. LoCoMo: non-commercial; gold
   errors reported and unfixed; category codes tied to no documented
   type, and the paper's numbered list differs from them.
5. **Where the field reports.** Zep since 2025 and Mem0 since 2026
   report on it (S10, S14, S9), as do A-MEM's first author and two
   outside groups (S17, S18, S19).

Accepted against it: its metric needs a judge, and its one history per
question puts the extracting backends out of reach.

**The subset.** The smallest one above: 120 questions of four types,
in-house, three loci at H = 0 and H = 2, one single-writer cell and
one `no_memory` cell, Qwen, both judges on every distinct answer.
29,314 writes a cell (about 205,000 in all), 960 consumer calls and at
most 840 calls to each judge; at most $8.40; 5 to 10 laptop hours by
extrapolation. It can show whether the loci tie at H = 0 on outside
data, on block and answer identity. Whether they part at H = 2 it can
show for a gap of 0.12 with probability 0.87 if 3% of the questions
go the other way and 0.59 if 10% do; how large the gap is, and how
many go the other way, is not known on this data. It cannot place us
beside any published number, and it says nothing on the extracting
backends, deletion, privacy or supersession.

## Open decisions

For the user; none is taken here.

1. **Which benchmark.** (a) LongMemEval, as recommended; (b) LoCoMo:
   cheaper per question, and judge-free by its own metric only with
   their reader prompt (decision 8 (b)), but ten users, a pair for a
   user, and known gold errors; (c) both; (d) none,
   and the paper states that its benchmark is its own. Bears on: what
   the paper can say about outside data, and a subtask of work.
2. **What a writer stores.** (a) the user's turns, as proposed: four
   types, 311 questions; (b) rounds, a user turn with its reply:
   single-session-assistant becomes answerable (temporal-reasoning also
   needs dates in the rows), rows are about seven times longer and the
   block holds four or five of them; (c) both roles as rows of
   their own. Bears on: which types are run, the block, the cost, and
   closeness to Mem0's own run (S9 adds both roles).
3. **Long turns.** (a) cut at 300 words, as proposed; (b) store them
   whole and report the empty blocks; (c) change the library's budget
   stage to skip a row that cannot fit, a kernel change that moves
   `PIPELINE_VERSION`. Bears on: a kernel and replicated handicap
   against native that is the budget rule's, not memory's.
4. **The split and the agent count.** (a) the file's order over v2's
   three writers, as proposed; (b) date order, their reader's, which
   turns question 618f13b2's gold around; (c) a hash of the session id;
   (d) N = 3, 6 or 12 with the agent-count schedule, in which every
   writer can deviate. Bears on: which schedule applies, how much of a
   user's store one deviating writer holds, and whether session ages
   agree with the gold.
5. **Retrieval settings.** (a) v1's k 10 and 2,000 tokens, as proposed;
   (b) v2's k 30 and 300 tokens, the paper's v2 setting, which holds
   about five rows here; (c) settings of its own. Bears on: whether the
   kernel is compared with native at equal block size.
6. **Size.** (a) 120 questions; (b) all 311 of the four types, 12 to 26
   laptop hours and no sampling; (c) all 500, which needs decision 2
   (b), dates in the rows, and a check of which order the gold of 35
   temporal-reasoning questions follows (their evidence sessions are
   in another order by date than in the file). Bears on: the smallest
   gap the test can find (0.12 with probability 0.87 at 120 questions,
   0.08 with 0.95 at 287, if 3% of the questions go the other way;
   0.59 and 0.70 if 10% do) and whether per-type rates can be read.
7. **Judges.** (a) both of ours on every distinct answer, with their
   prompts, as proposed; (b) their judge model on our Azure `gpt-4o`
   deployment, if
   its version is theirs (not checked), for their metric to the letter;
   (c) both (a) and (b); and whether a label is judged once or k times.
   Bears on: the claim "their metric", and the judges' cost at decision
   6 (b), 2,177 judgments: at most about $22 for (a), about $2.45 for
   (b) (430 tokens in and 5 out assumed, at `gpt-4o`'s price;
   computed).
8. **The consumer.** (a) ours, unchanged, as proposed; (b) their reader
   prompt with the question's date. Bears on: abstention accuracy, and
   whether these cells are comparable with the rest of the paper's.
9. **An extracting backend.** (a) none, as proposed; (b) one backend on
   the oracle history: $39 to $165 and 4 to 12 hours for six cells by
   our prices (A-MEM's $39 is about $165 at LightMem's count); (c) one
   backend on the S history for fewer questions, at $1.37 to $5.76 a
   question a cell by our prices (A-MEM's about $5.77 at LightMem's).
   Bears on: whether the paper can say anything about Mem0, Graphiti
   or A-MEM on outside data.
10. **A second model.** `gpt-4o` as consumer: $2.98 to $6.30 for seven
    cells, and up to $8.40 more for their judging. Bears on: one model
    or two.
11. **The derived records.** (a) a record type of the harness's own,
    without a profile; (b) `users_v2`'s type with placeholder profile,
    task context and follow-up query, which no agent may see. Bears on:
    the size of the harness change, and the risk that a placeholder
    reaches a prompt or a measure.
12. **When.** Before the full grid, as a pilot of its own, or after it;
    and whether its judgments join the grid's judge window
    (`FULL_GRID.md`) or have a window of their own. Bears on: the
    laptop's hours and the judges' drift.
