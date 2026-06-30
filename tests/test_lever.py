"""Tests for Lever adapter (TICKET-03)."""

import pytest
import responses as rsps_lib

from src.adapters.lever import LEVER_BASE, fetch_jobs

FAKE_RESPONSE = [
    {
        "id": "lever-001",
        "text": "Site Reliability Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/lever-001",
        "categories": {"location": "San Francisco, CA", "team": "Engineering"},
        "workplaceType": "remote",
    },
    {
        "id": "lever-002",
        "text": "DevOps Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/lever-002",
        "categories": {"team": "Infrastructure"},
        "workplaceType": "hybrid",
    },
]


@rsps_lib.activate
def test_fetch_jobs_returns_normalised_list():
    rsps_lib.add(rsps_lib.GET, f"{LEVER_BASE}/acme", json=FAKE_RESPONSE, status=200)
    jobs = fetch_jobs("acme")

    assert len(jobs) == 2
    assert jobs[0]["job_id"] == "lever-001"
    assert jobs[0]["title"] == "Site Reliability Engineer"
    assert jobs[0]["location"] == "San Francisco, CA"
    assert "lever.co" in jobs[0]["url"]


@rsps_lib.activate
def test_fetch_jobs_falls_back_to_workplace_type():
    rsps_lib.add(rsps_lib.GET, f"{LEVER_BASE}/acme", json=FAKE_RESPONSE, status=200)
    jobs = fetch_jobs("acme")
    assert jobs[1]["location"] == "Hybrid"


@rsps_lib.activate
def test_fetch_jobs_empty_board():
    rsps_lib.add(rsps_lib.GET, f"{LEVER_BASE}/empty", json=[], status=200)
    assert fetch_jobs("empty") == []


@rsps_lib.activate
def test_fetch_jobs_http_error_raises():
    rsps_lib.add(rsps_lib.GET, f"{LEVER_BASE}/bad", status=404)
    with pytest.raises(Exception):
        fetch_jobs("bad")
