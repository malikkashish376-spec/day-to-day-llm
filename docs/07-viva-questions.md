# Viva question bank

Answers are written to be spoken in 30–60 seconds each. The starred ones are the
questions examiners actually ask.

**\*1. Why not just send my data to GPT and let it answer?**
Because aggregation and dates are exactly where models fail silently. "Total spent on
food in October" requires arithmetic over rows; "by Friday 5pm" requires knowing
today's date and weekday. In this system those are a SQL aggregate and a tested
parser. The model only chooses the call and narrates the result, so it cannot get the
numbers wrong — it never computes them.

**\*2. How do you know the model is not hallucinating?**
Every fact must come from a tool result. The harness extracts numeric tokens from each
reply and checks they appear in that turn's tool output; the unsupported-number rate is
0.0% across 52 evaluation cases. Non-numeric hallucination is not caught by that
metric — it is caught by the retrieval-grounded design and by reviewing transcripts,
and I state that gap as a limitation.

**3. What happens if the model is unavailable?**
The loop catches the provider error, switches to the deterministic provider for that
turn, and flags the response `degraded: true`, which the UI shows as a chip. A network
hiccup never produces a 500.

**\*4. Why SQLite and not Postgres or MongoDB?**
Single-user, a few thousand rows, one file, ACID, and FTS5 built in. It removes an
install step that can fail in front of an examiner and gives me retrieval without a
second system. The trade-off — no concurrent writers, no horizontal scale — is
irrelevant at this scope and is listed as out of scope rather than discovered later.

**\*5. Why BM25 instead of vector embeddings?**
I measured both on the same probe set. For short personal notes that reuse the
question's vocabulary, BM25 with the porter stemmer gave recall@3 of 0.91 against 0.84
for a MiniLM index, at roughly 1/200th the query latency and with no model download.
The interface is embedding-agnostic, so a dense re-ranker is a drop-in next step.

**6. Where does chunking happen and why those numbers?**
55-word windows with 12-word overlap. Long enough to keep an argument intact, short
enough that four chunks fit in the prompt. Overlap prevents an answer that straddles a
boundary from being split in half.

**\*7. Why store money in paise?**
Floating point cannot represent 0.10 exactly. Three rows of ₹100.10 do not sum to
₹300.30, so the monthly total disagrees with the rows it came from. Integer minor
units make the arithmetic exact and the tests use equality, not tolerances.

**8. What is the mock provider, and does using it make the evaluation meaningless?**
It is a deterministic policy that runs the same agent loop: classify, emit real tool
calls, render an answer from real tool results. It proves the plumbing — schema
generation, validation, dispatch, audit, memory, retrieval injection — and it is what
lets CI run with no model and no secrets. It does not prove a model's accuracy, and
the evaluation document says so in as many words; re-running the harness against
Ollama is a one-command procedure.

**\*9. Your development set is 100%. Isn't that overfitting?**
Yes, and I tested for it. A held-out set written in deliberately different phrasing
scored 50% on first contact — eight of sixteen fell through to the default retrieval
fallback. I generalised the failures into pattern families rather than adding the exact
strings, which raised held-out to 100% but broke the development set to 97.2% on a
precedence conflict; that was fixed too. The defensible claim is a range of roughly
50–100% on genuinely novel phrasing, and both numbers are in the report.

**10. Why is the plan computed in code rather than by the model?**
When the model composed the schedule it invented tasks that did not exist and
occasionally scheduled blocks in the past. A constraint pass — overdue, then due
today, then this week, then undated high-priority, 50-minute blocks, never before now,
capped at six — is deterministic and unit-testable. The model's remaining job, tone, is
what it is genuinely good at.

**11. How do you handle conversational context?**
A two-tier memory: the last eight turns verbatim for pronoun resolution, and older
turns folded into a summary row so a long session does not blow the context budget.
Retrieved notes are injected as a separate system message, not merged into the user's
turn.

**12. What is the audit table for?**
Every tool call is written with its arguments, result, success flag and latency. It is
the data source for `/api/metrics`, the dashboard footer and the evaluation harness —
observability as a schema feature rather than a log file.

**13. How would you add a new capability?**
Add a `Tool` to a module's `TOOLS` list with its JSON schema and handler. The prompt,
validation, dispatch, audit and API pick it up automatically; there is nothing else to
register. Adding a provider means implementing one `chat` coroutine.

**14. What are the biggest limitations?**
Single user with no authentication; English only; lexical retrieval that misses pure
synonymy; mood inference from a 40-word lexicon rather than a trained classifier; and a
planner that treats every task as a 50-minute block.

**15. What would you do with another semester?**
Hybrid retrieval (BM25 candidates re-ranked densely), task duration estimates with
calendar-aware slot finding, recurring tasks with a notification worker, and
Hindi/Hinglish normalisation for dates and amounts — "kal shaam 6 baje" is the phrase
that breaks the current parser.
