# job-tracker

Monitor job postings from specific companies over time, rank them against your
resume, and generate a digest of new and open roles.

**Does NOT auto-submit applications** — that step stays human.

---

## What it does

- Ingests jobs from configured sources (currently Adzuna, Greenhouse, Lever, JSearch)
- Stores history in SQLite with `first_seen`, `last_seen`, and open/closed state
- Scores open jobs against your resume using TF-IDF + cosine similarity
- Generates markdown digests and match reports
- Provides a local Streamlit dashboard to review jobs, matches, and reports

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         config.yaml                             │
│          (companies list: name, ATS type, board token)          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Ingestion Layer                             │
│                     src/ingest.py                               │
│                                                                 │
│   Adapters: Adzuna, Greenhouse, Lever, JSearch                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │  raw job JSON
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Storage / Diff Layer                           │
│               src/db.py  +  src/diff.py                         │
│                                                                 │
│  • Upserts jobs — never hard-deletes                            │
│  • Tracks first_seen / last_seen per job_id                     │
│  • Marks jobs closed when absent from feed                       │
│  • SQLite DB retains 6+ months of history                       │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
┌──────────────────────────┐   ┌──────────────────────────────────┐
│    Matching Layer        │   │         Output Layer             │
│    src/match.py          │   │         src/digest.py            │
│                          │   │                                  │
│  Score open postings     │   │  Markdown reports for digest +   │
│  against resume.txt      │   │  resume matches                  │
└──────────────────────────┘   └──────────────────────────────────┘
```

### Data flow in one sentence
`config.yaml` → adapters fetch ATS feeds → SQLite stores/diffs snapshots → matcher scores against resume → digest reports results.

---

## Config

`config.yaml` supports these fields for Adzuna entries:

- `name`: label used in outputs
- `ats_type`: `adzuna`
- `ats_slug`: search keywords (for example, `site reliability engineer google`)
- `country`: two-letter country code, default `us`
- `where`: optional location filter (for example, `California`)
- `full_time`: optional boolean full-time filter
- `pages`: number of pages to fetch (10 results per page)

Environment variables are loaded from `.env`:

- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`
- `JSEARCH_API_KEY` (only if you enable JSearch entries)

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Edit config.yaml to add your target companies
# Edit resume.txt to add your resume text

python -m src.ingest        # run ingestion once
pytest                       # run tests

# Run resume-vs-job scoring agent and write output/matches_YYYY-MM-DD.md
python -m src.agent --top 10

# Optional: set a minimum score filter
python -m src.agent --top 25 --min-score 0.03

# Run local dashboard UI
python -m pip install ".[ui]"
streamlit run src/ui.py
```

## UI workflow

The Streamlit dashboard includes:

- **Jobs** tab: filter by company, title, location, and open status
- **Matches** tab: ranked resume matches, score labels, and CSV export
- **Apply Queue** tab: top actionable roles with skill-hit and skill-miss badges
- **Reports** tab: latest generated digest and match markdown files

## Project structure

| Path | Purpose |
|------|---------|
| `config.yaml` | Companies to track (ATS type + board token) |
| `resume.txt` | Your resume (plain text, used by matcher) |
| `src/db.py` | SQLite schema + upsert helpers |
| `src/ingest.py` | Ingestion orchestrator |
| `src/adapters/` | One adapter per ATS (Greenhouse, Lever, …) |
| `src/match.py` | Resume scoring (TF-IDF + cosine similarity) |
| `src/agent.py` | CLI match agent, writes `output/matches_YYYY-MM-DD.md` |
| `src/ui.py` | Streamlit dashboard for jobs/matches/reports |
| `src/digest.py` | Markdown digest generation |
| `.github/workflows/` | GitHub Actions (daily cron) |

## Conventions

- Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- One branch per ticket: `ticket-NN/short-description`
- Run `pytest` before every commit

See [CLAUDE.md](CLAUDE.md) for full architecture and design decisions.
