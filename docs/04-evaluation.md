# Evaluation

## 1. What is measured, and why

Four things can fail independently, so four things are measured separately:

| # | Metric | Question it answers |
| --- | --- | --- |
| 1 | Tool (intent) accuracy | Did the assistant pick the right capability? |
| 2 | Slot / argument accuracy | Did it fill the arguments correctly (amount, date phrase, query)? |
| 3 | Unsupported-number rate | Did it invent a number that no tool returned? |
| 4 | Retrieval recall@k and MRR | Did the right note come back, and how high did it rank? |

Latency is reported alongside, since a correct answer after eight seconds is a
different product.

## 2. Datasets

| File | Cases | Purpose | Provenance |
| --- | --- | --- | --- |
| `eval/dataset.jsonl` | 36 | Development set, one or more cases per intent and per argument slot | Written alongside the router — **optimistic by construction** |
| `eval/heldout.jsonl` | 16 | Held-out paraphrases, written in deliberately different phrasing (idioms, no trigger keywords) | Written after the router, used once before any pattern was added |
| `eval/retrieval.jsonl` | 10 | Question → expected note title, over the seeded note corpus | Hand-labelled against the six seed notes |

Splitting development from held-out is the whole point: a set written while
implementing the rules will always score near 100% and tells you nothing.

## 3. Results

### 3.1 Development set and held-out set

| Run | Provider | Tool accuracy | Argument accuracy | Unsupported numbers | Latency p50 |
| --- | --- | --- | --- | --- | --- |
| Dev set, router baseline | — | 100.0% | 100.0% | 0.0% | 0.1 ms |
| Dev set, full agent | mock | 100.0% | 100.0% | 0.0% | 24.7 ms |
| **Held-out, v1 (first contact)** | — | **50.0%** | **50.0%** | 0.0% | 0.1 ms |
| Held-out, v2 (after generalising patterns) | — | 100.0% | 100.0% | 0.0% | 0.1 ms |
| Dev set, v2 (regression check) | — | 97.2% | 97.2% | 0.0% | 0.1 ms |
| Dev set, v3 (regression fixed) | — | 100.0% | 100.0% | 0.0% | 0.1 ms |

### 3.2 Retrieval

| Metric | Value |
| --- | --- |
| Recall@3 | 100% (10/10) |
| MRR | 1.00 |
| Corpus | 6 notes → 9 chunks, porter-stemmed FTS5 |

### 3.3 The interesting part: the 50%

Eight of sixteen held-out paraphrases failed on first contact, all in the same way —
they fell through to the default `search_notes` fallback:

| Case | Utterance | Expected | Cause of failure |
| --- | --- | --- | --- |
| H01 | "put the synopsis submission on my plate for tuesday" | `add_task` | Idiom "on my plate" was not in the task-creation vocabulary |
| H02 | "gotta finish the OS assignment tonight" | `add_task` | Colloquial opener "gotta" absent |
| H04 | "chai cost 30 rupees" | `add_expense` | Only "cost me" was matched, not bare "cost" |
| H08 | "anything on my list for today" | `list_tasks` | List phrasing without an interrogative keyword |
| H10 | "the electricity bill is done" | `complete_task` | Copula form "is done" absent (only "done with") |
| H11 | "sort out my schedule for today" | `plan_day` | Scheduling verb "sort out" absent |
| H12 | "what has my energy been like this fortnight" | `mood_trend` | "energy … been like" and "fortnight" absent |
| H13 | "summarise my week please" | `weekly_review` | "summarise" verb absent |

The fix was **not** to add those eight strings. Each failure was generalised into a
pattern *family* — an idiom class ("on/to my plate/list"), a colloquial-opener class
("gotta", "gonna", "need to"), a copula completion class ("is/are/was done"), a
scheduling-verb class ("sort out", "organise", "structure"), a week-summary verb class
("summarise", "recap") — and the held-out set was re-run only after all families were
in.

That change then broke the development set (97.2%): "put on my list: return the
borrowed reference book" started routing to `list_tasks` because the new list-phrasing
rule matched it. The precedence rule was corrected (list-intent requires an
interrogative frame; imperative "put … on my list" stays task creation) and both sets
returned to 100%.

**Reported honestly:** the 100% on the held-out set is no longer a clean held-out
number, because it informed the pattern families. The defensible claim is a range —
the router handles roughly **50–100% of genuinely novel phrasings** depending on how
far they drift from the vocabulary it knows. A model-based router is the principled
fix; the rule router exists because it must work with no model at all.

### 3.4 What the mock-provider numbers do and do not show

The agent-loop run and the router baseline score identically, and that is expected:
the mock provider *is* the router plus a renderer. The agent-loop run therefore
validates the plumbing — schema generation, argument validation, tool dispatch,
result rendering, audit rows, memory, retrieval injection, latency — and says nothing
about a language model's accuracy. Model quality is measured by re-running the same
harness against a real provider:

```bash
python eval/run_eval.py --provider ollama --dataset dataset.jsonl
python eval/run_eval.py --provider ollama --dataset heldout.jsonl --tag ollama-heldout
```

## 4. Reproducing

```bash
pip install -r requirements.txt
python eval/run_eval.py --baseline            # router, no model
python eval/run_eval.py                       # full loop, mock provider
python eval/run_eval.py --baseline --dataset heldout.jsonl --tag heldout
```

Outputs `eval/results.json` and `eval/RESULTS.md`. Each run seeds a throwaway
database in a temporary directory, so results never depend on local state. The suite
runs in CI on Python 3.11 and 3.12.

## 5. Threats to validity

| Threat | Effect | Mitigation |
| --- | --- | --- |
| Self-authored datasets | Optimistic routing scores | Held-out set written in different phrasing; the 50% → 100% gap is reported rather than hidden |
| Small sets (36 + 16 + 10) | Wide confidence intervals; one case moves the score by 2.8–6.3 points | Reported as counts, not just percentages |
| Single annotator | Labelled intent reflects one person's reading | Every case carries one unambiguous expected tool; ambiguous phrasings were excluded |
| Mock ≈ router | Agent-loop accuracy is not model accuracy | Stated explicitly in §3.4; real-model runs are a documented one-command procedure |
| Retrieval corpus is 9 chunks | Recall@3 saturates easily | Acknowledged; larger corpora are needed before claiming retrieval quality |
| Unsupported-number rate is syntactic | Catches invented figures, not invented prose | Complemented by the grounded-refusal case (UC-2) and manual review of transcripts |
| Latency measured on mock | Real end-to-end latency unmeasured here | Budget in `docs/02-architecture.md` §7; local 8B inference is 1–3 s per turn on CPU |
