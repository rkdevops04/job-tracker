"""Diff / snapshot logic (TICKET-04).

After each ingestion run, compare the fresh job list from a feed against
what is stored in the DB and:
  - Upsert jobs that are present (handled by db.upsert_job)
  - Mark jobs as closed (is_open=0) when they no longer appear in the feed
  - Never hard-delete rows — history is preserved forever

This module owns the per-company diff lifecycle so ingest.py stays thin.
"""

import sqlite3
from datetime import date

from src.db import mark_closed, upsert_job


class SnapshotResult:
    """Summary of one company's diff run."""

    def __init__(self, company: str):
        self.company = company
        self.upserted: int = 0
        self.newly_closed: int = 0
        self.newly_seen: list[str] = []   # job_ids appearing for the first time
        self.reopened: list[str] = []     # job_ids that were closed and are now open again

    def __repr__(self) -> str:
        return (
            f"SnapshotResult(company={self.company!r}, upserted={self.upserted}, "
            f"newly_closed={self.newly_closed}, new={len(self.newly_seen)}, "
            f"reopened={len(self.reopened)})"
        )


def apply_snapshot(
    conn: sqlite3.Connection,
    company: str,
    fetched_jobs: list[dict],
) -> SnapshotResult:
    """Apply a fresh batch of jobs for *company* to the DB.

    Steps:
      1. Identify jobs that are brand-new (not yet in DB) and ones that were
         previously closed but have reappeared.
      2. Upsert all fetched jobs (updates last_seen, reopens closed ones).
      3. Mark any DB job for this company not in the feed as closed.

    Args:
        conn:         Open SQLite connection.
        company:      Company name (must match the `company` column in jobs table).
        fetched_jobs: Normalised job dicts from an ATS adapter, each must have
                      at least {job_id, company, title, location, url, raw_json}.

    Returns:
        SnapshotResult with counts and notable job_ids.
    """
    result = SnapshotResult(company)

    if not fetched_jobs:
        result.newly_closed = mark_closed(conn, company, set())
        return result

    fetched_ids = {str(j["job_id"]) for j in fetched_jobs}

    # Query current DB state for this company in one shot
    existing = {
        row["job_id"]: row["is_open"]
        for row in conn.execute(
            "SELECT job_id, is_open FROM jobs WHERE company = ?", (company,)
        ).fetchall()
    }

    for job in fetched_jobs:
        job_id = str(job["job_id"])
        if job_id not in existing:
            result.newly_seen.append(job_id)
        elif existing[job_id] == 0:
            result.reopened.append(job_id)

        job["company"] = company
        upsert_job(conn, job)
        result.upserted += 1

    result.newly_closed = mark_closed(conn, company, fetched_ids)
    return result


def snapshot_summary(results: list[SnapshotResult]) -> str:
    """Return a human-readable summary of a list of SnapshotResults."""
    lines = [f"{'Company':<30} {'Upserted':>8} {'New':>6} {'Reopened':>9} {'Closed':>7}"]
    lines.append("-" * 65)
    for r in results:
        lines.append(
            f"{r.company:<30} {r.upserted:>8} {len(r.newly_seen):>6} "
            f"{len(r.reopened):>9} {r.newly_closed:>7}"
        )
    total_upserted = sum(r.upserted for r in results)
    total_new = sum(len(r.newly_seen) for r in results)
    total_reopened = sum(len(r.reopened) for r in results)
    total_closed = sum(r.newly_closed for r in results)
    lines.append("-" * 65)
    lines.append(
        f"{'TOTAL':<30} {total_upserted:>8} {total_new:>6} "
        f"{total_reopened:>9} {total_closed:>7}"
    )
    return "\n".join(lines)
