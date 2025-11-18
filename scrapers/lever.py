import requests
from datetime import datetime, timedelta, timezone

KEYWORDS_FLEXIBLE = [
    "software", "swe", "developer", "engineer", "backend", "full stack",
    "full-stack", "python", "java", "ml", "machine learning", "data",
    "security", "ai", "artificial intelligence", "research engineer",
    "applied scientist"
]

USA_KEYWORDS = ["united states", "usa", "us", "remote - us", "remote-us"]


def normalize(text: str):
    return text.lower().strip() if text else ""


def is_recent(created_at_iso: str, minutes=30):
    """Check if job was posted in last X minutes."""
    try:
        posted = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - posted <= timedelta(minutes=minutes)
    except:
        return False


def matches_flexible_keywords(title: str):
    title = normalize(title)
    return any(kw in title for kw in KEYWORDS_FLEXIBLE)


def is_usa(location: str):
    if not location:
        return False
    loc = normalize(location)
    return any(kw in loc for kw in USA_KEYWORDS)


def scrape(company_name, careers_url):
    """
    Example: https://jobs.lever.co/scaleai
    API:     https://api.lever.co/v0/postings/scaleai?mode=json
    """

    try:
        board = careers_url.rstrip("/").split("/")[-1]
        api_url = f"https://api.lever.co/v0/postings/{board}?mode=json"

        resp = requests.get(api_url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[LEVER] Error fetching {company_name}: {e}")
        return []

    results = []

    for job in data:
        title = job.get("text", "")
        location = job.get("categories", {}).get("location", "")
        created = job.get("createdAt")

        if not created:
            continue

        created_iso = datetime.utcfromtimestamp(created / 1000).isoformat() + "Z"

        # FILTERS
        if not is_recent(created_iso, minutes=30):
            continue

        if not matches_flexible_keywords(title):
            continue

        if not is_usa(location):
            continue

        results.append({
            "id": job.get("id"),
            "title": title,
            "company": company_name,
            "location": location,
            "url": job.get("hostedUrl"),
            "created_at": created_iso
        })

    print(f"[LEVER] {company_name}: {len(results)} filtered jobs")
    return results
