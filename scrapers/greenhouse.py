# scrapers/greenhouse.py

import requests


def _extract_board_token(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def fetch_greenhouse_jobs(company: str, careers_url: str):
    jobs = []
    board_token = _extract_board_token(careers_url)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"

    try:
        resp = requests.get(api_url, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        raw = data.get("jobs", [])
        print(f"[GREENHOUSE] API returned {len(raw)} jobs for {company}")

        for j in raw:
            jobs.append(
                {
                    "title": j.get("title") or "",
                    "company": company,
                    "location": (j.get("location") or {}).get("name", "") or "",
                    "url": j.get("absolute_url") or "",
                    "description": j.get("content") or "",
                    "created_at": j.get("created_at"),
                    "updated_at": j.get("updated_at"),
                }
            )

    except Exception as e:
        print(f"Error:  Greenhouse API failed for {company}: {e}")

    return jobs
