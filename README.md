# job-tracker

Monitor job postings from specific companies over time, rank them against your
resume, and generate a digest of new and open roles.

**Does NOT auto-submit applications** — that step stays human.

---

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
│   ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│   │  Greenhouse     │  │     Lever        │  │    Ashby      │  │
│   │  adapter        │  │     adapter      │  │    adapter    │  │
│   │  (TICKET-02) ✅ │  │  (TICKET-03) 🔲 │  │  (future)  🔲 │  │
│   └────────┬────────┘  └────────┬─────────┘  └──────┬────────┘  │
│            └───────────────────┬┘                   │           │
│                                └────────────────────┘           │
└────────────────────────────────┬────────────────────────────────┘
                                 │  raw job JSON
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Storage / Diff Layer                           │
│               src/db.py  +  src/diff.py                         │
│                                                                 │
│  • Upserts jobs — never hard-deletes (TICKET-01) ✅             │
│  • Tracks first_seen / last_seen per job_id                     │
│  • Marks jobs closed when absent from feed (TICKET-04) 🔲       │
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
│  Score open postings     │   │  Markdown report of new +        │
│  against resume.txt      │   │  still-open postings,            │
│  (TICKET-06) 🔲          │   │  grouped by company              │
│                          │   │  (TICKET-07) 🔲                  │
└──────────────────────────┘   └──────────────────────────────────┘
```

### Data flow in one sentence
`config.yaml` → adapters fetch ATS feeds → SQLite stores/diffs snapshots → matcher scores against resume → digest reports results.

---

## Roadmap

| Ticket | Description | Branch | Status |
|--------|-------------|--------|--------|
| TICKET-01 | DB schema (`jobs` + `companies` tables, upsert, close) | `ticket-01/db-schema` | ✅ Done |
| TICKET-02 | Greenhouse ingestion adapter | `ticket-02/greenhouse-adapter` | ✅ Done |
| TICKET-03 | Lever ingestion adapter | `ticket-03/lever-adapter` | 🔲 Next |
| TICKET-04 | Diff/snapshot logic (mark closed, never delete) | `ticket-04/diff-snapshot` | 🔲 Queued |
| TICKET-05 | GitHub Actions daily cron + artifact upload | `ticket-05/github-actions` | 🔲 Queued |
| TICKET-06 | Resume matching (keyword/semantic scoring) | `ticket-06/resume-matching` | 🔲 Queued |
| TICKET-07 | Digest output (markdown report by company) | `ticket-07/digest-output` | 🔲 Queued |

Full ticket details in [PLAN.md](PLAN.md).

---

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
| `src/match.py` | Resume scoring (TICKET-06) |
| `src/digest.py` | Markdown/CSV report generation (TICKET-07) |
| `.github/workflows/` | GitHub Actions (daily cron) |

## Conventions

- Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- One branch per ticket: `ticket-NN/short-description`
- Run `pytest` before every commit

See [CLAUDE.md](CLAUDE.md) for full architecture and design decisions.
