# Software Requirements Specification

**Project:** DayToDay-LLM — a grounded personal assistant for everyday life
**Author:** Kashish Malik · **Version:** 1.0 · **Status:** implemented and evaluated

---

## 1. Purpose

This document specifies the requirements for a single-user assistant that helps an
individual manage four everyday information streams — commitments (tasks), money
(expenses), wellbeing (journal), and knowledge (notes) — through natural language,
while guaranteeing that every factual statement it makes is traceable to stored
data.

## 2. Scope

**In scope.** A local-first conversational assistant with tool-augmented LLM
reasoning, retrieval over the user's own notes, a web dashboard, a CLI, a test
suite, and a reproducible evaluation harness.

**Out of scope (explicitly).** Multi-user tenancy and authentication; cloud sync;
bank/UPI integration; calendar provider sync; voice input; non-English input;
mobile clients.

## 3. Stakeholders

| Stakeholder | Interest |
| --- | --- |
| The user (a student managing deadlines, spending, study notes) | Fast, private, correct answers about their own data |
| Project guide / examiner | Traceable design, measurable behaviour, defensible evaluation |
| Future maintainer | Modular boundaries, tests, documented decisions |

## 4. Definitions

- **Tool call** — a structured function invocation emitted by the model and executed by the application.
- **Grounded** — every number or fact in a reply appears in a tool result produced during that turn.
- **Unsupported-number rate** — share of numeric tokens in a reply that no tool returned. Target: 0%.
- **Turn** — one user message plus the complete assistant response, including all tool calls.
- **Degradation** — automatic fallback to the deterministic provider when the configured provider is unreachable.

## 5. Functional requirements

### 5.1 Conversation and reasoning

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-1 | Accept a natural-language message and reply in prose | Must |
| FR-2 | Select tools from a registry of JSON-schema-described functions | Must |
| FR-3 | Execute tool calls and feed results back to the model, up to a bounded number of rounds (default 4) | Must |
| FR-4 | Never state a fact about the user's data that no tool returned in that turn | Must |
| FR-5 | When retrieval finds nothing relevant, say so instead of answering from model priors | Must |
| FR-6 | Maintain conversational context: last 8 turns verbatim, older turns folded into a summary | Must |
| FR-7 | Report which tools ran, with arguments and latency, for every turn | Should |
| FR-8 | Degrade to the offline provider if the configured provider fails, and flag the response as degraded | Must |

### 5.2 Tasks

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-9 | Create a task with title, due date/time, priority and tags | Must |
| FR-10 | Resolve relative time phrases ("tomorrow 6pm", "by Friday", "in 2 hours", "25/12") server-side | Must |
| FR-11 | List tasks with due dates, flagging overdue and due-soon items | Must |
| FR-12 | Complete a task identified by a fuzzy natural-language description, reporting a clear failure when no task matches | Must |

### 5.3 Expenses

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-13 | Log an expense from a spoken amount ("250", "Rs 1,450.50", "1.2k") | Must |
| FR-14 | Store money in integer minor units and never lose paise | Must |
| FR-15 | Infer a spending category from the description, overridable by the user | Should |
| FR-16 | Report totals and a category breakdown for today, week, month or year, with shares summing to 100% | Must |
| FR-17 | Reject implausible or non-numeric amounts with an explanatory error | Must |

### 5.4 Journal

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-18 | Save a journal entry with mood and energy on a 1–5 scale | Must |
| FR-19 | Infer mood and energy from free text when not supplied, and mark the value as inferred | Should |
| FR-20 | Report average mood/energy and the direction of travel over a window | Should |

### 5.5 Notes and retrieval

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-21 | Store a note, chunk it, and index it for retrieval | Must |
| FR-22 | Retrieve the top-k chunks for a question with relevance scores and snippets | Must |
| FR-23 | Re-indexing a note must not leave stale chunks retrievable | Must |

