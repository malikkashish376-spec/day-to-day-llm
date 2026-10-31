"""Offline evaluation harness.

Three things are measured, because three things can fail independently:

1. routing accuracy  -- did the assistant pick the right tool for the intent?
2. argument accuracy -- did it fill the slots correctly (amount, date phrase)?
3. groundedness      -- does the prose contain numbers that no tool returned?
   (an unsupported-number rate above zero means the model is inventing figures)

Plus retrieval recall@k over a hand-labelled note set, and latency
percentiles. The rule-based router is always evaluated as the baseline, so an
LLM's numbers are reported against something, not in a vacuum.

Usage:
    python eval/run_eval.py                  # mock provider (no network)
    python eval/run_eval.py --provider ollama
    python eval/run_eval.py --baseline       # router only, no agent loop
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from daytoday import rag                                    # noqa: E402
from daytoday.agent import Agent                            # noqa: E402
from daytoday.db import connect                             # noqa: E402
from daytoday.router import route                           # noqa: E402
from daytoday.seed import seed_demo_data                    # noqa: E402

NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
EVAL_DIR = Path(__file__).parent


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def args_match(expected: dict, actual: dict) -> bool:
    """Compare expected slots against what the model produced.

    ``<key>_contains`` means a case-insensitive substring check, which is what
    we actually care about for free-text slots like a task title. Everything
    else is compared after normalisation, so '1.2k' and 1.2 are both accepted
    where a number is expected only if they are genuinely equal.
    """
    for key, want in expected.items():
        if key.endswith("_contains"):
            field = key[: -len("_contains")]
            got = str(actual.get(field, "")).lower()
            if str(want).lower() not in got:
                return False
        else:
            got = actual.get(key)
            if got is None:
                return False
            if isinstance(want, (int, float)):
                try:
                    if float(str(got).replace(",", "")) != float(want):
                        return False
                except ValueError:
                    return False
            elif str(got).lower().strip() != str(want).lower().strip():
                return False
    return True


def unsupported_numbers(reply: str, tool_results: list[dict]) -> list[str]:
    corpus = json.dumps(tool_results, ensure_ascii=False, default=str)
    corpus = corpus.replace(",", "")
    bad = []
    for token in NUMBER_RE.findall(reply.replace(",", "")):
        if token not in corpus:
            bad.append(token)
    return bad


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(round(q * (len(ordered) - 1))), len(ordered) - 1)
    return round(ordered[index], 1)


def evaluate_routing(cases: list[dict], provider: str, baseline: bool) -> dict:
    db_path = Path(tempfile.mkdtemp()) / "eval.db"
    seed_demo_data(str(db_path))
    agent = None if baseline else Agent(db_path=str(db_path))
    if agent is not None and provider != agent.client.name:
        import os
        os.environ["DAYTODAY_LLM_PROVIDER"] = provider
        from daytoday.llm import get_client
        agent.client = get_client()

    rows, latencies, unsupported_total, numbers_total = [], [], 0, 0
    for case in cases:
        started = time.perf_counter()
        if baseline:
            calls = route(case["message"])
            produced = [{"name": c.name, "arguments": c.arguments, "result": {}} for c in calls]
            reply = ""
        else:
            result = asyncio.run(agent.respond(case["message"], f"eval-{case['id']}"))
            produced = [{"name": t.name, "arguments": t.arguments, "result": t.result}
                        for t in result.tool_calls]
            reply = result.reply
        latencies.append((time.perf_counter() - started) * 1000)

        expect = case["expect"]
        tool_ok = bool(produced) and produced[0]["name"] == expect["tool"]
        arg_ok = tool_ok and args_match(expect.get("args", {}), produced[0]["arguments"])
        bad_numbers = unsupported_numbers(reply, [p["result"] for p in produced]) if reply else []
        if reply:
            numbers_total += len(NUMBER_RE.findall(reply.replace(",", "")))
            unsupported_total += len(bad_numbers)
        rows.append({"id": case["id"], "message": case["message"],
                     "expected": expect["tool"],
                     "predicted": produced[0]["name"] if produced else None,
                     "tool_ok": tool_ok, "args_ok": arg_ok,
                     "unsupported_numbers": bad_numbers})

    n = len(rows)
    return {
        "mode": "router-baseline" if baseline else f"agent:{agent.client.name}",
        "cases": n,
        "tool_accuracy": round(sum(r["tool_ok"] for r in rows) / n, 3),
        "argument_accuracy": round(sum(r["args_ok"] for r in rows) / n, 3),
        "unsupported_number_rate": round(unsupported_total / numbers_total, 3) if numbers_total else 0.0,
        "latency_p50_ms": pct(latencies, 0.50),
        "latency_p95_ms": pct(latencies, 0.95),
        "failures": [r for r in rows if not r["tool_ok"] or not r["args_ok"]],
        "rows": rows,
    }


def evaluate_retrieval(cases: list[dict], k: int = 3) -> dict:
    db_path = Path(tempfile.mkdtemp()) / "rag.db"
    seed_demo_data(str(db_path))
    conn = connect(db_path)
    hits_at_k, reciprocal = 0, []
    details = []
    for case in cases:
        results = rag.search_notes(conn, case["query"], k=k)
        titles = [r["title"] for r in results]
        rank = titles.index(case["expect_note"]) + 1 if case["expect_note"] in titles else 0
        hits_at_k += 1 if rank else 0
        reciprocal.append(1.0 / rank if rank else 0.0)
        details.append({"id": case["id"], "query": case["query"],
                        "expected": case["expect_note"], "rank": rank, "returned": titles})
    conn.close()
    return {
        "cases": len(cases), "k": k,
        "recall_at_k": round(hits_at_k / len(cases), 3),
        "mrr": round(sum(reciprocal) / len(reciprocal), 3),
        "details": details,
    }


def markdown(routing: dict, retrieval: dict) -> str:
    lines = [
        "# Evaluation results", "",
        f"Mode: **{routing['mode']}** &middot; {routing['cases']} routing cases &middot; "
        f"{retrieval['cases']} retrieval queries", "",
        "| Metric | Value |", "| --- | --- |",
        f"| Tool (intent) accuracy | {routing['tool_accuracy']:.1%} |",
        f"| Slot / argument accuracy | {routing['argument_accuracy']:.1%} |",
        f"| Unsupported-number rate (groundedness) | {routing['unsupported_number_rate']:.1%} |",
        f"| Retrieval recall@{retrieval['k']} | {retrieval['recall_at_k']:.1%} |",
        f"| Retrieval MRR | {retrieval['mrr']:.2f} |",
        f"| Turn latency p50 / p95 | {routing['latency_p50_ms']} ms / {routing['latency_p95_ms']} ms |",
        "",
    ]
    if routing["failures"]:
        lines += ["## Routing failures", "",
                  "| Case | Message | Expected | Predicted |", "| --- | --- | --- | --- |"]
        for row in routing["failures"]:
            lines.append(f"| {row['id']} | {row['message'][:60]} | {row['expected']} | "
                         f"{row['predicted']} |")
        lines.append("")
    else:
        lines += ["No routing failures in this run.", ""]
    missed = [d for d in retrieval["details"] if not d["rank"]]
    if missed:
        lines += ["## Retrieval misses", ""]
        for item in missed:
            lines.append(f"- `{item['query']}` expected *{item['expected']}*, got {item['returned']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="mock", choices=["mock", "ollama", "openai"])
    parser.add_argument("--baseline", action="store_true", help="rule router only")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--dataset", default="dataset.jsonl",
                        help="routing set to evaluate (dataset.jsonl | heldout.jsonl)")
    parser.add_argument("--tag", default="", help="suffix for the output files")
    args = parser.parse_args()

    cases = load(EVAL_DIR / args.dataset)
    queries = load(EVAL_DIR / "retrieval.jsonl")
    routing = evaluate_routing(cases, args.provider, args.baseline)
    retrieval = evaluate_retrieval(queries, k=args.k)

    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "routing": routing, "retrieval": retrieval}
    suffix = args.tag or ("heldout" if "heldout" in args.dataset else "")
    name = f"results-{suffix}.json" if suffix else "results.json"
    (EVAL_DIR / name).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    if not suffix:
        (EVAL_DIR / "RESULTS.md").write_text(markdown(routing, retrieval))

    print(f"mode                : {routing['mode']}")
    print(f"tool accuracy       : {routing['tool_accuracy']:.1%}")
    print(f"argument accuracy   : {routing['argument_accuracy']:.1%}")
    print(f"unsupported numbers : {routing['unsupported_number_rate']:.1%}")
    print(f"recall@{retrieval['k']}            : {retrieval['recall_at_k']:.1%}")
    print(f"mrr                 : {retrieval['mrr']:.2f}")
    print(f"latency p50 / p95   : {routing['latency_p50_ms']} / {routing['latency_p95_ms']} ms")
    if routing["failures"]:
        print("\nfailures:")
        for row in routing["failures"]:
            print(f"  {row['id']}: {row['message'][:50]!r} -> {row['predicted']} "
                  f"(expected {row['expected']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
