"""Ingestion orchestrator — reads config.yaml and runs the appropriate adapter."""

import os
import sys
from pathlib import Path

import yaml

from src.db import get_connection, init_db, mark_closed, upsert_job

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
ENV_PATH = Path(__file__).parent.parent / ".env"


def _load_dotenv(env_path: Path = ENV_PATH) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (no external deps)."""
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_ingestion(config_path: Path = CONFIG_PATH, db_path=None) -> None:
    _load_dotenv()
    config = load_config(config_path)
    conn_kwargs = {"db_path": db_path} if db_path else {}
    conn = get_connection(**conn_kwargs)
    init_db(conn)

    for company in config.get("companies", []):
        name = company["name"]
        ats_type = company["ats_type"]
        slug = company["ats_slug"]

        print(f"[ingest] {name} ({ats_type}/{slug})")

        if ats_type == "greenhouse":
            from src.adapters.greenhouse import fetch_jobs
            raw_jobs = fetch_jobs(slug)
        elif ats_type == "lever":
            from src.adapters.lever import fetch_jobs  # noqa: F811
            raw_jobs = fetch_jobs(slug)
        elif ats_type == "jsearch":
            from src.adapters.jsearch import fetch_jobs  # noqa: F811
            pages = company.get("pages", 1)
            raw_jobs = fetch_jobs(slug, pages=pages)
        elif ats_type == "adzuna":
            from src.adapters.adzuna import fetch_jobs  # noqa: F811
            pages = company.get("pages", 1)
            country = company.get("country", "us")
            raw_jobs = fetch_jobs(slug, country=country, pages=pages)
        else:
            print(f"  [WARN] unknown ats_type '{ats_type}' — skipping", file=sys.stderr)
            continue

        for job in raw_jobs:
            job["company"] = name
            upsert_job(conn, job)

        closed = mark_closed(conn, name, {j["job_id"] for j in raw_jobs})
        print(f"  upserted {len(raw_jobs)} jobs, marked {closed} closed")

    conn.close()


if __name__ == "__main__":
    run_ingestion()
