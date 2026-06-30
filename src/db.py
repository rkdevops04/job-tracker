"""SQLite schema and upsert helpers (TICKET-01)."""

import json
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "jobs.db"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            ats_type TEXT NOT NULL,
            ats_slug TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            job_id     TEXT    NOT NULL,
            company    TEXT    NOT NULL,
            title      TEXT    NOT NULL,
            location   TEXT,
            url        TEXT,
            first_seen TEXT    NOT NULL,
            last_seen  TEXT    NOT NULL,
            is_open    INTEGER NOT NULL DEFAULT 1,
            raw_json   TEXT,
            PRIMARY KEY (job_id, company)
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_company   ON jobs(company);
        CREATE INDEX IF NOT EXISTS idx_jobs_is_open   ON jobs(is_open);
        CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen);
    """)
    conn.commit()


def upsert_job(conn: sqlite3.Connection, job: dict) -> None:
    """Insert a new job or update last_seen / metadata if it already exists."""
    today = date.today().isoformat()
    conn.execute("""
        INSERT INTO jobs (job_id, company, title, location, url, first_seen, last_seen, is_open, raw_json)
        VALUES (:job_id, :company, :title, :location, :url, :today, :today, 1, :raw_json)
        ON CONFLICT (job_id, company) DO UPDATE SET
            title      = excluded.title,
            location   = excluded.location,
            url        = excluded.url,
            last_seen  = excluded.last_seen,
            is_open    = 1,
            raw_json   = excluded.raw_json
    """, {
        "job_id":   str(job["job_id"]),
        "company":  job["company"],
        "title":    job["title"],
        "location": job.get("location"),
        "url":      job.get("url"),
        "today":    today,
        "raw_json": json.dumps(job.get("raw_json", {})),
    })
    conn.commit()


def mark_closed(conn: sqlite3.Connection, company: str, open_ids: set[str]) -> int:
    """Mark jobs from *company* as closed if their job_id is not in *open_ids*.

    Returns the number of rows updated.
    """
    today = date.today().isoformat()
    cur = conn.execute("""
        UPDATE jobs
        SET is_open = 0, last_seen = ?
        WHERE company = ? AND is_open = 1 AND job_id NOT IN ({placeholders})
    """.format(placeholders=",".join("?" * len(open_ids)) if open_ids else "'__never__'"),
        [today, company, *open_ids] if open_ids else [today, company],
    )
    conn.commit()
    return cur.rowcount
