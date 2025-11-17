import requests
from datetime import datetime, timezone


def _extract_board_token(careers_url: str) -> str:
    """
    careers_url example: https://boards.greenhouse.io/databricks
    We take the last non-empty segment as board token.
    """
    if not careers_url:
        return ""
    parts = [p for p in careers_url.strip().split("/") if p]
    return parts[-1]


def fetch_greenhouse_jobs(company: str, careers_url: str):
    board_token = _extract_board_token(careers_url)
    if not board_token:
        print(f"[GREENHOUSE] No board token for {company}, url={careers_url}")
        return []

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"

    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ERROR] Greenhouse API failed for {company}: {e}")
        return []

    jobs_raw = data.get("jobs", [])
    print(f"[GREENHOUSE] API returned {len(jobs_raw)} jobs for {company}")

    jobs = []
    for j in jobs_raw:
        title = j.get("title", "")
        url = j.get("absolute_url") or ""
        loc_obj = j.get("location") or {}
        location = loc_obj.get("name", "")

        # Greenhouse has 'updated_at' / 'created_at' as ISO strings
        posted_at = j.get("updated_at") or j.get("created_at")

        jobs.append(
            {
                "title": title,
                "location": location,
                "description": j.get("content", "") or "",
                "url": url,
                "employment_type": "",  # not always available
                "posted_at": posted_at,
            }
        )

    return jobs
