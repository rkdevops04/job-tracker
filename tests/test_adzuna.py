"""Tests for the Adzuna adapter."""

import pytest
import responses as rsps_lib

from src.adapters.adzuna import ADZUNA_BASE, fetch_jobs

FAKE_RESPONSE = {
    "results": [
        {
            "id": "9001",
            "title": "Site Reliability Engineer",
            "location": {"display_name": "San Francisco, CA", "area": ["US", "California"]},
            "redirect_url": "https://www.adzuna.com/details/9001",
            "company": {"display_name": "Google"},
            "description": "Join Google SRE...",
        },
        {
            "id": "9002",
            "title": "Senior SRE",
            "location": {"display_name": "New York, NY", "area": ["US", "New York"]},
            "redirect_url": "https://www.adzuna.com/details/9002",
            "company": {"display_name": "Google"},
            "description": "Senior SRE role...",
        },
    ]
}


@pytest.fixture(autouse=True)
def set_credentials(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "test-app-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-app-key")


@rsps_lib.activate
def test_fetch_jobs_returns_normalised_list():
    rsps_lib.add(rsps_lib.GET, f"{ADZUNA_BASE}/us/search/1", json=FAKE_RESPONSE, status=200)
    jobs = fetch_jobs("site reliability engineer google")

    assert len(jobs) == 2
    assert jobs[0]["job_id"] == "9001"
    assert jobs[0]["title"] == "Site Reliability Engineer"
    assert jobs[0]["location"] == "San Francisco, CA"
    assert "adzuna.com" in jobs[0]["url"]


@rsps_lib.activate
def test_fetch_jobs_empty_results():
    rsps_lib.add(rsps_lib.GET, f"{ADZUNA_BASE}/us/search/1", json={"results": []}, status=200)
    assert fetch_jobs("nonexistent role xyz") == []


@rsps_lib.activate
def test_fetch_jobs_http_error_raises():
    rsps_lib.add(rsps_lib.GET, f"{ADZUNA_BASE}/us/search/1", status=401)
    with pytest.raises(Exception):
        fetch_jobs("SRE at Google")


@rsps_lib.activate
def test_fetch_jobs_multiple_pages_stops_on_empty():
    rsps_lib.add(rsps_lib.GET, f"{ADZUNA_BASE}/us/search/1", json=FAKE_RESPONSE, status=200)
    rsps_lib.add(rsps_lib.GET, f"{ADZUNA_BASE}/us/search/2", json={"results": []}, status=200)
    jobs = fetch_jobs("SRE", pages=3)
    assert len(jobs) == 2


@rsps_lib.activate
def test_fetch_jobs_custom_country():
    rsps_lib.add(rsps_lib.GET, f"{ADZUNA_BASE}/gb/search/1", json=FAKE_RESPONSE, status=200)
    jobs = fetch_jobs("SRE", country="gb")
    assert len(jobs) == 2


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="ADZUNA_APP_ID"):
        fetch_jobs("SRE")


@rsps_lib.activate
def test_location_fallback_to_area():
    raw_result = {**FAKE_RESPONSE["results"][0], "location": {"display_name": None, "area": ["US", "Remote"]}}
    rsps_lib.add(rsps_lib.GET, f"{ADZUNA_BASE}/us/search/1", json={"results": [raw_result]}, status=200)
    jobs = fetch_jobs("SRE")
    assert jobs[0]["location"] == "US"
