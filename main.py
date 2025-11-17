import json
import hashlib
from datetime import datetime, timezone
from google.cloud import firestore

from scrapers.greenhouse import fetch_greenhouse_jobs
from scrapers.lever import fetch_lever_jobs
from scrapers.workday import fetch_workday_jobs
from scrapers.ashby import fetch_ashby_jobs


# -------------------------------------------
# FILTER CONFIG
# -------------------------------------------
TARGET_ROLES = [
    "software engineer", "ml engineer", "machine learning engineer",
    "ai engineer", "data scientist", "data engineer",
    "security engineer", "cybersecurity", "security analyst",
    "associate software engineer", "associate ml engineer"
]

EXPERIENCE_KEYWORDS = [
    "entry level", "new grad", "graduate", "junior",
    "early career", "assistant", "associate"
]

LOCATION_KEYWORDS = [
    "us", "usa", "u.s.", "united states",
    "remote", "remote-us", "remote us",
    "anywhere in the us", "us only",
    "hybrid", "hybrid-us", "hybrid us"
]


# -------------------------------------------
# TIME FILTER (last 30 minutes)
# -------------------------------------------
def posted_within(job, minutes=30):
    timestamp = job.get("updated_at") or job.get("created_at")
    if not timestamp:
        return False

    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        return False

    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 60 <= minutes


# -------------------------------------------
# LOAD COMPANIES.JSON
# -------------------------------------------
def load_companies():
    print("[INFO] Loading companies.json...")
    with open("config/companies.json") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} companies.")
    return data


# -------------------------------------------
# JOB FILTER LOGIC
# -------------------------------------------
def job_matches(job):
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    text = title + " " + desc
    loc = (job.get("location") or "").lower()

    if not any(role in text for role in TARGET_ROLES):
        return False

    if not any(exp in text for exp in EXPERIENCE_KEYWORDS):
        return False

    if not any(loc_kw in loc for loc_kw in LOCATION_KEYWORDS):
        return False

    if not posted_within(job, minutes=30):
        return False

    # exclude internships
    if "intern" in text or "internship" in text:
        return False

    return True


# -------------------------------------------
# UNIQUE JOB HASH
# -------------------------------------------
def job_id(company, job):
    base = f"{company}|{job.get('title')}|{job.get('url')}"
    return hashlib.md5(base.encode()).hexdigest()


# -------------------------------------------
# EMAIL SENDER
# -------------------------------------------
def send_email(new_jobs):
    import smtplib
    from email.mime.text import MIMEText

    if not new_jobs:
        print("[INFO] No new jobs — skipping email.")
        return

    print(f"[INFO] Sending email with {len(new_jobs)} new jobs...")

    body = ""
    for j in new_jobs:
        body += f"{j['title']} — {j['company']}\n{j['url']}\n\n"

    msg = MIMEText(body)
    msg["Subject"] = f"{len(new_jobs)} New Jobs Found"
    msg["From"] = "somaharsha71@gmail.com"
    msg["To"] = "somaharsha71@gmail.com"

    with smtplplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login("somaharsha71@gmail.com", "xzrs dgan dgdh noke")
        server.send_message(msg)

    print("[INFO] Email sent successfully.")


# -------------------------------------------
# MAIN
# -------------------------------------------
def main(request=None):
    print("\n======== JOB ALERT AGENT STARTED ========\n")

    # Firestore disabled in GitHub Actions
    try:
        db = firestore.Client()
    except Exception as e:
        print(f"[INFO] Firestore DISABLED — running in dev mode. Reason: {e}")
        db = None

    companies = load_companies()
    seen = set()

    if db:
        seen = {doc.id for doc in db.collection("jobs_seen").stream()}
        print(f"[INFO] Loaded {len(seen)} previously seen job IDs.\n")
    else:
        print("[INFO] No Firestore — job dedupe disabled.\n")

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

        print(f"[INFO] {name}: scraper returned {len(jobs)} jobs.")

        for job in jobs:
            if not job_matches(job):
                continue

            jid = job_id(name, job)
            if jid in seen:
                continue

            record = {
                "company": name,
                "title": job["title"],
                "location": job["location"],
                "url": job["url"]
            }

            if db:
                db.collection("jobs_seen").document(jid).set(record)

            new_jobs.append(record)

        print(f"[INFO] {name}: {len(new_jobs)} total new jobs accumulated so far.")

    print(f"\n[INFO] FINAL: Found {len(new_jobs)} new jobs.")
    send_email(new_jobs)

    print("\n======== JOB ALERT AGENT FINISHED ========\n")
    return "OK"
