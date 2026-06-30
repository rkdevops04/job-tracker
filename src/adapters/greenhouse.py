"""Greenhouse ingestion adapter (TICKET-02).

Public API docs: https://developers.greenhouse.io/job-board.html
Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
"""

import requests

GREENHOUSE_BASE = "https://boards-api.greenhouse.io/v1/boards"
REQUEST_TIMEOUT = 30  # seconds


def fetch_jobs(board_token: str) -> list[dict]:
    """Fetch all open jobs from a Greenhouse board and normalise to a common shape."""
    url = f"{GREENHOUSE_BASE}/{board_token}/jobs"
    response = requests.get(url, params={"content": "true"}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for raw in data.get("jobs", []):
        location = None
        if raw.get("offices"):
            location = raw["offices"][0].get("name")
        elif raw.get("location", {}).get("name"):
            location = raw["location"]["name"]

        jobs.append({
            "job_id":   str(raw["id"]),
            "title":    raw.get("title", ""),
            "location": location,
            "url":      raw.get("absolute_url", ""),
            "raw_json": raw,
        })
    return jobs
