"""Job match agent.

Compares open job descriptions against resume text, ranks jobs by score,
prints a concise terminal summary, and saves a markdown report.
"""

import argparse
from datetime import date
from pathlib import Path

from src.db import DB_PATH, get_connection
from src.match import RESUME_PATH, score_jobs

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _render_markdown(results: list[dict], resume_path: Path, min_score: float) -> str:
    lines = [
        f"# Resume Match Report - {date.today().isoformat()}",
        "",
        f"Resume: {resume_path.name}",
        f"Minimum score filter: {min_score:.4f}",
        f"Matched jobs: {len(results)}",
        "",
    ]

    if not results:
        lines.append("No matching open jobs found.")
        return "\n".join(lines)

    lines.extend([
        "| Rank | Company | Title | Location | Score | Apply | Matched Keywords |",
        "|------|---------|-------|----------|-------|-------|------------------|",
    ])

    for idx, job in enumerate(results, 1):
        keywords = ", ".join(job["matched_keywords"]) if job["matched_keywords"] else "-"
        location = job["location"] or "-"
        lines.append(
            "| "
            f"{idx} | {job['company']} | {job['title']} | {location} | "
            f"{job['score']:.4f} | [Apply]({job['url']}) | {keywords} |"
        )

    return "\n".join(lines)


def run_agent(
    top_n: int = 10,
    min_score: float = 0.0,
    resume_path: Path = RESUME_PATH,
    output_dir: Path = OUTPUT_DIR,
    db_path: Path = DB_PATH,
) -> Path:
    """Run matching and write ranked output to output/matches_YYYY-MM-DD.md."""
    conn = get_connection(db_path)
    try:
        results = score_jobs(conn, resume_path=resume_path, top_n=None)
    finally:
        conn.close()

    if min_score > 0:
        results = [job for job in results if job["score"] >= min_score]

    results = results[:top_n]

    print(f"[agent] scored {len(results)} jobs (top_n={top_n}, min_score={min_score:.4f})")
    for idx, job in enumerate(results, 1):
        print(f"  {idx:02d}. {job['score']:.4f}  {job['title']}  ->  {job['url']}")

    output_dir.mkdir(exist_ok=True)
    out_file = output_dir / f"matches_{date.today().isoformat()}.md"
    out_file.write_text(_render_markdown(results, resume_path=resume_path, min_score=min_score))
    print(f"[agent] saved -> {out_file}")
    return out_file


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run resume-to-job match agent.")
    parser.add_argument("--top", type=int, default=10, help="Number of top matches to keep.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Only keep jobs with score >= min-score.",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=RESUME_PATH,
        help="Path to resume text file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory where match report markdown is written.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DB_PATH,
        help="Path to SQLite jobs database.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run_agent(
        top_n=args.top,
        min_score=args.min_score,
        resume_path=args.resume,
        output_dir=args.output_dir,
        db_path=args.db_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())