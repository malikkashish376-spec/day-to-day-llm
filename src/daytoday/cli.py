"""Command-line interface: ``python -m daytoday.cli <command>``.

The CLI is what a grader uses when there is no browser, and it is what the
offline demo runs on. It shares the agent, not a reimplementation of it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .agent import Agent
from .config import PROJECT_ROOT, settings
from .db import connect, init_db
from .tools import build_registry
from .tools.registry import ToolError

BANNER = """
DayToDay-LLM  |  provider: {provider}  |  db: {db}
Type a message, or /plan /tasks /money /help /quit
"""


def _run_tool(name: str, args: dict) -> dict:
    conn = connect()
    try:
        return build_registry().execute(name, args, conn)
    finally:
        conn.close()


def cmd_init(_: argparse.Namespace) -> int:
    init_db()
    print(f"Initialised database at {settings.db_path}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    agent = Agent()
    result = asyncio.run(agent.respond(args.message, args.session))
    print(result.reply)
    if args.verbose:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    agent = Agent()
    print(BANNER.format(provider=agent.client.name, db=settings.db_path))
    while True:
        try:
            line = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/quit", "/exit"):
            return 0
        if line == "/help":
            print(" /tasks  list open tasks    /money  this month's spend\n"
                  " /plan   plan today         /quit   exit")
            continue
        if line == "/tasks":
            data = _run_tool("list_tasks", {"status": "open"})
            for task in data["tasks"]:
                print(f"  #{task['id']} {task['title']} ({task['due_human']})")
            continue
        if line == "/money":
            data = _run_tool("spending_summary", {"period": "month"})
            print(f"  {data['total']} across {data['transaction_count']} transactions")
            for row in data["breakdown"]:
                print(f"    {row['category']:<12} {row['total']:>12}  {row['share_pct']}%")
            continue
        if line == "/plan":
            data = _run_tool("plan_day", {"when": "today"})
            for block in data["blocks"]:
                print(f"  {block['start']}-{block['end']}  {block['title']}")
            print(f"  {data['coach_note']}")
            continue
        result = asyncio.run(agent.respond(line, args.session))
        print(f"day > {result.reply}")
        if result.tool_calls:
            names = ", ".join(f"{t.name}({t.latency_ms}ms)" for t in result.tool_calls)
            print(f"      [{names}]")
    return 0


def cmd_seed(_: argparse.Namespace) -> int:
    from .seed import seed_demo_data
    init_db()
    summary = seed_demo_data()
    print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daytoday", description="DayToDay-LLM CLI")
    parser.add_argument("--db", help="override database path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database schema").set_defaults(func=cmd_init)

    ask = sub.add_parser("ask", help="send one message")
    ask.add_argument("message")
    ask.add_argument("--session", default="cli")
    ask.add_argument("-v", "--verbose", action="store_true")
    ask.set_defaults(func=cmd_ask)

    chat = sub.add_parser("chat", help="interactive session")
    chat.add_argument("--session", default="cli")
    chat.set_defaults(func=cmd_chat)

    sub.add_parser("seed", help="load demo data").set_defaults(func=cmd_seed)

    args = parser.parse_args(argv)
    if getattr(args, "db", None):
        import os
        os.environ["DAYTODAY_DB"] = args.db
    try:
        return args.func(args)
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
