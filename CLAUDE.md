# CLAUDE.md — job-tracker

## Purpose

Monitor job postings from specific companies over time, rank postings against a
resume for fit, and assist in drafting tailored application materials.

**This tool does NOT auto-submit applications.** Submitting is always a manual,
human step.

Key behaviours:
- Retain 6+ months of posting history (nothing is hard-deleted).
- Track first_seen / last_seen per job_id so closed postings are visible historically.
- Score open postings against a resume and surface the best matches.
- Emit a markdown/CSV digest of new and still-open postings after each run.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Storage | SQLite (single `.db` file, committed or artifact) |
| Scheduling | GitHub Actions (daily cron) |
| Config | `config.yaml` — list of companies with ATS type + board token |

## Architecture

```
config.yaml
    │
    ▼
Ingestion layer        polls ATS JSON feeds (Greenhouse / Lever / Ashby)
    │                  writes raw JSON snapshots per run
    ▼
Storage / diff layer   upserts into SQLite; marks jobs closed when they
    │                  disappear from a feed; never hard-deletes rows
    ▼
Matching layer         scores a posting against a resume (keyword / semantic)
    │
    ▼
Output layer           markdown report grouped by company; CSV digest
```

### ATS adapters (one module per ATS)
- `src/adapters/greenhouse.py` — `GET /v1/boards/{board_token}/jobs`
- `src/adapters/lever.py` — Lever public postings API
- `src/adapters/ashby.py` — Ashby job board API

## Conventions

- **Commits**: Conventional Commits — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- **Branches**: one branch per ticket (`ticket-01/db-schema`, `ticket-02/greenhouse-adapter`, …)
- **Tests**: run the full test suite (`pytest`) before every commit; CI enforces this
- **Secrets**: ATS tokens / API keys go in `.env` (gitignored); never hardcode

## File Layout

```
job-tracker/
├── .github/workflows/   GitHub Actions
├── src/
│   ├── db.py            schema + upsert helpers
│   ├── ingest.py        orchestrator — loads config, runs adapters
│   ├── diff.py          snapshot / close detection logic
│   ├── match.py         resume scoring
│   ├── digest.py        markdown / CSV report generation
│   └── adapters/
│       ├── greenhouse.py
│       ├── lever.py
│       └── ashby.py
├── tests/
├── config.yaml          companies list (no secrets here)
├── resume.txt           placeholder — replace with your actual resume
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── PLAN.md
└── CLAUDE.md            ← this file
```
