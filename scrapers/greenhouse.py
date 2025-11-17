import requests


def _extract_board_token(url: str) -> str:
    """
    For URLs like:
      - https://boards.greenhouse.io/databricks
      - https://boards.greenhouse.io/databricks/
    return "databricks".
    """
    return url.rstrip("/").split("/")[-1]


def fetch_greenhouse_jobs(company: str, careers_url: str):
    jobs = []
    board_token = _extract_board_token(careers_url)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"

    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        raw_jobs = data.get("jobs", [])
        print(f"[GREENHOUSE] API returned {len(raw_jobs)} jobs for {company}")

        for j in raw_jobs:
            jobs.append(
                {
                    "title": j.get("title", ""),
                    "company": company,
                    "location": j.get("location", {}).get("name", "") or "",
                    "url": j.get("absolute_url", "") or "",
                    "description": j.get("content", "") or "",
                    "created_at": j.get("created_at"),
                    "updated_at": j.get("updated_at"),
                }
            )

    except Exception as e:
        print(f"Error:  Greenhouse API failed for {company}: {e}")

    return jobs
