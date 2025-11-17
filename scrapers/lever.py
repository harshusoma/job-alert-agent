import requests
from datetime import datetime, timezone


def fetch_lever_jobs(company: str, careers_url: str):
    """
    careers_url can be:
    - a full Lever API URL
      e.g. https://api.lever.co/v0/postings/rippling?mode=json
    - OR just the Lever account slug, e.g. "rippling"
    """
    if careers_url.startswith("http"):
        api_url = careers_url
        if "mode=" not in api_url:
            # ensure JSON mode
            sep = "&" if "?" in api_url else "?"
            api_url = f"{api_url}{sep}mode=json"
    else:
        # assume account slug
        api_url = f"https://api.lever.co/v0/postings/{careers_url}?mode=json"

    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        jobs_raw = resp.json()
    except Exception as e:
        print(f"[ERROR] Lever API failed for {company}: {e}")
        return []

    print(f"[LEVER] API returned {len(jobs_raw)} jobs for {company}")

    jobs = []
    for j in jobs_raw:
        title = j.get("text", {}).get("title", "") or j.get("title", "")
        location = j.get("categories", {}).get("location", "") or ""
        description = j.get("descriptionPlain", "") or j.get("description", "") or ""
        url = j.get("hostedUrl") or j.get("applyUrl") or ""

        # createdAt in ms since epoch
        created_ms = j.get("createdAt")
        posted_at = None
        if isinstance(created_ms, (int, float)):
            posted_at = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc)

        employment_type = (j.get("categories", {}).get("commitment") or "").lower()
        # e.g. "intern", "full-time", etc.

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
