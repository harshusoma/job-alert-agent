import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def fetch_workday_jobs(company: str, careers_url: str):
    """
    Best-effort HTML scraper for Workday / custom career pages.

    Returns a list of dicts:
      {
        "title": str,
        "location": str,
        "url": str,
        "description": str,
        "posted_at": None  # we don't reliably get timestamps yet
      }
    """
    print(f"[INFO] Workday scraper starting for {company}: {careers_url}")

    jobs = []

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }
        resp = requests.get(careers_url, headers=headers, timeout=25)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Workday request failed for {company}: {e}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")

    # Strategy 1: Common Workday markup with data-automation-id="jobTitle"
    title_links = soup.find_all("a", attrs={"data-automation-id": "jobTitle"})
    if not title_links:
        # Some tenants use slightly different IDs
        alt_ids = ["jobPostingTitle", "jobTitle-link"]
        for alt in alt_ids:
            title_links = soup.find_all("a", attrs={"data-automation-id": alt})
            if title_links:
                break

    # Strategy 2: Heuristic fallback — links whose href looks like a job posting
    if not title_links:
        possible = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if not text:
                continue
            # Very loose heuristic: Workday job URLs often contain "/wd" or "job"
            if "job" in href.lower() or "wd" in href.lower():
                possible.append(a)
        title_links = possible

    print(f"[WORKDAY] Found {len(title_links)} potential job links for {company}")

    for a in title_links:
        title = a.get_text(strip=True)
        if not title:
            continue

        href = a.get("href", "").strip()
        if not href:
            continue

        url = urljoin(careers_url, href)

        # Try to find a nearby location element
        location = ""
        try:
            parent = a
            for _ in range(4):  # walk up a few levels max
                if not parent:
                    break

                loc_tag = (
                    parent.find(attrs={"data-automation-id": "jobLocation"})
                    or parent.find(attrs={"data-automation-id": "secondaryLocation"})
                    or parent.find(attrs={"data-automation-id": "locations"})
                )

                if loc_tag:
                    location = loc_tag.get_text(strip=True)
                    break

                parent = parent.parent
        except Exception:
            pass

        job = {
            "title": title,
            "location": location or "",
            "url": url,
            "description": "",
            "posted_at": None
        }
        jobs.append(job)

    print(f"[WORKDAY] Parsed {len(jobs)} job entries for {company}")
    return jobs
