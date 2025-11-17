import os
import json
import hashlib
from datetime import datetime, timezone

from google.cloud import firestore

from scrapers.greenhouse import fetch_greenhouse_jobs
from scrapers.lever import fetch_lever_jobs
from scrapers.workday import fetch_workday_jobs


# -------------------------------
# FILTERING CONFIG
# -------------------------------
TARGET_ROLES = [
    "software engineer",
    "software developer",
    "ml engineer",
    "machine learning engineer",
    "ai engineer",
    "data scientist",
    "data engineer",
    "security engineer",
    "cybersecurity",
    "security analyst",
]

# Junior / early-career signals
EXPERIENCE_KEYWORDS = [
    "entry level",
    "new grad",
    "graduate",
    "junior",
    "early career",
    "associate",
    "assistant",
]

# Titles / descriptions we want to EXCLUDE
EXCLUDE_KEYWORDS = [
    "senior", " sr ", " sr.", "sr-",
    "staff",
    "principal",
    "lead",
    "director",
    "vp ", "vice president",
    "architect",
    "manager",
    "head of",
    "intern", "internship", "co-op", "co op",
    "fellowship",
]

# Location INCLUDE and EXCLUDE lists
LOCATION_INCLUDE = [
    " us", " usa", " u.s.", " united states",
    "(us)", "(usa)",
    "remote us", "remote-us", "remote in the us", "remote in usa",
    "anywhere in the us", "us only",
    "hybrid", "hybrid-us", "hybrid us",
    "onsite", "on-site", "in office", "in-office",
]

LOCATION_EXCLUDE = [
    "canada", "toronto", "vancouver",
    "europe", " eu ", "emea",
    "united kingdom", "uk", "london",
    "india", "bangalore", "bengaluru", "hyderabad", "gurgaon", "mumbai", "pune",
    "mexico", "latam", "latin america",
    "australia", "sydney", "melbourne",
    "singapore", "hong kong", "china",
    "worldwide", "global",
    "remote global", "remote worldwide",
]


# -------------------------------
# LOAD COMPANIES
# -------------------------------
def load_companies():
    print("[INFO] Loading companies.json...")
    with open("config/companies.json", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} companies.")
    return data


# -------------------------------
# FILTER BY POSTING AGE (30 MIN)
# -------------------------------
def posted_within(job, minutes=30):
    """
    Accepts job dict with `created_at` / `updated_at` (ISO8601 strings).
    Returns True if within the last `minutes`.
    """
    updated = job.get("updated_at")
    created = job.get("created_at")

    timestamp = updated or created
    if not timestamp:
        return False  # no timestamp => ignore

    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        return False

    now = datetime.now(timezone.utc)
    diff_min = (now - dt).total_seconds() / 60.0
    return diff_min <= minutes


# -------------------------------
# JOB FILTER CHECK
# -------------------------------
def job_matches(job):
    title = job.get("title", "") or ""
    desc = job.get("description", "") or ""
    loc = job.get("location", "") or ""

    text = (title + " " + desc).lower()
    loc_low = loc.lower()

    # 1) Exclude clearly senior / non-junior / intern roles
    if any(bad in text for bad in EXCLUDE_KEYWORDS):
        return False

    # 2) Require at least one junior / early-career signal
    if not any(exp in text for exp in EXPERIENCE_KEYWORDS):
        return False

    # 3) Require target role keywords
    if not any(role in text for role in TARGET_ROLES):
        return False

    # 4) Location must NOT contain non-US markers
    if any(bad in loc_low for bad in LOCATION_EXCLUDE):
        return False

    # 5) Location must look like US / US-remote / US-hybrid / onsite US
    if not any(ok in loc_low for ok in LOCATION_INCLUDE):
        # As a fallback, accept locations that explicitly mention US states
        us_states = [
            "california", "ca", "new york", "ny",
            "texas", "tx", "washington", "wa",
            "massachusetts", "ma", "virginia", "va",
            "colorado", "co", "illinois", "il",
            "georgia", "ga", "north carolina", "nc",
            "ohio", "oh", "arizona", "az",
            "florida", "fl", "pennsylvania", "pa",
        ]
        if not any(state in loc_low for state in us_states):
            return False

    # 6) Must be posted within last 30 minutes
    if not posted_within(job, minutes=30):
        return False

    return True


# -------------------------------
# UNIQUE JOB HASH
# -------------------------------
def job_id(company, job):
    base = f"{company}|{job.get('title','')}|{job.get('url','')}"
    return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()


# -------------------------------
# EMAIL SENDER (uses env/Secrets)
# -------------------------------
def send_email(new_jobs):
    import smtplib
    from email.mime.text import MIMEText

    if not new_jobs:
        print("[INFO] No new jobs found — not sending email.")
        return

    email_address = os.environ.get("EMAIL_ADDRESS")
    email_password = os.environ.get("EMAIL_PASSWORD")

    if not email_address or not email_password:
        print(
            "[WARN] EMAIL_ADDRESS or EMAIL_PASSWORD not set — "
            "skipping email send. Jobs will be printed instead."
        )
        for j in new_jobs:
            print(f"JOB: {j['title']} — {j['company']} — {j['location']} | {j['url']}")
        return

    print(f"[INFO] Sending email with {len(new_jobs)} new jobs...")

    lines = []
    for j in new_jobs:
        lines.append(f"{j['title']} — {j['company']} — {j['location']}")
        lines.append(j["url"])
        lines.append("")
    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"{len(new_jobs)} New Junior Jobs (Last 30 Minutes)"
    msg["From"] = email_address
    msg["To"] = email_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_address, email_password)
        server.send_message(msg)

    print("[INFO] Email sent successfully.")


# -------------------------------
# FIRESTORE (optional)
# -------------------------------
def get_firestore_client():
    try:
        db = firestore.Client()
        print("[INFO] Firestore ENABLED.")
        return db
    except Exception as e:
        print(f"[INFO] Firestore DISABLED — running in dev mode. Reason: {e}")
        return None


# -------------------------------
# MAIN FUNCTION
# -------------------------------
def main(request=None):
    print("\n======== JOB ALERT AGENT STARTED ========\n")

    db = get_firestore_client()
    companies = load_companies()

    seen = set()
    if db:
        seen = {doc.id for doc in db.collection("jobs_seen").stream()}

    print(f"[INFO] Loaded {len(seen)} previously seen job IDs.\n")

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
                "title": job.get("title", ""),
                "location": job.get("location", ""),
                "url": job.get("url", ""),
            }

            if db:
                db.collection("jobs_seen").document(jid).set(record)
            seen.add(jid)
            new_jobs.append(record)

        print(f"[INFO] {name}: {len(new_jobs)} total new jobs accumulated so far.")

    print(f"\n[INFO] FINAL: Found {len(new_jobs)} new jobs.")
    send_email(new_jobs)

    print("\n======== JOB ALERT AGENT FINISHED ========\n")
    return "OK"


if __name__ == "__main__":
    main()
