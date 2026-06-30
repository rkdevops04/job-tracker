"""Tests for the JSearch adapter."""

import os

import pytest
import responses as rsps_lib

from src.adapters.jsearch import JSEARCH_BASE, fetch_jobs

FAKE_RESPONSE = {
    "data": [
        {
            "job_id": "abc123",
            "job_title": "Site Reliability Engineer",
            "employer_name": "Google",
            "job_city": "Mountain View",
            "job_state": "CA",
            "job_country": "US",
            "job_apply_link": "https://careers.google.com/jobs/abc123",
            "job_description": "Join the SRE team...",
            "job_publisher": "LinkedIn",
        },
        {
            "job_id": "def456",
            "job_title": "Senior SRE",
            "employer_name": "Google",
            "job_city": "New York",
            "job_state": "NY",
            "job_country": "US",
            "job_apply_link": "https://careers.google.com/jobs/def456",
            "job_description": "Senior SRE role...",
            "job_publisher": "Indeed",
        },
    ]
}


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key-123")


@rsps_lib.activate
def test_fetch_jobs_returns_normalised_list():
    rsps_lib.add(rsps_lib.GET, JSEARCH_BASE, json=FAKE_RESPONSE, status=200)
    jobs = fetch_jobs("Site Reliability Engineer at Google")

    assert len(jobs) == 2
    assert jobs[0]["job_id"] == "abc123"
    assert jobs[0]["title"] == "Site Reliability Engineer"
    assert jobs[0]["location"] == "Mountain View, CA, US"
    assert "careers.google.com" in jobs[0]["url"]


@rsps_lib.activate
def test_fetch_jobs_empty_results():
    rsps_lib.add(rsps_lib.GET, JSEARCH_BASE, json={"data": []}, status=200)
    assert fetch_jobs("nonexistent role xyz") == []


@rsps_lib.activate
def test_fetch_jobs_http_error_raises():
    rsps_lib.add(rsps_lib.GET, JSEARCH_BASE, status=429)
    with pytest.raises(Exception):
        fetch_jobs("SRE at Google")


@rsps_lib.activate
def test_fetch_jobs_multiple_pages():
    rsps_lib.add(rsps_lib.GET, JSEARCH_BASE, json=FAKE_RESPONSE, status=200)
    rsps_lib.add(rsps_lib.GET, JSEARCH_BASE, json={"data": []}, status=200)
    jobs = fetch_jobs("SRE at Google", pages=2)
    # Second page is empty so stops early — only first page results
    assert len(jobs) == 2


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="JSEARCH_API_KEY"):
        fetch_jobs("SRE at Google")


@rsps_lib.activate
def test_location_fallback_when_no_city():
    raw = {**FAKE_RESPONSE["data"][0], "job_city": None, "job_state": None, "job_country": None, "job_location": "Remote"}
    rsps_lib.add(rsps_lib.GET, JSEARCH_BASE, json={"data": [raw]}, status=200)
    jobs = fetch_jobs("SRE")
    assert jobs[0]["location"] == "Remote"
