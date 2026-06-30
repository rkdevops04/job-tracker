"""Lever ingestion adapter (TICKET-03).

Public API docs: https://hire.lever.co/developer/postings
Endpoint: GET https://api.lever.co/v0/postings/{site}?mode=json
"""

import requests

LEVER_BASE = "https://api.lever.co/v0/postings"
REQUEST_TIMEOUT = 30


def fetch_jobs(site: str) -> list[dict]:
    """Fetch all open postings from a Lever board and normalise to common shape."""
    url = f"{LEVER_BASE}/{site}"
    response = requests.get(url, params={"mode": "json"}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for raw in data:
        location = None
        categories = raw.get("categories", {})
        if categories.get("location"):
            location = categories["location"]
        elif raw.get("workplaceType"):
            location = raw["workplaceType"].capitalize()

        jobs.append({
            "job_id":   raw.get("id", ""),
            "title":    raw.get("text", ""),
            "location": location,
            "url":      raw.get("hostedUrl", ""),
            "raw_json": raw,
        })
    return jobs
