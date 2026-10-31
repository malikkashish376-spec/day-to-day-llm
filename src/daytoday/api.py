"""FastAPI surface.

Design note: the HTTP write endpoints do not re-implement business logic.
They dispatch through the same ``ToolRegistry`` the agent uses, so a task
created from the UI is validated, stored and audited exactly like one the
model created. One code path, one set of tests, no drift between the
conversational and the button-driven interface.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import rag
from .agent import Agent
from .config import PROJECT_ROOT
from .db import connect, init_db
from .tools import build_registry
from .tools.registry import ToolError

WEB_DIR = PROJECT_ROOT / "web"
agent = Agent()
registry = build_registry()

app = FastAPI(
    title="DayToDay-LLM",
    version="1.0.0",
    description="A grounded, local-first assistant for everyday tasks, money, mood and notes.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.on_event("startup")
def _startup() -> None:
    init_db()


# -- schemas ---------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = "default"


class TaskCreate(BaseModel):
    title: str
    when: str | None = None
    priority: str = "normal"
    tags: str = ""


class ExpenseCreate(BaseModel):
    amount: str
    note: str = ""
    category: str | None = None
    when: str | None = None


class JournalCreate(BaseModel):
    entry: str
    mood: int | None = None
    energy: int | None = None
    tags: str = ""


class NoteCreate(BaseModel):
    body: str
    title: str | None = None
    tags: str = ""


def _run(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    conn = connect()
    try:
        result = registry.execute(tool, args, conn)
    finally:
        conn.close()
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return result


# -- chat ------------------------------------------------------------------
@app.post("/api/chat")
async def chat(request: ChatRequest) -> JSONResponse:
    result = await agent.respond(request.message, request.session_id)
    return JSONResponse(result.to_dict())


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", **agent.stats()}


@app.get("/api/metrics")
async def metrics() -> dict[str, Any]:
    return agent.stats()


# -- tasks -----------------------------------------------------------------
@app.get("/api/tasks")
def list_tasks(status: str = Query("open")) -> dict[str, Any]:
    return _run("list_tasks", {"status": status})


@app.post("/api/tasks", status_code=201)
def create_task(payload: TaskCreate) -> dict[str, Any]:
    return _run("add_task", payload.model_dump())


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int) -> dict[str, Any]:
    return _run("complete_task", {"task_id": task_id})


# -- money -----------------------------------------------------------------
@app.get("/api/expenses")
def list_expenses(limit: int = 20) -> dict[str, Any]:
    return _run("list_expenses", {"limit": limit})


@app.post("/api/expenses", status_code=201)
def create_expense(payload: ExpenseCreate) -> dict[str, Any]:
    return _run("add_expense", payload.model_dump())


@app.get("/api/expenses/summary")
def expense_summary(period: str = "month") -> dict[str, Any]:
    return _run("spending_summary", {"period": period})


# -- journal ---------------------------------------------------------------
@app.post("/api/journal", status_code=201)
def create_journal(payload: JournalCreate) -> dict[str, Any]:
    return _run("log_journal", payload.model_dump())


@app.get("/api/journal/trend")
def journal_trend(days: int = 14) -> dict[str, Any]:
    return _run("mood_trend", {"days": days})


# -- notes -----------------------------------------------------------------
@app.post("/api/notes", status_code=201)
def create_note(payload: NoteCreate) -> dict[str, Any]:
    return _run("add_note", payload.model_dump())


@app.get("/api/notes/search")
def search_notes(q: str, k: int = 4) -> dict[str, Any]:
    conn = connect()
    try:
        return {"query": q, "hits": rag.search_notes(conn, q, k=k)}
    finally:
        conn.close()


# -- planning --------------------------------------------------------------
@app.get("/api/plan")
def plan(when: str = "today") -> dict[str, Any]:
    return _run("plan_day", {"when": when})


@app.get("/api/review")
def review() -> dict[str, Any]:
    return _run("weekly_review", {})


# -- static UI -------------------------------------------------------------
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")
