"""Digest output — terminal view + markdown report (TICKET-07)."""

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _fetch_jobs(conn: sqlite3.Connection, since: str) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT job_id, company, title, location, url, first_seen, last_seen, is_open
        FROM jobs
        ORDER BY company, first_seen DESC, title
    """).fetchall()


def _group_by_company(rows: list) -> dict:
    grouped: dict[str, dict] = {}
    for r in rows:
        company = r["company"]
        if company not in grouped:
            grouped[company] = {"new": [], "open": [], "closed": []}
        if r["is_open"] == 0:
            grouped[company]["closed"].append(r)
        elif r["first_seen"] >= r["last_seen"]:
            # first_seen == last_seen means seen for the first time today
            grouped[company]["new"].append(r)
        else:
            grouped[company]["open"].append(r)
    return grouped


def print_terminal(conn: sqlite3.Connection, since: Optional[str] = None) -> None:
    """Pretty-print a digest to the terminal."""
    since = since or date.today().isoformat()
    rows = _fetch_jobs(conn, since)
    grouped = _group_by_company(rows)

    total_new = sum(len(v["new"]) for v in grouped.values())
    total_open = sum(len(v["open"]) for v in grouped.values())
    total_closed = sum(len(v["closed"]) for v in grouped.values())

    width = 80
    print("\n" + "=" * width)
    print(f"  JOB TRACKER DIGEST — {date.today().isoformat()}")
    print(f"  {total_new} new  |  {total_open} still open  |  {total_closed} closed")
    print("=" * width)

    for company, buckets in grouped.items():
        all_jobs = buckets["new"] + buckets["open"] + buckets["closed"]
        if not all_jobs:
            continue

        print(f"\n{'─' * width}")
        print(f"  {company.upper()}  ({len(buckets['new'])} new, {len(buckets['open'])} open, {len(buckets['closed'])} closed)")
        print(f"{'─' * width}")

        if buckets["new"]:
            print("\n  🆕 NEW")
            for job in buckets["new"]:
                _print_job_row(job)

        if buckets["open"]:
            print("\n  ✅ STILL OPEN")
            for job in buckets["open"]:
                _print_job_row(job)

        if buckets["closed"]:
            print("\n  ❌ CLOSED")
            for job in buckets["closed"]:
                _print_job_row(job, closed=True)

    print("\n" + "=" * width + "\n")


def _print_job_row(job: sqlite3.Row, closed: bool = False) -> None:
    title = job["title"][:55] + "…" if len(job["title"]) > 55 else job["title"]
    location = (job["location"] or "Remote/Unknown")[:30]
    since_label = f"seen {job['first_seen']}"
    strike = "~~" if closed else ""
    print(f"  {strike}{title:<57}{strike}  📍 {location:<32}  🗓  {since_label}")
    print(f"     🔗 {job['url'][:75]}")


def generate_markdown(conn: sqlite3.Connection, since: Optional[str] = None) -> str:
    """Generate a markdown report and save it to output/digest_YYYY-MM-DD.md."""
    since = since or date.today().isoformat()
    rows = _fetch_jobs(conn, since)
    grouped = _group_by_company(rows)

    total_new = sum(len(v["new"]) for v in grouped.values())
    total_open = sum(len(v["open"]) for v in grouped.values())
    total_closed = sum(len(v["closed"]) for v in grouped.values())

    lines = [
        f"# Job Tracker Digest — {date.today().isoformat()}",
        "",
        f"> **{total_new} new** &nbsp;|&nbsp; **{total_open} still open** &nbsp;|&nbsp; **{total_closed} closed**",
        "",
    ]

    for company, buckets in grouped.items():
        all_jobs = buckets["new"] + buckets["open"] + buckets["closed"]
        if not all_jobs:
            continue

        lines += [
            f"## {company}",
            "",
        ]

        if buckets["new"]:
            lines.append("### 🆕 New")
            lines.append("")
            lines.append("| Title | Location | First Seen | Apply |")
            lines.append("|-------|----------|------------|-------|")
            for job in buckets["new"]:
                loc = job["location"] or "—"
                lines.append(f"| {job['title']} | {loc} | {job['first_seen']} | [Apply]({job['url']}) |")
            lines.append("")

        if buckets["open"]:
            lines.append("### ✅ Still Open")
            lines.append("")
            lines.append("| Title | Location | First Seen | Apply |")
            lines.append("|-------|----------|------------|-------|")
            for job in buckets["open"]:
                loc = job["location"] or "—"
                lines.append(f"| {job['title']} | {loc} | {job['first_seen']} | [Apply]({job['url']}) |")
            lines.append("")

        if buckets["closed"]:
            lines.append("### ❌ Closed / No Longer Listed")
            lines.append("")
            lines.append("| Title | Location | Last Seen |")
            lines.append("|-------|----------|-----------|")
            for job in buckets["closed"]:
                loc = job["location"] or "—"
                lines.append(f"| ~~{job['title']}~~ | {loc} | {job['last_seen']} |")
            lines.append("")

    md = "\n".join(lines)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_file = OUTPUT_DIR / f"digest_{date.today().isoformat()}.md"
    out_file.write_text(md)
    print(f"[digest] saved → {out_file}")

    return md


if __name__ == "__main__":
    from src.db import get_connection
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    print_terminal(conn)
    generate_markdown(conn)
    conn.close()
