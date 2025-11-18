# scrapers/workday.py

import json
import re
from datetime import datetime, timezone, timedelta

import requests

# How recent a posting must be to be considered "fresh"
RECENT_MINUTES = 30

# Simple User-Agent to avoid some basic bot blocks
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobAlertBot/1.0; +https://github.com/harshusoma/job-alert-agent)"
}


def _is_recent(posted_at: datetime | None) -> bool:
    """Return True if posted_at is within RECENT_MINUTES from now."""
    if not isinstance(posted_at, datetime):
        return False
    now = datetime.now(timezone.utc)
    return (now - posted_at) <= timedelta(minutes=RECENT_MINUTES)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Best-effort parser for Workday-like ISO strings."""
    if not value or not isinstance(value, str):
        return None

    # Normalize "2025-11-17T12:34:56Z" → "2025-11-17T12:34:56+00:00"
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(v)
    except Exception:
        # Sometimes Workday only gives date "2025-11-17"
        try:
            return datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def _build_workday_api_url(careers_url: str) -> str | None:
    """
    Try to convert a Workday careers URL like:
      https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite
    into the JSON API endpoint:
      https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/fs/searchPagination/0/50
    """
    if "myworkdayjobs.com" not in careers_url:
        # Not a real Workday host – we skip API scraping for now.
        return None

    # Strip query params and trailing slashes
    base = careers_url.split("?", 1)[0].rstrip("/")

    # Append standard Workday searchPagination path
    return f"{base}/fs/searchPagination/0/50"


def _workday_search(company: str, careers_url: str) -> list[dict]:
    """
    Hit the Workday JSON searchPagination API if possible and return raw postings.
    This does NOT filter by role/level/location; that is done in main.job_matches().
    """
    api_url = _build_workday_api_url(careers_url)
    if not api_url:
        print(f"[WORKDAY] {company}: careers_url is not a Workday tenant, skipping API. url={careers_url}")
        return []

    print(f"[WORKDAY] {company}: calling JSON API: {api_url}")

    # Standard Workday search payload – we do a broad search
    payload = {
        "appliedFacets": {},
        "limit": 50,
        "offset": 0,
        "searchText": ""  # empty = all jobs
    }

    try:
        resp = requests.post(api_url, headers=HEADERS, json=payload, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error:  Workday API failed for {company}: {e}")
        return []

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print(f"Error:  Workday API for {company} did not return valid JSON.")
        return []

    postings = data.get("jobPostings") or data.get("jobPostingsSearchResult", {}).get("jobPostings") or []
    print(f"[WORKDAY] {company}: API returned {len(postings)} postings (before parsing).")

    jobs: list[dict] = []

    for p in postings:
        title = p.get("title") or p.get("titlePlainText") or ""
        if not title:
            continue

        # Location – Workday often uses locationsText or a list
        location = ""
        if isinstance(p.get("locationsText"), str):
            location = p["locationsText"]
        elif isinstance(p.get("locations"), list) and p["locations"]:
            location = ", ".join(str(x) for x in p["locations"])

        # URL – usually something like 'externalPath' or 'externalUrl'
        path = (
            p.get("externalPath")
            or p.get("externalUrl")
            or p.get("jobPostingExternalUrl")
            or ""
        )
        url = ""
        if path:
            if path.startswith("http"):
                url = path
            else:
                # Build full URL from careers_url base
                base = careers_url.split("?", 1)[0].rstrip("/")
                if not path.startswith("/"):
                    path = "/" + path
                url = base + path

        # Posted date – Workday varies by tenant
        posted_raw = (
            p.get("postedOn")
            or p.get("postedDate")
            or p.get("startDate")
            or p.get("postedOnDate")
        )
        posted_at = None
        if isinstance(posted_raw, str):
            posted_at = _parse_iso_datetime(posted_raw)
        elif isinstance(posted_raw, dict):
            # Sometimes { "value": "2025-11-17T..." } or { "date": "2025-11-17" }
            posted_at = _parse_iso_datetime(
                posted_raw.get("value")
                or posted_raw.get("date")
                or posted_raw.get("iso8601")
            )

        # We only keep "recent" postings; older ones will be ignored.
        if not _is_recent(posted_at):
            continue

        jobs.append(
            {
                "company": company,
                "title": title,
                "location": location,
                "url": url or careers_url,
                "description": "",          # main.py does keyword filtering; empty is OK
                "posted_at": posted_at,     # datetime or None
            }
        )

    print(f"[WORKDAY] {company}: returning {len(jobs)} recent jobs after time filter.")
    return jobs


def fetch_workday_jobs(company: str, careers_url: str) -> list[dict]:
    """
    Public entry used by main.py.
    Tries Workday JSON API; if not applicable, returns [] safely.
    """
    print(f"[INFO] Workday scraper starting for {company}: {careers_url}")

    jobs = _workday_search(company, careers_url)

    print(f"[INFO] {company}: scraper returned {len(jobs)} raw jobs.")
    return jobs
