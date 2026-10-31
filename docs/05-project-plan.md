# Project plan

Two semesters, 32 working weeks, one student, one guide. The plan is written the way
it was actually executed: a vertical slice early, evaluation in the middle, polish and
documentation at the end — not "code for six months, then test".

## 1. Phases and milestones

| Phase | Weeks | Work | Milestone |
| --- | --- | --- | --- |
| P0 Literature and scoping | 1–3 | Survey tool-augmented LLM systems (ReAct, Toolformer, function calling), personal-information assistants, RAG; define the four data streams and the grounding requirement | **M1** Problem statement + synopsis approved |
| P1 Foundations | 4–6 | Schema design, `db.py`, `timeparse.py` with tests, money as minor units | **M2** Storage layer frozen, 20 tests green |
| P2 Tools and retrieval | 7–10 | Tool registry, 12 tools, FTS5 chunking and BM25 retrieval, seed corpus | **M3** All tools callable from a script; retrieval recall@3 ≥ 0.8 on the probe set |
| P3 Agent loop | 11–13 | Provider abstraction (ollama, openai-compatible), tool-calling loop, memory, degradation | **M4** End-to-end turn with a local 8B model |
| P4 Interfaces | 14–16 | FastAPI surface, single-file dashboard, CLI | Mid-semester review demo |
| P5 Evaluation | 17–20 | Development and held-out datasets, harness, metrics, failure analysis | **M5** Evaluation report with honest numbers |
| P6 Hardening | 21–24 | Error paths, validation, audit trail, CI on two Python versions, Docker | Review 2: reproducible build |
| P7 Documentation and viva | 25–28 | SRS, architecture, ADR log, demo script, viva question bank, report writing | Draft report to guide |
| P8 Buffer and final | 29–32 | Fixes from guide's comments, rehearsal, final demo | **M6** Final submission and viva |

## 2. Weekly cadence

- Monday: 30-minute guide meeting — show a running system, not slides.
- Wednesday: evaluation run; numbers appended to the results table so progress is visible week to week.
- Friday: documentation commit; the report is written continuously, never in one panic week.

## 3. Testing strategy

| Level | Scope | Count | Runs |
| --- | --- | --- | --- |
| Unit | Time parsing, amount parsing, chunking, category inference, validation | 34 | Every commit, CI |
| Component | Tools against a temporary SQLite database (tasks, expenses, journal, retrieval, planner) | 24 | Every commit, CI |
| Integration | Full agent loop: multi-turn memory, audit rows, round budget, provider failure degradation | 8 | Every commit, CI |
| API | FastAPI via `TestClient`: chat, CRUD, 422 paths, static page | 8 | Every commit, CI |
| Evaluation | 36 development + 16 held-out routing cases, 10 retrieval queries | 62 | Every commit, CI (offline) |
| Manual | Demo script rehearsal with a local model, twice: once with network, once without | — | Weekly from week 24 |

Total automated: **80 tests + 62 evaluation cases**, full suite under 15 seconds.

## 4. Risk register

| # | Risk | Likelihood | Impact | Mitigation (what was actually done) |
| --- | --- | --- | --- | --- |
| R1 | Local model unavailable or too slow during the viva | Medium | High | Deterministic provider runs the identical loop with no model; demo rehearsed offline |
| R2 | Model invents data in front of the examiner | Medium | High | Tools own all facts; unsupported-number metric in CI; deliberate grounded-refusal moment in the demo |
| R3 | Relative dates resolved wrongly | High | Medium | Dates resolved in Python, 11 unit tests, model never does arithmetic |
| R4 | Floating-point money errors | Medium | Medium | Integer minor units, equality asserted in tests |
| R5 | Rule router overfits the development set | High (observed) | Medium | Held-out set scored 50% on first contact; generalised to pattern families; both numbers documented |
| R6 | Setup fails on the examiner's machine | Low | High | `pip install` + `make seed` + `make run`; Docker image as a fallback |
| R7 | Scope creep into multi-user/cloud | Medium | Medium | SRS out-of-scope list; roadmap instead of implementation |
| R8 | Loss of work | Low | High | Git from week 4, CI on every push, database never committed |

## 5. Deliverables

1. Working repository (application, tests, evaluation harness, CI).
2. Project report (SRS, architecture, evaluation, conclusion).
3. Live demo: dashboard + CLI, with and without a model.
4. This documentation set, including the ADR log and the viva question bank.

## 6. Viva preparation checklist

- [ ] Rehearse `docs/06-demo-script.md` twice, once with the network cable out.
- [ ] Be able to draw the agent loop on a whiteboard in 60 seconds.
- [ ] Be able to state one measured number and one honest limitation for each of the four metrics.
- [ ] Know why BM25 beat embeddings here, and what would change the answer.
- [ ] Know why money is stored in paise.
- [ ] Know what the mock provider does and does not prove.
- [ ] Have the failure table from `docs/04-evaluation.md` §3.3 ready — examiners reward candour.
