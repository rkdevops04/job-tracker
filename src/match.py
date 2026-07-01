"""Resume matching — scores open jobs against a resume using TF-IDF (TICKET-06).

No external ML libraries needed. Uses Python's stdlib only.

Scoring approach:
  1. Tokenise resume and job (title + description) into lowercase words
  2. Build a TF-IDF weighted term vector for each document
  3. Compute cosine similarity between resume vector and each job vector
  4. Return jobs ranked highest → lowest
"""

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Optional

RESUME_PATH = Path(__file__).parent.parent / "resume.txt"

# Common English stop words — excluded from scoring
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "this", "that", "these", "those", "we", "our",
    "you", "your", "they", "their", "it", "its", "as", "if", "so", "not",
    "no", "can", "all", "any", "both", "each", "more", "also", "than",
    "then", "when", "where", "who", "which", "what", "how", "about", "into",
    "through", "during", "including", "while", "per", "other", "such",
}


def _tokenise(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stop words and short tokens."""
    tokens = re.findall(r"[a-z][a-z0-9\+\#]*", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def _term_freq(tokens: list[str]) -> dict[str, float]:
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    total = len(tokens) or 1
    return {t: count / total for t, count in tf.items()}


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    shared = set(vec_a) & set(vec_b)
    if not shared:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] for t in shared)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _build_idf(documents: list[list[str]]) -> dict[str, float]:
    n = len(documents)
    df: dict[str, int] = {}
    for doc in documents:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    return {term: math.log(n / count) for term, count in df.items()}


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = _term_freq(tokens)
    return {t: tf[t] * idf.get(t, 0) for t in tf}


def score_jobs(
    conn: sqlite3.Connection,
    resume_path: Path = RESUME_PATH,
    top_n: Optional[int] = None,
) -> list[dict]:
    """Score all open jobs against the resume and return ranked results.

    Returns a list of dicts sorted by score descending:
        job_id, company, title, location, url, score, matched_keywords,
        missing_keywords
    """
    resume_text = resume_path.read_text()
    resume_tokens = _tokenise(resume_text)

    if not resume_tokens:
        raise ValueError(f"Resume at {resume_path} appears empty or has no readable text.")

    rows = conn.execute("""
        SELECT job_id, company, title, location, url, raw_json
        FROM jobs
        WHERE is_open = 1
    """).fetchall()

    if not rows:
        return []

    # Build token lists for each job
    job_token_lists = []
    for row in rows:
        raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
        description = raw.get("description", "") or ""
        text = f"{row['title']} {row['title']} {description}"  # title weighted ×2
        job_token_lists.append(_tokenise(text))

    # IDF over all documents (resume + all jobs)
    all_docs = [resume_tokens] + job_token_lists
    idf = _build_idf(all_docs)

    resume_vec = _tfidf_vector(resume_tokens, idf)

    results = []
    for row, job_tokens in zip(rows, job_token_lists):
        job_vec = _tfidf_vector(job_tokens, idf)
        score = _cosine_similarity(resume_vec, job_vec)

        # Top matched keywords: resume terms present in job, sorted by weight
        matched = sorted(
            [t for t in resume_vec if t in job_vec],
            key=lambda t: resume_vec[t] * job_vec.get(t, 0),
            reverse=True,
        )[:10]

        missing = sorted(
            [t for t in resume_vec if t not in job_vec],
            key=lambda t: resume_vec[t],
            reverse=True,
        )[:10]

        results.append({
            "job_id":           row["job_id"],
            "company":          row["company"],
            "title":            row["title"],
            "location":         row["location"],
            "url":              row["url"],
            "score":            round(score, 4),
            "matched_keywords": matched,
            "missing_keywords": missing,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n] if top_n else results


def print_matches(
    conn: sqlite3.Connection,
    resume_path: Path = RESUME_PATH,
    top_n: int = 10,
) -> None:
    """Print top-N matched jobs to the terminal."""
    results = score_jobs(conn, resume_path=resume_path, top_n=top_n)

    width = 80
    print("\n" + "=" * width)
    print(f"  RESUME MATCH RESULTS  —  top {min(top_n, len(results))} of {len(results)} open jobs")
    print(f"  Resume: {resume_path.name}")
    print("=" * width)

    if not results:
        print("  No open jobs found in the database.")
        print("=" * width + "\n")
        return

    for rank, job in enumerate(results, 1):
        bar_len = int(job["score"] * 400)  # scale to ~40 chars max
        bar = "█" * min(bar_len, 40)
        pct = f"{job['score'] * 100:.1f}%"
        title = job["title"][:52] + "…" if len(job["title"]) > 52 else job["title"]
        loc = (job["location"] or "Remote/Unknown")[:28]

        print(f"\n  #{rank:02d}  {title}")
        print(f"       📍 {loc:<30}  🏢 {job['company']}")
        print(f"       Match: {bar:<40} {pct}")
        if job["matched_keywords"]:
            print(f"       🔑 {', '.join(job['matched_keywords'])}")
        print(f"       🔗 {job['url'][:72]}")

    print("\n" + "=" * width + "\n")


if __name__ == "__main__":
    from src.db import get_connection
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    print_matches(conn, top_n=10)
    conn.close()
