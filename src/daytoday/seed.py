"""Deterministic demo data.

Two purposes: a reviewer can see a populated dashboard immediately, and the
retrieval evaluation needs a corpus with known answers. Everything is dated
relative to the run so the demo never looks stale.
"""
from __future__ import annotations

import random
from datetime import timedelta

from . import rag
from .config import settings
from .db import connect, init_db, utcnow
from .timeparse import now_local

NOTES = [
    ("Project synopsis - final year",
     "Synopsis for the final year project is due on the 12th. Sections required: abstract of "
     "300 words, literature survey with at least 12 references, methodology, expected outcomes "
     "and a Gantt chart for two semesters. Guide said the abstract must state the problem "
     "statement in one sentence before any motivation. Review meeting with the guide every "
     "Tuesday at 4pm in cabin 214."),
    ("Placement prep plan",
     "Aptitude: finish permutations, probability and data interpretation from the Arun Sharma "
     "book. DSA: revise graphs, dynamic programming and sliding window patterns. Two mock "
     "interviews scheduled with the placement cell in the first week of next month. Target "
     "companies: three product firms and two service firms. Keep the resume to one page and "
     "put the project above coursework."),
    ("DBMS unit 3 revision",
     "Normalisation: 1NF to BCNF with examples. Key point - BCNF removes redundancy from "
     "functional dependencies but does not guarantee dependency preservation, which is why 3NF "
     "is often preferred in practice. Transactions: ACID properties, isolation levels and the "
     "dirty read versus phantom read distinction. Practice the two numerical questions from the "
     "2023 paper."),
    ("Wifi and electricity notes",
     "Broadband renewal is 899 per month, auto-debit on the 5th. Electricity bill for the hostel "
     "room comes every second month and is usually around 640. Cylinder booking number is saved "
     "in the phone. Landlord asked for the rent receipt by the 10th."),
    ("Ideas for the project demo",
     "Demo flow: open with a real question, show the tool trace panel, then break the assistant "
     "deliberately by asking about something not in the notes, and show that it says it does not "
     "know instead of inventing an answer. That groundedness check is the strongest part of the "
     "viva. Keep the whole demo under eight minutes and rehearse the offline mode once."),
    ("Gym and sleep routine",
     "Gym four days a week: push, pull, legs, and one full body session. Sleep target seven "
     "hours; last coffee before 4pm. Morning slot works better than evening because the lab is "
     "free before 10am."),
]

TASKS = [
    ("Submit project synopsis to the guide", 3, "high"),
    ("Finish DBMS unit 3 numericals", 1, "high"),
    ("Renew broadband plan", 5, "normal"),
    ("Two mock aptitude tests", 6, "normal"),
    ("Buy a new laptop charger", 9, "low"),
    ("Book the demo slot with the lab assistant", 2, "high"),
    ("Revise graphs and DP patterns", 8, "normal"),
    ("Return the borrowed reference book", 11, "low"),
]

EXPENSES = [
    (180, "canteen lunch", "food", 0),
    (45, "morning chai", "food", 0),
    (899, "broadband renewal", "bills", 1),
    (240, "auto to college", "transport", 1),
    (1250, "groceries for the week", "groceries", 2),
    (320, "xerox of question papers", "education", 3),
    (150, "metro card top-up", "transport", 4),
    (2100, "textbook for DBMS", "education", 5),
    (260, "dinner with friends", "food", 6),
    (140, "pharmacy", "health", 8),
    (499, "music subscription", "entertainment", 10),
    (640, "electricity bill", "bills", 12),
]

JOURNAL = [
    ("Finished the methodology section and the guide approved it without changes.", 5, 4),
    ("Long lab session, productive but tiring. Two numericals still pending.", 4, 2),
    ("Woke up late and skipped the gym, felt off all morning.", 2, 2),
    ("Good study block in the morning, graphs finally make sense.", 4, 4),
    ("Stressed about the synopsis deadline but the plan is clear now.", 3, 3),
    ("Mock aptitude score improved from 42 to 58.", 5, 4),
    ("Low energy, mostly admin work and errands.", 3, 2),
    ("Cleared the pending assignment and had a calm evening.", 4, 3),
]


def seed_demo_data(db_path: str | None = None, reset: bool = True) -> dict:
    init_db(db_path)
    conn = connect(db_path or settings.db_path)
    rng = random.Random(2026)
    try:
        if reset:
            for table in ("tasks", "expenses", "journal", "notes", "note_chunks", "note_fts",
                          "messages", "session_memory", "tool_audit"):
                conn.execute(f"DELETE FROM {table}")

        today = now_local().date()
        note_count = 0
        for title, body in NOTES:
            cursor = conn.execute(
                "INSERT INTO notes (title, body, tags, created_at) VALUES (?,?,?,?)",
                (title, body, "seed", utcnow()))
            rag.index_note(conn, cursor.lastrowid, body)
            note_count += 1

        for title, days_ahead, priority in TASKS:
            due = (today + timedelta(days=days_ahead)).isoformat() + "T18:00:00"
            conn.execute(
                "INSERT INTO tasks (title, due_at, priority, status, tags, created_at)"
                " VALUES (?,?,?,'open','seed',?)",
                (title, due, priority, utcnow()))

        for amount, note, category, days_ago in EXPENSES:
            conn.execute(
                "INSERT INTO expenses (amount_minor, currency, category, note, spent_on, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (amount * 100, settings.currency, category, note,
                 (today - timedelta(days=days_ago)).isoformat(), utcnow()))

        for index, (entry, mood, energy) in enumerate(JOURNAL):
            stamp = utcnow()
            conn.execute(
                "INSERT INTO journal (entry, mood, energy, tags, created_at) VALUES (?,?,?,?,?)",
                (entry, mood, energy, "seed",
                 (today - timedelta(days=index * 2)).isoformat() + stamp[10:]))
        conn.commit()

        return {
            "notes": note_count,
            "note_chunks": conn.execute("SELECT COUNT(*) c FROM note_chunks").fetchone()["c"],
            "tasks": conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"],
            "expenses": conn.execute("SELECT COUNT(*) c FROM expenses").fetchone()["c"],
            "journal_entries": conn.execute("SELECT COUNT(*) c FROM journal").fetchone()["c"],
            "rng_seed": 2026,
        }
    finally:
        conn.close()
