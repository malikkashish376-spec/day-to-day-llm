# Demo script (8 minutes)

Rehearse this twice. Time each block. If a step fails, move on — never debug live.

## Before the room

```bash
source .venv/bin/activate
make seed                 # deterministic demo data
make test                 # 80 passing, proves the build is sound
make run                  # http://127.0.0.1:8000
```

Have a second terminal open with `python -m daytoday.cli chat` ready. Have the
network cable decision made in advance: if `DAYTODAY_LLM_PROVIDER=ollama` and the
model is pulled, use it; otherwise stay on `mock` and say why (that is a strength,
not a fallback).

## 0:00 — Framing (45 s)

> "Most LLM projects put a text box in front of a model and hope. This one is built
> the other way round: the model never states a fact about me that did not come out
> of a database query. Everything you will see is auditable."

Point at the dashboard: chat pane on the left, live plan/tasks/money/notes rail on
the right, provider badge in the header.

## 0:45 — Grounded retrieval (90 s)

Type: `what did i write about normalisation`

Expected: a `search_notes` chip appears with its latency; the reply quotes the note
and cites the title and date. Click the chip to open the tool trace — arguments and
result JSON.

> "The note chip is the retrieved source. The tool chip is the exact call. Nothing in
> that sentence came from the model's weights."

## 2:15 — The deliberate failure (60 s)

Type: `who won the 1983 world cup`

Expected: "I could not find anything in your notes about that."

> "This is the important moment. The model knows the answer; the system refuses
> anyway, because the answer is not in my data. That is the difference between an
> assistant and a chatbot, and it is measured — the unsupported-number rate in CI is
> zero."

## 3:15 — Capture, with server-side dates (75 s)

Type: `remind me to submit the synopsis by friday 5pm`

Expected: task added, due date resolved to the coming Friday 17:00, visible in the
Tasks pane immediately.

> "The model did not compute that date. It passed the raw phrase and a tested parser
> resolved it against the server clock — because models are unreliable at date
> arithmetic and I did not want that class of bug."

## 4:30 — Money, exactly (60 s)

Type: `i spent 250 on coffee`, then `how much did i spend this month`

Expected: expense logged with inferred category `food`; then a total with the top
categories and percentage shares.

> "Amounts are stored as integer paise, so the monthly total is exactly the sum of the
> rows. A floating-point column would drift by a few paise and the examiner's
> calculator would disagree with my screen."

## 5:30 — Planning as a solved problem (75 s)

Type: `plan my day`

Expected: six 50-minute blocks from the next quarter hour, overdue items first, plus
a coach note.

> "The schedule is solved in Python under constraints — overdue first, then due today,
> then this week, never in the past, capped at six blocks. The model only writes the
> sentence around it. When I let the model plan, it invented tasks."

## 6:45 — CLI and the offline claim (45 s)

Switch to the terminal:

```bash
python -m daytoday.cli ask "review my week" -v
```

Expected: the seven-day review plus the full JSON trace, provider `mock`.

> "Same agent, no browser, and no network. The deterministic provider runs the
> identical loop, which is how this is tested in CI and why the demo cannot fail
> because of a model download."

## 7:30 — Numbers and candour (30 s)

Open `docs/04-evaluation.md`:

> "Eighty tests, 36 development cases at 100%, a held-out set that scored 50% on first
> contact and 100% after I generalised the patterns — and I report both numbers,
> because the held-out set informed the fix. Retrieval is recall@3 of 1.0 on a small
> corpus. The honest range for novel phrasing is 50 to 100 percent."

Close on the roadmap: hybrid retrieval, task durations, Hindi date parsing.

## If something breaks

| Symptom | Say this, do that |
| --- | --- |
| Model is slow or not pulled | Switch to `mock`, say: "the deterministic provider runs the same loop; the model is a configuration choice" |
| Dashboard does not load | Use the CLI in the second terminal; the CLI is the same agent |
| A tool errors | Show the trace: "the error is returned to the model as data and it explains it — that is the designed path" |
| Database looks empty | `make seed` in the second terminal; it takes one second |
