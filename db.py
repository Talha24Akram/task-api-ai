"""SQLite storage layer. The API in main.py never talks to the database file directly."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# tasks.db lives next to this file, so the same file is used however the server is started
DB_PATH = Path(__file__).resolve().parent / "tasks.db"

SEED_TASKS = [
    ("Buy milk", 0),
    ("Walk the dog", 0),
    ("Write README", 1),
]


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create the file and table if missing; insert the 3 example tasks only if the table is empty."""
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                done  BOOLEAN NOT NULL DEFAULT 0
            )
            """
        )
        (count,) = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
        if count == 0:
            conn.executemany("INSERT INTO tasks (title, done) VALUES (?, ?)", SEED_TASKS)
