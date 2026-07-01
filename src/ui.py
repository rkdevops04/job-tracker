"""Local UI for job tracker data and resume match results.

Run with:
    streamlit run src/ui.py
"""

import csv
import json
import sqlite3
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from typing import Optional

import streamlit as st

from src.db import DB_PATH
from src.match import RESUME_PATH, score_jobs


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _extract_job_type(raw_json: str) -> str:
    if not raw_json:
        return "Unknown"
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        return "Unknown"

    contract_type = (raw.get("contract_type") or "").strip().lower()
    if contract_type in {"permanent", "full_time", "full-time", "full time"}:
        return "Full-time"
    if contract_type in {"contract", "temporary", "temp"}:
        return "Contract"

    if raw.get("contract_time"):
        return str(raw.get("contract_time")).replace("_", " ").title()

    return "Unknown"


def _fetch_jobs(
    conn: sqlite3.Connection,
    open_only: bool,
    company: str,
    search_text: str,
    location_text: str,
) -> list[dict]:
    clauses = []
    params = []
    if open_only:
        clauses.append("is_open = 1")
    if company and company != "All":
        clauses.append("company = ?")
        params.append(company)
    if search_text:
        clauses.append("LOWER(title) LIKE ?")
        params.append(f"%{search_text.lower()}%")
    if location_text:
        clauses.append("LOWER(COALESCE(location, '')) LIKE ?")
        params.append(f"%{location_text.lower()}%")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT company, title, location, url, first_seen, last_seen, is_open, raw_json
        FROM jobs
        {where_sql}
        ORDER BY is_open DESC, company, last_seen DESC
        """,
        params,
    ).fetchall()

    return [
        {
            "Company": r["company"],
            "Title": r["title"],
            "Location": r["location"] or "Unknown",
            "Job Type": _extract_job_type(r["raw_json"]),
            "Open": "Yes" if r["is_open"] else "No",
            "Jon Opened": r["first_seen"],
            "First Seen": r["first_seen"],
            "Last Seen": r["last_seen"],
            "Apply URL": r["url"] or "",
        }
        for r in rows
    ]


def _fetch_companies(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT company FROM jobs ORDER BY company").fetchall()
    return [r[0] for r in rows]


def _fetch_summary(conn: sqlite3.Connection) -> dict:
    open_jobs = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_open = 1").fetchone()[0]
    closed_jobs = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_open = 0").fetchone()[0]
    companies = conn.execute("SELECT COUNT(DISTINCT company) FROM jobs").fetchone()[0]
    latest_seen = conn.execute("SELECT MAX(last_seen) FROM jobs").fetchone()[0]
    return {
        "open_jobs": open_jobs,
        "closed_jobs": closed_jobs,
        "companies": companies,
        "latest_seen": latest_seen or "-",
    }


def _read_latest_report(prefix: str) -> tuple[str, str]:
    output_dir = Path(__file__).parent.parent / "output"
    files = sorted(output_dir.glob(f"{prefix}_*.md"), reverse=True)
    if not files:
        return "", ""
    latest = files[0]
    return latest.name, latest.read_text()


def _score_label(score: float) -> str:
    if score >= 8.0:
        return "Strong"
    if score >= 6.0:
        return "Good"
    if score > 1.0:
        return "Weak"
    return "No overlap"


def _score_1_to_10(raw_score: float) -> float:
    """Map cosine score in [0, 1] to user-friendly [1, 10] scale."""
    return round(1 + (9 * raw_score), 2)


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 1.8rem;
            max-width: 1280px;
        }
        .jt-banner {
            border-radius: 14px;
            padding: 1rem 1.2rem;
            background: linear-gradient(120deg, #f2f7ff 0%, #f7fff3 100%);
            border: 1px solid #d8e8d8;
            margin-bottom: 1rem;
        }
        .jt-card {
            border: 1px solid #d7dde5;
            border-radius: 12px;
            padding: 0.8rem 0.9rem;
            margin-bottom: 0.6rem;
            background: #ffffff;
        }
        .jt-muted {
            color: #4b5563;
            font-size: 0.92rem;
        }
        .jt-badge {
            display: inline-block;
            padding: 0.15rem 0.45rem;
            border-radius: 999px;
            font-size: 0.78rem;
            margin: 0.08rem 0.2rem 0.08rem 0;
            border: 1px solid;
        }
        .jt-hit {
            background: #ecfdf3;
            color: #166534;
            border-color: #86efac;
        }
        .jt-miss {
            background: #fff1f2;
            color: #9f1239;
            border-color: #fda4af;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _matches_to_csv(rows: list[dict]) -> str:
    header = [
        "rank",
        "score",
        "fit",
        "company",
        "title",
        "location",
        "opened_on",
        "matched_keywords",
        "missing_from_resume",
        "improve_to_8",
        "apply_url",
    ]
    sio = StringIO()
    writer = csv.writer(sio)
    writer.writerow(header)
    for row in rows:
        writer.writerow([
            str(row["Rank"]),
            str(row["Score"]),
            row["Fit"],
            row["Company"],
            row["Title"],
            row["Location"],
            row["Opened On"],
            row["Keywords"],
            row["Missing From Resume"],
            row["Improve To 8"],
            row["Apply URL"],
        ])
    return sio.getvalue()


def _convert_text_to_docx_bytes(text: str) -> Optional[bytes]:
    """Convert plain text to DOCX bytes using macOS textutil.

    Note: this keeps content but not the original Word styling/template.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_txt = tmp_path / "resume.txt"
        out_docx = tmp_path / "resume.docx"
        in_txt.write_text(text)

        result = subprocess.run(
            ["textutil", "-convert", "docx", str(in_txt), "-output", str(out_docx)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not out_docx.exists():
            return None
        return out_docx.read_bytes()


_SKILL_CATEGORY_KEYWORDS = {
    "Reliability": {
        "reliability", "sre", "incident", "postmortem", "availability", "uptime", "mttr", "sla", "slo", "sli", "error"
    },
    "Cloud": {
        "aws", "gcp", "azure", "cloud", "ec2", "iam", "vpc", "eks", "lambda"
    },
    "Containers": {
        "kubernetes", "k8s", "docker", "helm", "container", "orchestration"
    },
    "Observability": {
        "observability", "monitoring", "metrics", "alerts", "alerting", "splunk", "signalfx", "grafana", "prometheus", "cloudwatch", "logging", "tracing"
    },
    "Automation": {
        "automation", "terraform", "iac", "ansible", "pipeline", "jenkins", "github", "actions", "cicd", "gitops"
    },
    "Platform": {
        "platform", "infrastructure", "engineering", "devops", "network", "security", "performance", "scalability"
    },
}


def _categorize_missing_keywords(missing: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for kw in missing:
        kw_lower = kw.lower()
        matched_category = None
        for category, vocab in _SKILL_CATEGORY_KEYWORDS.items():
            if any(token in kw_lower for token in vocab):
                matched_category = category
                break

        category = matched_category or "Role Terms"
        grouped.setdefault(category, []).append(kw)
    return grouped


def _improve_to_target_plan(job: dict, target_score: float = 8.0) -> str:
    current_score = _score_1_to_10(job["score"])
    if current_score >= target_score:
        return "Already at/above target score. Tailor role bullets with quantified impact and ownership depth."

    missing = job.get("missing_from_resume_keywords", [])
    if not missing:
        return "Low lexical overlap. Mirror the job terminology directly and add measurable outcomes."

    grouped = _categorize_missing_keywords(missing)
    top_categories = list(grouped.items())[:3]
    parts = []
    for category, words in top_categories:
        parts.append(f"{category}: {', '.join(words[:3])}")

    return (
        "Priority gaps -> " + " | ".join(parts) + ". "
        "To move toward 8/10, add 2-3 resume bullets using these exact terms with production outcomes "
        "(uptime, MTTR, incident reduction, deployment speed, automation hours saved)."
    )


def main() -> None:
    st.set_page_config(page_title="Job Tracker UI", layout="wide")
    _inject_styles()

    st.markdown(
        """
        <div class="jt-banner">
          <h2 style="margin:0;">Job Tracker Command Center</h2>
          <div class="jt-muted">Prioritize high-fit roles, keep an application queue, and move fast on fresh openings.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Settings")
        db_path_str = st.text_input("Database path", value=str(DB_PATH))
        resume_path_str = st.text_input("Resume path", value=str(RESUME_PATH))
        top_n = st.slider("Top matches", min_value=5, max_value=100, value=25, step=5)
        min_score = st.slider("Min match score (1-10)", min_value=1.0, max_value=10.0, value=1.0, step=0.1)
        st.caption("Tip: start with min score 3.0 to hide weak matches.")

    db_path = Path(db_path_str)
    resume_path = Path(resume_path_str)
    if not db_path.exists():
        st.error(f"Database not found at: {db_path}")
        st.stop()
    if not resume_path.exists():
        st.error(f"Resume file not found at: {resume_path}")
        st.stop()

    conn = _connect(db_path)
    try:
        companies = ["All"] + _fetch_companies(conn)
        summary = _fetch_summary(conn)
        scored_jobs = score_jobs(conn, resume_path=resume_path, top_n=None)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Open Jobs", summary["open_jobs"])
        m2.metric("Closed Jobs", summary["closed_jobs"])
        m3.metric("Companies", summary["companies"])
        m4.metric("Latest Snapshot", summary["latest_seen"])

        tab_jobs, tab_matches, tab_queue, tab_resume, tab_reports = st.tabs(
            ["Jobs", "Matches", "Apply Queue", "Resume", "Reports"]
        )

        with tab_jobs:
            col1, col2, col3, col4 = st.columns([1.0, 1.1, 1.2, 1.2])
            with col1:
                open_only = st.checkbox("Show open jobs only", value=True)
            with col2:
                selected_company = st.selectbox("Company", companies)
            with col3:
                location_filter = st.text_input("Location contains", value="")
            with col4:
                title_filter = st.text_input("Title contains", value="")

            jobs = _fetch_jobs(
                conn,
                open_only=open_only,
                company=selected_company,
                search_text=title_filter,
                location_text=location_filter,
            )
            st.subheader(f"Jobs ({len(jobs)})")
            if jobs:
                st.dataframe(
                    jobs,
                    use_container_width=True,
                    column_config={
                        "Apply URL": st.column_config.LinkColumn("Apply URL"),
                    },
                    hide_index=True,
                )
            else:
                st.info("No jobs found for current filters.")

        with tab_matches:
            min_raw_score = (min_score - 1.0) / 9.0
            filtered = [r for r in scored_jobs if r["score"] >= min_raw_score][:top_n]

            st.subheader(f"Matches ({len(filtered)})")
            if filtered:
                st.bar_chart(
                    {
                        "Score (1-10)": [_score_1_to_10(r["score"]) for r in filtered[:15]],
                    }
                )

                match_rows = [
                    {
                        "Rank": i,
                        "Score": _score_1_to_10(r["score"]),
                        "Fit": _score_label(_score_1_to_10(r["score"])),
                        "Company": r["company"],
                        "Title": r["title"],
                        "Location": r["location"] or "Unknown",
                        "Opened On": r.get("first_seen", "-"),
                        "Keywords": ", ".join(r["matched_keywords"]),
                        "Missing From Resume": ", ".join(r.get("missing_from_resume_keywords", [])),
                        "Improve To 8": _improve_to_target_plan(r, target_score=8.0),
                        "Apply URL": r["url"],
                    }
                    for i, r in enumerate(filtered, 1)
                ]

                st.download_button(
                    "Download matches CSV",
                    data=_matches_to_csv(match_rows),
                    file_name="matches_export.csv",
                    mime="text/csv",
                )

                st.dataframe(
                    match_rows,
                    use_container_width=True,
                    column_config={
                        "Apply URL": st.column_config.LinkColumn("Apply URL"),
                    },
                    hide_index=True,
                )
            else:
                st.info("No matching jobs found. Try lowering the minimum score.")

        with tab_queue:
            st.subheader("Actionable Application Queue")
            st.caption("Use this as your daily apply list: strongest matches first.")
            st.caption("Missing from resume = terms found in the job post but not found in your resume text.")

            min_raw_score = (min_score - 1.0) / 9.0
            queue = [r for r in scored_jobs if r["score"] >= min_raw_score][:10]

            if not queue:
                st.info("Queue is empty with current score filter.")
            else:
                for idx, job in enumerate(queue, 1):
                    hit_badges = " ".join(
                        f'<span class="jt-badge jt-hit">{k}</span>'
                        for k in job["matched_keywords"][:8]
                    ) or '<span class="jt-muted">No direct keyword hits</span>'

                    miss_badges = " ".join(
                        f'<span class="jt-badge jt-miss">{k}</span>'
                        for k in job.get("missing_from_resume_keywords", [])[:8]
                    ) or '<span class="jt-muted">No major misses</span>'

                    resume_extra_badges = " ".join(
                        f'<span class="jt-badge jt-hit">{k}</span>'
                        for k in job.get("resume_only_keywords", [])[:6]
                    ) or '<span class="jt-muted">No extra strengths</span>'

                    st.markdown(
                        f"""
                        <div class="jt-card">
                          <b>{idx:02d}. {job['title']}</b><br/>
                                                                                                        <span class="jt-muted">{job['company']} | {job['location'] or 'Unknown'} | opened {job.get('first_seen', '-')} | score {_score_1_to_10(job['score']):.2f}/10 ({_score_label(_score_1_to_10(job['score']))})</span><br/>
                          <span class="jt-muted">Skill hits:</span><br/>
                          {hit_badges}<br/>
                          <span class="jt-muted">Missing from resume:</span><br/>
                          {miss_badges}<br/>
                          <span class="jt-muted">Resume strengths not required by this role:</span><br/>
                          {resume_extra_badges}<br/>
                                                    <span class="jt-muted">Improve to 8/10:</span><br/>
                                                    <span class="jt-muted">{_improve_to_target_plan(job, target_score=8.0)}</span><br/>
                          <a href="{job['url']}" target="_blank">Open application link</a>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        with tab_resume:
            st.subheader("Resume Editor")
            st.caption("Edit resume content here and save to refresh future matching.")
            st.info(
                "Formatting note: your original DOCX keeps its font/style. "
                "Matching runs on this plain-text resume content."
            )

            source_docx_default = "/Users/rakeshkuna/Downloads/DevOps_SRE_Resume_Updated.docx"
            source_docx_path = st.text_input(
                "Source DOCX path (optional)",
                value=source_docx_default,
                help="Use this to download the original styled Word resume from UI.",
            )

            current_resume = resume_path.read_text()
            edited_resume = st.text_area(
                "Resume text",
                value=current_resume,
                height=480,
                help="This writes directly to the configured resume file path.",
            )

            col_save, col_reset = st.columns([1, 1])
            with col_save:
                if st.button("Save Resume", type="primary"):
                    resume_path.write_text(edited_resume)
                    st.success("Resume saved successfully.")
                    st.rerun()
            with col_reset:
                st.download_button(
                    "Download Resume",
                    data=edited_resume,
                    file_name=resume_path.name,
                    mime="text/plain",
                )

            updated_docx = _convert_text_to_docx_bytes(edited_resume)
            if updated_docx:
                st.download_button(
                    "Download Updated DOCX (from editor text)",
                    data=updated_docx,
                    file_name="resume_updated_from_editor.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                st.caption("This file includes your latest edits, but style is regenerated from plain text.")

            docx_path = Path(source_docx_path.strip()) if source_docx_path.strip() else None
            if docx_path and docx_path.exists() and docx_path.suffix.lower() == ".docx":
                st.download_button(
                    "Download Source DOCX (with style)",
                    data=docx_path.read_bytes(),
                    file_name=docx_path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                st.caption("This keeps original style/template and may not include edits made only in this text editor.")
            elif source_docx_path.strip():
                st.caption("Source DOCX path not found. Update the path to enable styled DOCX download.")

        with tab_reports:
            digest_name, digest_text = _read_latest_report("digest")
            matches_name, matches_text = _read_latest_report("matches")

            st.subheader("Latest Digest")
            if digest_text:
                st.caption(digest_name)
                st.markdown(digest_text)
            else:
                st.info("No digest markdown found in output folder.")

            st.subheader("Latest Match Report")
            if matches_text:
                st.caption(matches_name)
                st.markdown(matches_text)
            else:
                st.info("No match report markdown found in output folder.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()