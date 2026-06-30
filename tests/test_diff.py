"""Tests for diff/snapshot logic (TICKET-04)."""

import pytest

from src.db import get_connection, init_db, upsert_job
from src.diff import apply_snapshot, snapshot_summary, SnapshotResult


@pytest.fixture()
def db(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


def _job(job_id, title="Engineer", company="Acme"):
    return {
        "job_id": str(job_id),
        "company": company,
        "title": title,
        "location": "Remote",
        "url": f"https://example.com/{job_id}",
        "raw_json": {},
    }


# ---------------------------------------------------------------------------
# apply_snapshot
# ---------------------------------------------------------------------------

def test_new_jobs_are_tracked(db):
    result = apply_snapshot(db, "Acme", [_job("j1"), _job("j2")])
    assert result.upserted == 2
    assert set(result.newly_seen) == {"j1", "j2"}
    assert result.reopened == []
    assert result.newly_closed == 0


def test_vanished_jobs_are_closed(db):
    apply_snapshot(db, "Acme", [_job("j1"), _job("j2")])
    result = apply_snapshot(db, "Acme", [_job("j1")])  # j2 gone
    assert result.newly_closed == 1
    row = db.execute("SELECT is_open FROM jobs WHERE job_id='j2'").fetchone()
    assert row["is_open"] == 0


def test_reappeared_jobs_are_reopened(db):
    apply_snapshot(db, "Acme", [_job("j1")])
    db.execute("UPDATE jobs SET is_open=0 WHERE job_id='j1'")
    db.commit()
    result = apply_snapshot(db, "Acme", [_job("j1")])
    assert "j1" in result.reopened
    row = db.execute("SELECT is_open FROM jobs WHERE job_id='j1'").fetchone()
    assert row["is_open"] == 1


def test_empty_feed_closes_all(db):
    apply_snapshot(db, "Acme", [_job("j1"), _job("j2")])
    result = apply_snapshot(db, "Acme", [])
    assert result.newly_closed == 2
    assert result.upserted == 0


def test_snapshot_does_not_affect_other_companies(db):
    apply_snapshot(db, "Acme", [_job("j1", company="Acme")])
    apply_snapshot(db, "Other", [_job("j2", company="Other")])
    # Closing Acme jobs should not touch Other
    apply_snapshot(db, "Acme", [])
    row = db.execute("SELECT is_open FROM jobs WHERE job_id='j2'").fetchone()
    assert row["is_open"] == 1


def test_existing_open_jobs_not_counted_as_new(db):
    apply_snapshot(db, "Acme", [_job("j1")])
    result = apply_snapshot(db, "Acme", [_job("j1")])
    assert result.newly_seen == []
    assert result.upserted == 1


# ---------------------------------------------------------------------------
# snapshot_summary
# ---------------------------------------------------------------------------

def test_snapshot_summary_renders(db):
    r1 = apply_snapshot(db, "Acme", [_job("j1"), _job("j2")])
    r2 = apply_snapshot(db, "Other", [_job("j3", company="Other")])
    summary = snapshot_summary([r1, r2])
    assert "Acme" in summary
    assert "Other" in summary
    assert "TOTAL" in summary
