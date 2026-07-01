"""Adzuna job search adapter.

Aggregates postings from LinkedIn, Indeed, and company career sites.
Docs: https://developer.adzuna.com/docs/search

Required env vars:
    ADZUNA_APP_ID   — your Adzuna App ID
    ADZUNA_APP_KEY  — your Adzuna App Key

Usage in config.yaml:
    - name: "Google SRE"
      ats_type: adzuna
      ats_slug: "site reliability engineer google"
      country: "us"      # optional, defaults to "us"
    where: "California" # optional location filter (city/state)
    full_time: true      # optional full-time only filter
    max_days_old: 15     # optional posted-in-last-N-days filter
      pages: 2           # optional, 10 results per page, defaults to 1
"""

import os
from typing import Optional

import requests

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"
REQUEST_TIMEOUT = 30
RESULTS_PER_PAGE = 10


def _credentials() -> tuple[str, str]:
    app_id = os.environ.get("ADZUNA_APP_ID", "")
    app_key = os.environ.get("ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        raise EnvironmentError(
            "ADZUNA_APP_ID and ADZUNA_APP_KEY must be set in your .env file."
        )
    return app_id, app_key


def fetch_jobs(
    query: str,
    country: str = "us",
    pages: int = 1,
    where: Optional[str] = None,
    full_time: Optional[bool] = None,
    max_days_old: Optional[int] = None,
) -> list[dict]:
    """Fetch jobs matching *query* from Adzuna and normalise to common shape.

    Args:
        query:   Search keywords, e.g. "site reliability engineer google".
        country: Two-letter country code (us, gb, au, ca, de, …).
        pages:   Number of result pages (10 results each).
        where:   Optional location filter, e.g. "California" or "San Francisco".
        full_time: Optional full-time filter. True sends full_time=1.
        max_days_old: Optional posted-in-last-N-days filter.
    """
    app_id, app_key = _credentials()

    jobs = []
    for page in range(1, pages + 1):
        url = f"{ADZUNA_BASE}/{country}/search/{page}"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": query,
            "results_per_page": RESULTS_PER_PAGE,
            "content-type": "application/json",
        }
        if where:
            params["where"] = where
        if full_time is True:
            params["full_time"] = 1
        if max_days_old is not None:
            params["max_days_old"] = int(max_days_old)
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            break

        for raw in results:
            jobs.append(_normalise(raw))

    return jobs


def _normalise(raw: dict) -> dict:
    """Map an Adzuna result to the common job shape used by db.upsert_job."""
    location = (
        raw.get("location", {}).get("display_name")
        or raw.get("location", {}).get("area", [""])[0]
    )

    return {
        "job_id":   str(raw.get("id", "")),
        "title":    raw.get("title", ""),
        "location": location,
        "url":      raw.get("redirect_url", ""),
        "raw_json": raw,
    }
