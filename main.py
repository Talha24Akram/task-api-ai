from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # table + seed rows are created on first start only
    yield


app = FastAPI(title="Task API", version="2.0", lifespan=lifespan)


# --- models (unchanged from Assignment 1) -----------------------------------

class TaskCreate(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("title must not be empty")
        return v


def row_to_task(row) -> dict:
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def not_found(task_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Task {task_id} not found")


# --- root & health -----------------------------------------------------------

@app.get("/")
def root():
    return {"name": "Task API", "version": "2.0", "endpoints": ["/tasks"]}


@app.get("/health")
def health():
    return {"status": "ok"}


# --- error handling (same JSON shape as Assignment 1) -------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0]
    field = ".".join(str(p) for p in first_error["loc"] if p != "body")
    return JSONResponse(status_code=400, content={"error": f"{field}: {first_error['msg']}"})


# --- read (SQL SELECT) ---------------------------------------------------------

@app.get("/tasks")
def list_tasks(done: Optional[bool] = None, search: Optional[str] = None):
    # optional filters are pushed into SQL: WHERE done = ? AND title LIKE ?
    sql, params = "SELECT id, title, done FROM tasks", []
    clauses = []
    if done is not None:
        clauses.append("done = ?")
        params.append(int(done))
    if search:
        clauses.append("title LIKE ?")
        params.append(f"%{search}%")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id"
    with db.connect() as conn:
        return [row_to_task(r) for r in conn.execute(sql, params)]


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    with db.connect() as conn:
        row = conn.execute("SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise not_found(task_id)
    return row_to_task(row)


# --- create (SQL INSERT) --------------------------------------------------------

@app.post("/tasks", status_code=201)
def create_task(payload: TaskCreate):
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO tasks (title, done) VALUES (?, 0)", (payload.title,))
        return {"id": cur.lastrowid, "title": payload.title, "done": False}
