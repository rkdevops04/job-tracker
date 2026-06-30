# PLAN.md — job-tracker ticket breakdown

Each ticket maps to exactly one git branch / worktree.
Branch naming: `ticket-NN/short-description`

---

## TICKET-01 · DB Schema
**Branch:** `ticket-01/db-schema`

Create the SQLite schema and Python helpers.

Tables:
- `companies(id, name, ats_type, ats_slug)`
- `jobs(job_id, company, title, location, url, first_seen, last_seen, is_open, raw_json)`

Deliverables:
- `src/db.py` — `init_db()`, `upsert_job()`, `mark_closed()`
- Migration is run-once on startup (no Alembic needed at this scale)

**Status:** ✅ done (part of `setup/initial-skeleton`)

---

## TICKET-02 · Greenhouse Ingestion Adapter
**Branch:** `ticket-02/greenhouse-adapter`

Fetch `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` and
upsert results into the DB.

Deliverables:
- `src/adapters/greenhouse.py` — `fetch_jobs(board_token) -> list[dict]`
- `src/ingest.py` — orchestrator that reads `config.yaml` and calls adapters
- `tests/test_greenhouse.py` — mocked HTTP + upsert test

**Status:** ✅ done (part of `setup/initial-skeleton`)

---

## TICKET-03 · Lever Ingestion Adapter
**Branch:** `ticket-03/lever-adapter`

Same pattern as TICKET-02 but for Lever's public postings endpoint:
`GET https://api.lever.co/v0/postings/{site}?mode=json`

Deliverables:
- `src/adapters/lever.py`
- Tests

**Status:** 🔲 not started

---

## TICKET-04 · Diff / Snapshot Logic
**Branch:** `ticket-04/diff-snapshot`

After each ingestion run, compare the fresh job list against the DB and:
- Set `is_open = 0` / update `last_seen` for jobs no longer in the feed
- Never delete rows

Deliverables:
- `src/diff.py` — `apply_diff(company, fetched_ids, db_conn)`
- Tests covering close detection

**Status:** 🔲 not started

---

## TICKET-05 · GitHub Actions Scheduling
**Branch:** `ticket-05/github-actions`

Daily cron workflow that:
1. Checks out the repo
2. Installs dependencies
3. Runs `python -m src.ingest`
4. Commits the updated `.db` file **or** uploads it as a workflow artifact

Deliverables:
- `.github/workflows/ingest.yml`

**Status:** 🔲 not started (skeleton workflow created in `setup/initial-skeleton`)

---

## TICKET-06 · Resume Matching
**Branch:** `ticket-06/resume-matching`

Score open postings against `resume.txt` using keyword overlap (TF-IDF or
simple token intersection). Semantic scoring (embeddings) is a stretch goal.

Deliverables:
- `src/match.py` — `score_jobs(resume_path, db_conn) -> list[(job_id, score)]`
- Tests with fixture resume + job descriptions

**Status:** 🔲 not started

---

## TICKET-07 · Digest Output
**Branch:** `ticket-07/digest-output`

Generate a markdown report after each ingestion run:
- New postings since the previous run (grouped by company)
- Still-open postings older than N days
- Optional CSV export

Deliverables:
- `src/digest.py` — `generate_markdown(db_conn, since) -> str`
- Output written to `output/digest_YYYY-MM-DD.md`

**Status:** 🔲 not started

---

## Open questions / future work

- Ashby adapter (TICKET-08, not yet scoped)
- Semantic matching via embeddings (stretch goal for TICKET-06)
- Notification on new matches (email / Slack webhook)
- De-duplication across ATS platforms (same role listed on multiple boards)
