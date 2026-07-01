import sqlite3

from src.agent import run_agent
from src.db import get_connection, init_db, upsert_job


def _seed_job(conn: sqlite3.Connection, job_id: str, title: str, description: str) -> None:
    upsert_job(conn, {
        "job_id": job_id,
        "company": "Google SRE",
        "title": title,
        "location": "California",
        "url": f"https://example.com/{job_id}",
        "raw_json": {"description": description},
    })


def test_run_agent_writes_ranked_report(tmp_path):
    db_path = tmp_path / "jobs.db"
    resume_path = tmp_path / "resume.txt"
    output_dir = tmp_path / "output"
    resume_path.write_text("python kubernetes sre reliability automation")

    conn = get_connection(db_path)
    init_db(conn)
    _seed_job(conn, "1", "Site Reliability Engineer", "kubernetes python automation")
    _seed_job(conn, "2", "Backend Engineer", "java spring services")
    conn.close()

    out_file = run_agent(
        top_n=1,
        resume_path=resume_path,
        output_dir=output_dir,
        db_path=db_path,
    )

    assert out_file.exists()
    content = out_file.read_text()
    assert "Resume Match Report" in content
    assert "Site Reliability Engineer" in content
    assert "https://example.com/1" in content
    assert "Backend Engineer" not in content


def test_run_agent_applies_min_score(tmp_path):
    db_path = tmp_path / "jobs.db"
    resume_path = tmp_path / "resume.txt"
    output_dir = tmp_path / "output"
    resume_path.write_text("python kubernetes sre reliability automation")

    conn = get_connection(db_path)
    init_db(conn)
    _seed_job(conn, "1", "Data Entry", "excel typing office")
    conn.close()

    out_file = run_agent(
        top_n=10,
        min_score=0.5,
        resume_path=resume_path,
        output_dir=output_dir,
        db_path=db_path,
    )

    assert out_file.exists()
    content = out_file.read_text()
    assert "No matching open jobs found." in content