import json
import hashlib
from datetime import datetime, timedelta
from google.cloud import firestore

from scrapers.greenhouse import fetch_greenhouse_jobs
from scrapers.lever import fetch_lever_jobs
from scrapers.workday import fetch_workday_jobs
from scrapers.ashby import fetch_ashby_jobs


# ================================
# FILTERS CONFIG (PHASE 2.1)
# ================================

TARGET_ROLES = [
    "software engineer",
    "swe",
    "ml engineer",
    "machine learning engineer",
    "ai engineer",
    "data scientist",
    "data engineer",
    "security engineer",
    "cybersecurity",
    "security analyst",
]

ENTRY_KEYWORDS = [
    "entry level",
    "new grad",
    "graduate",
    "junior",
    "early career",
    "associate",
    "assistant",
]

ENTRY_TITLE_MARKERS = [
    "engineer i",
    "engineer 1",
    "software engineer i",
    "software engineer 1",
    "data engineer i",
    "data engineer 1",
    "ml engineer i",
    "ml engineer 1",
    "security engineer i",
    "security engineer 1",
]

SENIOR_EXCLUDE = [
    "senior",
    "staff",
    "sr ",
    "principal",
    "lead",
    "manager",
    "director",
    "head of",
    "vp ",
]

LOCATION_KEYWORDS = [
    "us", "usa", "u.s.", "united states",
    "remote", "remote-us", "remote us",
    "anywhere in the us", "us only",
    "hybrid", "hybrid-us",
]


# ================================
# LOAD COMPANIES
# ================================
def load_companies():
    print("[INFO] Loading companies.json...")
    with open("config/companies.json") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} companies.")
    return data


# ================================
# TIMESTAMP NORMALIZATION
# ================================
def normalize_ts(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def posted_within_window(job, hours=24):
    """
    PHASE 2.1:
    Treat missing timestamps as fresh.
    Window = 24 hours for testing.
    """
    ts = normalize_ts(job.get("updated_at")) or normalize_ts(job.get("created_at"))
    if ts is None:
        return True  # assume new
    return datetime.utcnow() - ts < timedelta(hours=hours)


# ================================
# FILTERING LOGIC
# ================================
def job_matches(job):
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()
    text = f"{title} {desc}"
    loc = job.get("location", "").lower()

    # Debug reasons
    if not any(r in text for r in TARGET_ROLES):
        print(f"[FILTER] Reject (role): {job.get('title')}")
        return False

    if any(s in title for s in SENIOR_EXCLUDE):
        print(f"[FILTER] Reject (senior): {job.get('title')}")
        return False

    # Entry-level detection
    entry_match = (
        any(exp in text for exp in ENTRY_KEYWORDS) or
        any(marker in title for marker in ENTRY_TITLE_MARKERS)
    )
    if not entry_match:
        print(f"[FILTER] Reject (not entry-level): {job.get('title')}")
        return False

    # Location
    if not any(loc_kw in loc for loc_kw in LOCATION_KEYWORDS):
        print(f"[FILTER] Reject (location): {job.get('title')} | {loc}")
        return False

    # Freshness
    if not posted_within_window(job, hours=24):
        print(f"[FILTER] Reject (too old): {job.get('title')}")
        return False

    return True


# ================================
# UNIQUE JOB HASH
# ================================
def job_id(company, job):
    base = f"{company}|{job['title']}|{job['url']}"
    return hashlib.md5(base.encode()).hexdigest()


# ================================
# EMAIL SENDER
# ================================
def send_email(new_jobs):
    import smtplib
    from email.mime.text import MIMEText

    if not new_jobs:
        print("[INFO] No new jobs found — skipping email.")
        return

    print(f"[INFO] Sending email with {len(new_jobs)} jobs...")

    body = ""
    for j in new_jobs:
        body += f"{j['title']} — {j['company']}\n{j['url']}\n\n"

    msg = MIMEText(body)
    msg["Subject"] = f"{len(new_jobs)} New Jobs Found"
    msg["From"] = "somaharsha71@gmail.com"
    msg["To"] = "somaharsha71@gmail.com"

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login("somaharsha71@gmail.com", "xzrs dgan dgdh noke")
        server.send_message(msg)

    print("[INFO] Email sent successfully.")


# ================================
# MAIN
# ================================
def main(request=None):
    print("\n======== JOB ALERT AGENT STARTED ========\n")

    # Firestore handling
    try:
        db = firestore.Client()
    except Exception as e:
        print(f"[INFO] Firestore DISABLED — using dev mode. Reason: {e}")
        db = None

    companies = load_companies()
    seen = set()

    new_jobs = []

    for company in companies:
        name = company["name"]
        ats = company["ats"]
        url = company["careers_url"]

        print(f"\n[INFO] Fetching jobs for: {name} ({ats})")

        if ats == "greenhouse":
            jobs = fetch_greenhouse_jobs(name, url)
        elif ats == "lever":
            jobs = fetch_lever_jobs(name, url)
        elif ats == "workday":
            jobs = fetch_workday_jobs(name, url)
        elif ats == "ashby":
            jobs = fetch_ashby_jobs(name, url)
        else:
            print(f"[WARN] Unsupported ATS: {ats}")
            jobs = []

        print(f"[INFO] {name}: scraper returned {len(jobs)} raw jobs.")

        for job in jobs:
            if not job_matches(job):
                continue

            jid = job_id(name, job)
            if jid in seen:
                continue

            seen.add(jid)
            new_jobs.append({
                "company": name,
                "title": job["title"],
                "location": job["location"],
                "url": job["url"],
            })

        print(f"[INFO] {name}: {len(new_jobs)} total new jobs accumulated so far.")

    print(f"\n[INFO] FINAL: Found {len(new_jobs)} new jobs.")
    send_email(new_jobs)

    print("\n======== JOB ALERT AGENT FINISHED ========\n")
    return "OK"
