# job-tracker

Monitor job postings from specific companies over time, rank them against your
resume, and generate a digest of new and open roles.

**Does NOT auto-submit applications** — that step stays human.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Edit config.yaml to add your target companies
# Edit resume.txt to add your resume text

python -m src.ingest        # run ingestion once
pytest                       # run tests
```

## Project structure

| Path | Purpose |
|------|---------|
| `config.yaml` | Companies to track (ATS type + board token) |
| `resume.txt` | Your resume (plain text, used by matcher) |
| `src/db.py` | SQLite schema + upsert helpers |
| `src/ingest.py` | Ingestion orchestrator |
| `src/adapters/` | One adapter per ATS (Greenhouse, Lever, …) |
| `.github/workflows/` | GitHub Actions (daily cron) |

## Tickets / roadmap

See [PLAN.md](PLAN.md) for the full ticket breakdown.

## Architecture

See [CLAUDE.md](CLAUDE.md) for design decisions and conventions.
