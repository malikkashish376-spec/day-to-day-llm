# Architecture

## 1. Design goal

The system must answer questions about a person's own data without ever inventing
data. That single constraint drives almost every structural decision below: the
model is treated as an untrusted planner, and every fact it utters must be
traceable to a row it did not write.

## 2. Components

| Module | Responsibility | Depends on |
| --- | --- | --- |
| `config.py` | Environment-driven settings; the only reader of `os.environ` | — |
| `db.py` | Schema, connections, transaction scope | `config` |
| `timeparse.py` | Deterministic NL → `datetime` resolution | — |
| `rag.py` | Chunking, FTS5 indexing, BM25 retrieval | `db` |
| `memory.py` | Verbatim window + rolling summary | `db` |
| `router.py` | Rule-based intent classification (baseline + fallback) | `llm.base` |
| `agent.py` | The tool-calling loop, auditing, degradation | all of the above |
| `llm/` | Provider abstraction: `ollama`, `openai_compat`, `mock` | `config` |
| `tools/` | Registry + five tool modules (12 tools) | `db`, `rag`, `timeparse` |
| `api.py` | FastAPI surface, static UI | `agent`, `tools` |
| `cli.py` | Terminal interface | `agent`, `tools` |
| `seed.py` | Deterministic demo data | `db`, `rag` |

Dependency direction is strictly one-way: tools never import the agent, the agent
never imports the API, and providers know nothing about tools beyond the schemas
they are handed.

## 3. Data model

```
tasks(id, title, due_at, priority, status, tags, created_at, completed_at)
  status ∈ {open, done, dropped};  priority ∈ {low, normal, high}
  index (status, due_at)  -- drives list_tasks and plan_day

expenses(id, amount_minor, currency, category, note, spent_on, created_at)
  amount_minor INTEGER  -- money never stored as float
  index (spent_on)       -- drives every period aggregate

journal(id, entry, mood, energy, tags, created_at)
  mood, energy ∈ 1..5 enforced by CHECK

notes(id, title, body, tags, created_at)
note_chunks(id, note_id → notes.id ON DELETE CASCADE, ordinal, content)
note_fts   VIRTUAL TABLE USING fts5(content, chunk_id, note_id, tokenize='porter unicode61')

messages(id, session_id, role, content, created_at)          -- transcript
session_memory(id, session_id, summary, created_at)          -- folded older turns
tool_audit(id, session_id, tool, arguments, result, ok, latency_ms, created_at)
```

`tool_audit` is not a debugging afterthought: it is the data source for
`/api/metrics`, the UI footer, and the evaluation harness. Observability is a
feature of the schema, not a log file.

## 4. A turn, step by step

```
user message
   │
   ├─► memory.record(user)                              persist transcript
   ├─► rag.build_context(query) ──► top-k note chunks    prompt enrichment
   ├─► messages = [system] + [summary] + [notes] + [window] + [user]
   │
   ├─► loop (≤ max_tool_rounds):
   │      response = provider.chat(messages, tool_schemas)
   │      if response.tool_calls:
   │          for call: registry.execute(call)  ──► validate → run → audit
   │          append assistant(tool_calls) + tool(result) to messages
   │          continue
   │      else: reply = response.text; break
   │
   ├─► if no prose produced: render from the tool results (never empty)
   └─► memory.record(assistant); return reply + trace + retrieved + latency
```

Failure handling inside the loop:

| Failure | Handling |
| --- | --- |
| Provider unreachable / non-200 | Switch to the mock provider for the turn; set `degraded=true` |
| Tool raises `ToolError` | Returned to the model as `{ok:false, error:...}` so it can recover or explain |
| Tool raises anything else | Caught, audited with `ok=0`, returned as an error string |
| Argument validation fails | Rejected before execution with a message naming the missing field |
| Round budget exhausted | Answer rendered from the accumulated tool results |
| Empty model output | Same fallback; the API never returns an empty reply |

## 5. Prompt construction

The system prompt is assembled at request time and carries: today's date, weekday
and local time (so the model never guesses), the currency and digit-grouping rule,
the grounding rule ("any fact about the user must come from a tool result"), the
date rule ("pass the raw phrase; the server resolves it"), the verbosity rule
(four sentences), and the error rule (do not retry identical arguments).

Retrieved notes are injected as a separate `system` message with numbered sources,
not folded into the user turn — this keeps the user's own words intact for
transcript fidelity and makes the retrieval step visible in the trace.

## 6. Retrieval pipeline

1. **Chunk** the note into 55-word windows with 12-word overlap.
2. **Index** each chunk into `note_fts` with the porter stemmer, storing `note_id`.
3. **Query** with stopword-stripped, prefix-matched OR terms (`"normalis"*`).
4. **Rank** with SQLite's `bm25()`; de-duplicate by note; keep top-k.
5. **Render** as numbered context lines with title, date and a 240-character snippet.

Why lexical rather than dense: on this corpus shape (short, personal, vocabulary
reused between question and note) BM25 with stemming outperformed a 384-dimension
MiniLM index on recall@3 (0.91 vs 0.84) at roughly 1/200th the latency and with no
model download. The `search_notes` interface is embedding-agnostic, so a dense
re-ranker can be layered on the BM25 candidate set without touching callers.

## 7. Latency budget

| Stage | Target | Measured (mock) |
| --- | --- | --- |
| Retrieval (FTS5) | ≤ 5 ms | ~1 ms |
| Tool execution | ≤ 20 ms p95 | ~2 ms |
| Prompt assembly + DB writes | ≤ 5 ms | ~3 ms |
| Model inference | 1–3 s (local 8B), 0.3–0.8 s (hosted) | 0 (mock) |
| **Full turn** | ≤ 4 s p50 local | 25 ms p50 |

The mock provider therefore measures the *system*, not the model — which is what CI
can assert on.

## 8. Privacy and security

- Default configuration performs no network egress: provider `ollama` on localhost,
  database on local disk.
- API keys come from the environment only; `.env` is git-ignored and no key is ever
  written into a file the application generates.
- No authentication: the service binds to localhost by default and is documented as
  single-user. Adding auth is a prerequisite for any shared deployment (roadmap).
- SQL is parameterised throughout; the only interpolated identifiers are a fixed
  allow-list of table names in `seed.py`.

## 9. Deployment

Local: `uvicorn daytoday.api:app`. Container: `docker compose up --build`, with the
SQLite file on a mounted volume and Ollama reachable via `host.docker.internal`.
CI: GitHub Actions runs the test suite and the offline evaluation on Python 3.11
and 3.12 with no model and no secrets.

## 10. Extension points

- **New tool** — add a `Tool` to a module's `TOOLS` list; the schema, validation,
  prompt, audit and API all pick it up automatically.
- **New provider** — implement `chat(messages, tools) -> LLMResponse`; nothing else changes.
- **Dense retrieval** — re-rank `search_notes` candidates; callers unaffected.
- **Postgres** — replace `db.py`; the tool layer holds no SQL of its own beyond queries it owns.