### 5.6 Planning and review

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-24 | Produce a time-blocked plan for a day, ordering overdue → due today → this week → undated | Must |
| FR-25 | Never schedule a block in the past | Must |
| FR-26 | Cap scheduled blocks and report what did not fit | Should |
| FR-27 | Produce a seven-day review: tasks completed, overdue count, spend vs previous week, average mood | Should |

### 5.7 Interfaces

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-28 | Web dashboard: chat pane with tool traces, plus plan/tasks/money/notes panes | Must |
| FR-29 | REST API with OpenAPI documentation | Must |
| FR-30 | CLI supporting one-shot and interactive use | Must |
| FR-31 | UI write actions must use the same validation and audit path as model-driven actions | Must |

## 6. Non-functional requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-1 | Turn latency with a local 8B model | ≤ 4 s p50 on CPU, ≤ 1 s with a hosted model |
| NFR-2 | Tool execution latency | ≤ 20 ms p95 (local SQLite) |
| NFR-3 | Privacy | Personal data never leaves the machine in the default (`ollama`) configuration |
| NFR-4 | Portability | Runs on Python 3.11+ with no compiled dependencies beyond the standard wheel set |
| NFR-5 | Testability | ≥ 70% of modules covered by automated tests; full suite under 15 s |
| NFR-6 | Determinism | Identical input and database state produce identical tool calls under the mock provider |
| NFR-7 | Observability | Every tool call audited with arguments, result, success flag and latency |
| NFR-8 | Recoverability | A provider outage degrades the assistant; it never returns a 500 |
| NFR-9 | Cost | Zero recurring cost in the default configuration |
| NFR-10 | Accessibility of the deliverable | One-command setup (`pip install -r requirements.txt`, `make seed`, `make run`) |

## 7. Use cases

### UC-1 Capture a commitment from conversation
Actor sends: *"remind me to submit the synopsis by friday 5pm"*.
System classifies intent → `add_task` → resolves "by friday 5pm" against the server
clock → stores the row → confirms with the resolved date in human form.
**Postcondition:** one `tasks` row with `due_at` set, one `tool_audit` row.

### UC-2 Ask a question the data cannot answer
Actor sends: *"who won the 1983 world cup"*.
System routes to `search_notes`; retrieval returns zero chunks; the assistant states
that it cannot find this in the notes rather than answering from model priors.
**Postcondition:** no invented fact; retrieval miss visible in the trace.

### UC-3 Understand the month's spending
Actor sends: *"how much did i spend this month"*.
System calls `spending_summary(period="month")`, returns total, top three categories
with percentage shares, and transaction count.
**Postcondition:** shares sum to 100% ± rounding; total equals the sum of rows.

### UC-4 Plan the day
Actor sends: *"plan my day"*.
System runs the constraint pass (overdue first, then due today, then this week, then
high-priority undated), allocates 50-minute blocks with 10-minute breaks from the
next quarter hour, caps at six blocks, and adds a coach note derived from overdue
count and seven-day energy.
**Postcondition:** no block starts in the past; unscheduled items are reported.

### UC-5 Recover from a provider outage
The configured provider is down. The loop catches the error, switches to the
deterministic provider for the turn, and returns a normal answer flagged
`degraded: true`.
**Postcondition:** no exception reaches the client; the UI shows a degraded chip.

## 8. Constraints and assumptions

- Python 3.11+; SQLite with FTS5 available (standard in CPython builds).
- One user per deployment; no concurrent-write contention beyond SQLite's WAL mode.
- The host clock is trusted; all relative dates resolve against server-local time in the configured timezone.
- The model may be weak or absent; correctness of stored data must not depend on model quality.

## 9. Acceptance criteria

1. All 80 automated tests pass on Python 3.11 and 3.12.
2. The evaluation harness runs offline and reports tool accuracy, argument accuracy, groundedness, retrieval recall and latency.
3. Every functional requirement above is exercised by at least one test or evaluation case.
4. The demo script in `docs/06-demo-script.md` runs end to end on a machine with no model installed.
