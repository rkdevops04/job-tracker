"""Tests for resume matching (TICKET-06)."""

import json
import sqlite3
from pathlib import Path

import pytest

from src.db import get_connection, init_db, upsert_job
from src.match import _tokenise, _cosine_similarity, _build_idf, score_jobs


@pytest.fixture()
def db(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture()
def resume_file(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text(
        "Python Kubernetes GCP site reliability engineering SRE Linux monitoring "
        "Terraform Docker CI/CD observability incident response distributed systems"
    )
    return path


def _insert_job(conn, job_id, title, description=""):
    raw = {"description": description}
    conn.execute("""
        INSERT INTO jobs (job_id, company, title, location, url, first_seen, last_seen, is_open, raw_json)
        VALUES (?, 'TestCo', ?, 'Remote', 'https://example.com', '2026-01-01', '2026-01-01', 1, ?)
    """, (job_id, title, json.dumps(raw)))
    conn.commit()


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

def test_tokenise_removes_stop_words():
    tokens = _tokenise("the quick brown fox and a dog")
    assert "the" not in tokens
    assert "and" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens


def test_tokenise_lowercases():
    assert "python" in _tokenise("Python")


def test_tokenise_handles_tech_terms():
    tokens = _tokenise("Kubernetes GCP CI/CD C++ Python3")
    assert "kubernetes" in tokens
    assert "gcp" in tokens
    assert "python3" in tokens


def test_cosine_similarity_identical_vectors():
    vec = {"python": 0.5, "sre": 0.3}
    assert _cosine_similarity(vec, vec) == pytest.approx(1.0)


def test_cosine_similarity_no_overlap():
    assert _cosine_similarity({"python": 1.0}, {"java": 1.0}) == 0.0


def test_cosine_similarity_partial_overlap():
    a = {"python": 1.0, "sre": 1.0}
    b = {"python": 1.0, "java": 1.0}
    score = _cosine_similarity(a, b)
    assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_score_jobs_ranks_best_match_first(db, resume_file):
    _insert_job(db, "j1", "Java Developer", "Java Spring Boot microservices")
    _insert_job(db, "j2", "Site Reliability Engineer",
                "Python Kubernetes GCP SRE monitoring Linux Terraform Docker")

    results = score_jobs(db, resume_path=resume_file)
    assert results[0]["job_id"] == "j2"
    assert results[0]["score"] > results[1]["score"]


def test_score_jobs_includes_matched_keywords(db, resume_file):
    _insert_job(db, "j1", "SRE", "Python Kubernetes GCP monitoring")
    results = score_jobs(db, resume_path=resume_file)
    assert len(results[0]["matched_keywords"]) > 0


def test_score_jobs_skips_closed_jobs(db, resume_file):
    _insert_job(db, "j1", "SRE Open", "Python Kubernetes")
    _insert_job(db, "j2", "SRE Closed", "Python Kubernetes")
    db.execute("UPDATE jobs SET is_open=0 WHERE job_id='j2'")
    db.commit()
    results = score_jobs(db, resume_path=resume_file)
    assert all(r["job_id"] != "j2" for r in results)


def test_score_jobs_empty_db(db, resume_file):
    assert score_jobs(db, resume_path=resume_file) == []


def test_score_jobs_empty_resume_raises(db, tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("   ")
    _insert_job(db, "j1", "SRE", "Python")
    with pytest.raises(ValueError, match="empty"):
        score_jobs(db, resume_path=empty)


def test_score_jobs_top_n(db, resume_file):
    for i in range(5):
        _insert_job(db, f"j{i}", f"SRE {i}", "Python Kubernetes GCP")
    results = score_jobs(db, resume_path=resume_file, top_n=3)
    assert len(results) == 3
