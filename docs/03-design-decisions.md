# Design decisions (ADR log)

Each entry records the decision, the alternatives that were seriously considered,
and the consequence we accepted. The rejected options are as important as the
chosen one — a decision without a discarded alternative is just a preference.

---

## ADR-001 — Tool calling instead of free-text generation over a dumped context

**Context.** The assistant must answer questions about the user's tasks, money and
notes. Two shapes are possible: serialise the user's data into the prompt and let the
model answer, or expose tools and let the model call them.

**Decision.** Tools. The model emits JSON-schema-validated calls; the application
executes them against SQLite.

**Alternatives rejected.** Dumping rows into the context window: simple to build,
but it does not scale past a few hundred rows, cannot perform aggregation
correctly ("total for October by category" is arithmetic the model will get wrong),
and makes every write action a string-parsing problem. Fine-tuning a model on the
user's data: no data to fine-tune on, and it freezes facts into weights.

**Consequence.** The model cannot aggregate badly, because it never aggregates —
`spending_summary` does. In exchange we pay one extra round trip per turn.

---

## ADR-002 — SQLite + FTS5 instead of Postgres + a vector database

**Context.** Single-user personal data, a few thousand rows, one developer, a viva
in which nothing may fail.

**Decision.** One embedded SQLite file, WAL mode, FTS5 for retrieval.

**Alternatives rejected.** Postgres + pgvector: two services to install and keep
alive for a workload that fits in a file, and a setup step that can fail in front of
an examiner. Chroma/FAISS + SQLite: a second storage system with its own
consistency story, for retrieval quality that measured *worse* here (see ADR-003).

**Consequence.** No concurrent multi-writer story, no horizontal scale. Both are
irrelevant to the stated scope, and both are documented as out of scope in the SRS
rather than discovered later.

---

## ADR-003 — BM25 retrieval over chunked notes, not embeddings

**Context.** Questions are answered from the user's own notes: short, personal,
vocabulary-heavy documents.

**Decision.** 55-word chunks with 12-word overlap, FTS5 with the porter stemmer,
BM25 ranking, prefix-matched OR queries, de-duplication by note.

**Alternatives rejected.** Dense retrieval with a sentence-transformer: measured
recall@3 of 0.84 against 0.91 for BM25 on the same probe set, with ~200× the query
latency and a 90 MB model download. Hybrid: the obvious next step, deferred because
the lexical baseline already saturates the current probe set.

**Consequence.** Pure synonymy fails ("salary" will not find "stipend"). This is
stated as a limitation and the retrieval interface is embedding-agnostic so a
re-ranker can be added without changing callers.

---

## ADR-004 — Deterministic server-side date parsing

**Context.** Models are unreliable at date arithmetic. Asked for "by Friday 5pm" on a
Saturday, an 8B model will happily emit last Friday's date, or the right weekday with
the wrong year.

**Decision.** Tool schemas accept the **raw phrase** in a `when` field. `timeparse.py`
resolves it against the server clock in the configured timezone, with 11 unit tests
covering relative days, weekdays, explicit dates, durations, and evening-hour
heuristics.

**Consequence.** Dates are testable without a model, identical across providers, and
auditable after the fact. The cost is a small, explicit set of supported phrasings.

---

## ADR-005 — Constraint-solved planning, model-narrated

**Context.** "Plan my day" is the flagship interaction. Letting the model compose the
schedule produced plans referencing tasks the user never created, and blocks that
started in the past.

**Decision.** `plan_day` solves the schedule in Python — ordering by
overdue → due today → due within three days → undated high-priority, allocating
50-minute blocks with 10-minute breaks from the next quarter hour, capped at six,
never before now — and returns structured blocks. The model narrates.

**Consequence.** The plan is reproducible and unit-testable, and the arithmetic can
never be wrong. The model's contribution is reduced to tone, which is the part it is
actually good at.

---

## ADR-006 — A deterministic provider in the product, not just in tests

**Context.** An assistant that only works with a GPU cannot be graded in CI, demoed on
a weak laptop, or regression-tested.

**Decision.** `MockLLM` runs the same agent loop: it classifies the message with the
rule router, emits real tool calls, and renders an answer from the real tool results.

**Alternatives rejected.** Skipping the model in tests (would leave the loop
untested); recording and replaying HTTP fixtures (brittle, and does not exercise
argument validation).

**Consequence.** CI asserts on end-to-end behaviour with zero network and zero
secrets. The honest caveat, stated in the evaluation document, is that mock-provider
scores measure the *plumbing and the router*, not a model's language ability.

---

## ADR-007 — Money as integer minor units

**Context.** Sums of `REAL` currency columns drift: three rows of ₹100.10 do not sum
to ₹300.30 in binary floating point, and a monthly total then disagrees with the rows
it came from — the kind of bug that is invisible until an examiner adds up the screen.

**Decision.** Store `amount_minor INTEGER` (paise). Parse "1.2k" / "Rs 1,450.50" /
"₹80" into minor units at the boundary; format for display only.

**Consequence.** Exact arithmetic and exact equality in tests (`40000` paise for
₹100 + ₹250.50 + ₹49.50). One conversion point to audit.

---

## ADR-008 — One registry behind both the model and the UI

**Context.** The dashboard has buttons that create tasks and expenses. Re-implementing
validation for them would create two code paths and two sets of bugs.

**Decision.** HTTP write endpoints dispatch through `ToolRegistry.execute`, the same
call the agent makes.

**Consequence.** Identical validation, identical audit rows, one set of tests. The
API layer stays thin enough to read in a minute.

---

## ADR-009 — Degrade rather than fail

**Context.** A network hiccup during a demo must not produce a stack trace.

**Decision.** `LLMError` inside the loop switches the turn to the mock provider and
marks the response `degraded: true`; the UI shows a chip. Tool-level errors are
returned to the model as data so it can explain them.

**Consequence.** The assistant is always answerable. The risk — silently serving a
degraded answer — is mitigated by surfacing the flag in the API response and the UI.

---

## ADR-010 — Measure groundedness with an unsupported-number rate

**Context.** "The model should not hallucinate" is not a testable requirement.

**Decision.** For every reply, extract numeric tokens and check each appears in the
tool results for that turn; report the share that do not.

**Alternatives rejected.** LLM-as-judge scoring: another model, another source of
noise, and not reproducible in CI. Exact-match scoring: too strict for prose.

**Consequence.** A cheap, deterministic, explainable metric that catches the failure
mode that matters (invented amounts and dates). It does not catch invented *words*;
that gap is named in the evaluation document's threats to validity.
