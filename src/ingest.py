"""Ingestion orchestrator — reads config.yaml and runs the appropriate adapter."""

import os
import sys
from pathlib import Path

import yaml

from src.db import get_connection, init_db
from src.diff import apply_snapshot, snapshot_summary, SnapshotResult

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


def run_ingestion(config_path: Path = CONFIG_PATH, db_path=None) -> list[SnapshotResult]:
    _load_dotenv()
    config = load_config(config_path)
    conn_kwargs = {"db_path": db_path} if db_path else {}
    conn = get_connection(**conn_kwargs)
    init_db(conn)

    results = []
    for company in config.get("companies", []):
        name = company["name"]
        ats_type = company["ats_type"]
        slug = company["ats_slug"]

        print(f"[ingest] {name} ({ats_type}/{slug})")

        try:
            if ats_type == "greenhouse":
                from src.adapters.greenhouse import fetch_jobs as fetch_greenhouse_jobs

                raw_jobs = fetch_greenhouse_jobs(slug)
            elif ats_type == "lever":
                from src.adapters.lever import fetch_jobs as fetch_lever_jobs

                raw_jobs = fetch_lever_jobs(slug)
            elif ats_type == "jsearch":
                from src.adapters.jsearch import fetch_jobs as fetch_jsearch_jobs

                raw_jobs = fetch_jsearch_jobs(slug, pages=company.get("pages", 1))
            elif ats_type == "adzuna":
                from src.adapters.adzuna import fetch_jobs as fetch_adzuna_jobs

                raw_jobs = fetch_adzuna_jobs(
                    slug,
                    country=company.get("country", "us"),
                    pages=company.get("pages", 1),
                    where=company.get("where"),
                    full_time=company.get("full_time"),
                )
            else:
                print(f"  [WARN] unknown ats_type '{ats_type}' — skipping", file=sys.stderr)
                continue

            result = apply_snapshot(conn, name, raw_jobs)
            results.append(result)
            print(
                f"  upserted {result.upserted}  |  "
                f"{len(result.newly_seen)} new  |  "
                f"{len(result.reopened)} reopened  |  "
                f"{result.newly_closed} closed"
            )

        except Exception as exc:
            print(f"  [ERROR] {exc}", file=sys.stderr)

    conn.close()

    if results:
        print()
        print(snapshot_summary(results))

    return results


if __name__ == "__main__":
    run_ingestion()
