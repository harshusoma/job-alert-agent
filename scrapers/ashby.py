import requests
from datetime import datetime, timezone


def _extract_board_name(value: str) -> str:
    """
    If user passes an Ashby board URL, take last segment.
    If they pass 'openai' etc., just return it.
    """
    if not value:
        return ""
    if value.startswith("http"):
        parts = [p for p in value.strip().split("/") if p]
        return parts[-1]
    return value


def fetch_ashby_jobs(company: str, board_value: str):
    """
    board_value is either:
    - jobs.ashbyhq.com/<board_name>
    - OR just the <board_name> itself.
    """
    board_name = _extract_board_name(board_value)
    if not board_name:
        print(f"[ASHBY] No board_name for {company}, value={board_value}")
        return []

    api_url = f"https://jobs.ashbyhq.com/api/non-user-boards/{board_name}/jobs"

    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ERROR] Ashby API failed for {company}: {e}")
        return []

    jobs_raw = data.get("jobs", [])
    print(f"[ASHBY] API returned {len(jobs_raw)} jobs for {company}")

    jobs = []
    for j in jobs_raw:
        title = j.get("jobTitle", "")
        url = j.get("jobUrl") or ""
        location = j.get("locationName") or ""
        description = j.get("descriptionHtml") or j.get("descriptionPlain") or ""

        published_at = j.get("publishedAt")  # ISO string
        posted_at = published_at

        employment_type = (j.get("employmentType") or "").lower()

        jobs.append(
            {
                "title": title,
                "location": location,
                "description": description,
                "url": url,
                "employment_type": employment_type,
                "posted_at": posted_at,
            }
        )

    return jobs
