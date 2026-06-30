"""JSearch (RapidAPI) ingestion adapter.

Searches LinkedIn, Indeed, Glassdoor, and Google Jobs via a single API.
Docs: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

Required env var: JSEARCH_API_KEY  (your RapidAPI key)

Usage in config.yaml:
  - name: "Google"
    ats_type: jsearch
    ats_slug: "Site Reliability Engineer at Google"
"""

import os

import requests

JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_BASE = f"https://{JSEARCH_HOST}/search"
REQUEST_TIMEOUT = 30


def _api_key() -> str:
    key = os.environ.get("JSEARCH_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "JSEARCH_API_KEY is not set. Add it to your .env file."
        )
    return key


def fetch_jobs(query: str, pages: int = 1) -> list[dict]:
    """Fetch jobs matching *query* from JSearch and normalise to common shape.

    Args:
        query:  Free-text search string, e.g. "Site Reliability Engineer at Google".
                Maps to ats_slug in config.yaml.
        pages:  Number of result pages to fetch (10 results per page).
    """
    headers = {
        "x-rapidapi-host": JSEARCH_HOST,
        "x-rapidapi-key": _api_key(),
    }

    jobs = []
    for page in range(1, pages + 1):
        params = {
            "query": query,
            "page": str(page),
            "num_pages": "1",
            "date_posted": "all",
            "employment_types": "FULLTIME",
        }
        response = requests.get(
            JSEARCH_BASE, headers=headers, params=params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()

        for raw in data.get("data", []):
            jobs.append(_normalise(raw))

        # Stop early if there are no more results
        if not data.get("data"):
            break

    return jobs


def _normalise(raw: dict) -> dict:
    """Map a JSearch result to the common job shape used by db.upsert_job."""
    location_parts = filter(None, [
        raw.get("job_city"),
        raw.get("job_state"),
        raw.get("job_country"),
    ])
    location = ", ".join(location_parts) or raw.get("job_location", None)

    return {
        "job_id":   raw.get("job_id", ""),
        "title":    raw.get("job_title", ""),
        "location": location,
        "url":      raw.get("job_apply_link") or raw.get("job_google_link", ""),
        "raw_json": raw,
        # Extra fields stored in raw_json but useful for digest/matching
        # "employer":    raw.get("employer_name"),
        # "source":      raw.get("job_publisher"),
        # "description": raw.get("job_description"),
    }
