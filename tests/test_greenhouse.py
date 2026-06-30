"""Tests for Greenhouse adapter + DB upsert logic (TICKET-01 & 02)."""

import json
import sqlite3
from pathlib import Path

import pytest
import responses as rsps_lib

from src.adapters.greenhouse import GREENHOUSE_BASE, fetch_jobs
from src.db import get_connection, init_db, mark_closed, upsert_job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    """In-memory-like SQLite DB in a temp dir."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


FAKE_GH_RESPONSE = {
    "jobs": [
        {
            "id": 1001,
            "title": "Software Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1001",
            "location": {"name": "Remote"},
            "offices": [],
        },
        {
            "id": 1002,
            "title": "Product Manager",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1002",
            "location": {"name": "New York, NY"},
            "offices": [],
        },
    ]
}


# ---------------------------------------------------------------------------
# Greenhouse adapter unit tests
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_fetch_jobs_returns_normalised_list():
    rsps_lib.add(
        rsps_lib.GET,
        f"{GREENHOUSE_BASE}/acmecorp/jobs",
        json=FAKE_GH_RESPONSE,
        status=200,
    )
    jobs = fetch_jobs("acmecorp")

    assert len(jobs) == 2
    assert jobs[0]["job_id"] == "1001"
    assert jobs[0]["title"] == "Software Engineer"
    assert jobs[0]["location"] == "Remote"
    assert jobs[0]["url"].endswith("/1001")


@rsps_lib.activate
def test_fetch_jobs_empty_board():
    rsps_lib.add(
        rsps_lib.GET,
        f"{GREENHOUSE_BASE}/empty/jobs",
        json={"jobs": []},
        status=200,
    )
    assert fetch_jobs("empty") == []


@rsps_lib.activate
def test_fetch_jobs_http_error_raises():
    rsps_lib.add(
        rsps_lib.GET,
        f"{GREENHOUSE_BASE}/bad/jobs",
        status=404,
    )
    with pytest.raises(Exception):
        fetch_jobs("bad")


# ---------------------------------------------------------------------------
# DB upsert tests
# ---------------------------------------------------------------------------

def _make_job(**kwargs):
    base = {
        "job_id": "1001",
        "company": "Acme Corp",
        "title": "Software Engineer",
        "location": "Remote",
        "url": "https://example.com/jobs/1001",
        "raw_json": {},
    }
    base.update(kwargs)
    return base


def test_upsert_inserts_new_job(db):
    upsert_job(db, _make_job())
    row = db.execute("SELECT * FROM jobs WHERE job_id = '1001'").fetchone()
    assert row is not None
    assert row["title"] == "Software Engineer"
    assert row["is_open"] == 1


def test_upsert_updates_existing_job(db):
    upsert_job(db, _make_job())
    upsert_job(db, _make_job(title="Senior Software Engineer"))
    rows = db.execute("SELECT * FROM jobs WHERE job_id = '1001'").fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "Senior Software Engineer"


def test_upsert_preserves_first_seen(db):
    upsert_job(db, _make_job())
    first = db.execute("SELECT first_seen FROM jobs WHERE job_id='1001'").fetchone()[0]
    upsert_job(db, _make_job(title="Updated Title"))
    still_first = db.execute("SELECT first_seen FROM jobs WHERE job_id='1001'").fetchone()[0]
    assert first == still_first


def test_upsert_reopens_closed_job(db):
    upsert_job(db, _make_job())
    db.execute("UPDATE jobs SET is_open=0 WHERE job_id='1001'")
    db.commit()
    upsert_job(db, _make_job())
    row = db.execute("SELECT is_open FROM jobs WHERE job_id='1001'").fetchone()
    assert row["is_open"] == 1


# ---------------------------------------------------------------------------
# mark_closed tests
# ---------------------------------------------------------------------------

def test_mark_closed_flags_missing_jobs(db):
    upsert_job(db, _make_job(job_id="1001"))
    upsert_job(db, _make_job(job_id="1002", title="Designer"))
    closed = mark_closed(db, "Acme Corp", {"1001"})
    assert closed == 1
    row = db.execute("SELECT is_open FROM jobs WHERE job_id='1002'").fetchone()
    assert row["is_open"] == 0


def test_mark_closed_all_when_empty_feed(db):
    upsert_job(db, _make_job(job_id="1001"))
    upsert_job(db, _make_job(job_id="1002", title="Designer"))
    closed = mark_closed(db, "Acme Corp", set())
    assert closed == 2


def test_mark_closed_does_not_affect_other_companies(db):
    upsert_job(db, _make_job(job_id="1001", company="Acme Corp"))
    upsert_job(db, _make_job(job_id="2001", company="Other Co", title="PM"))
    mark_closed(db, "Acme Corp", set())
    row = db.execute("SELECT is_open FROM jobs WHERE job_id='2001'").fetchone()
    assert row["is_open"] == 1
