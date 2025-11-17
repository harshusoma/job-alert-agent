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
    "ml engineer",
    "machine learning engineer",
    "ai engineer",
    "data scientist",
    "data engineer",
    "security engineer",
    "cybersecurity",
    "security analyst"
]

EXPERIENCE_KEYWORDS = [
    "0-2 years", "0–2 years", "0 to 2 years",
    "entry level", "new grad", "graduate", "junior"
]

EXCLUDE_KEYWORDS = [
    "senior", "sr ", "sr.", "staff",
    "principal", "lead",
    "director", "architect",
    "manager", "head",
    "intern", "internship", "co-op"
]

LOCATION_KEYWORDS = ["us", "usa", "united states", "u.s."]


# -------------------------------
# LOAD COMPANIES
# -------------------------------
def load_companies():
    print("[INFO] Loading companies.json...")
    with open("config/companies.json") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} companies.")
    return data


# -------------------------------
# FILTER BY POSTING AGE (15 MIN)
# -------------------------------
def posted_within(job, minutes=15):
    updated = job.get("updated_at")
    created = job.get("created_at")

    timestamp = updated or created
    if not timestamp:
        return False

    try:
        job_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except:
        return False

    now = datetime.now(timezone.utc)
    diff_minutes = (now - job_time).total_seconds() / 60

    return diff_minutes <= minutes


# -------------------------------
# JOB FILTER CHECK
# -------------------------------
def job_matches(job):
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    loc = job.get("location", "").lower()

    # ❌ Exclude internships, senior roles
    if any(bad in text for bad in EXCLUDE_KEYWORDS):
        return False

    # ✔ Role match
    if not any(role in text for role in TARGET_ROLES):
        return False

    # ✔ Experience level match
    if not any(exp in text for exp in EXPERIENCE_KEYWORDS):
        return False

    # ✔ US-based
    if not any(loc_kw in loc for loc_kw in LOCATION_KEYWORDS):
        return False

    # ✔ Posted recently (15 min)
    if not posted_within(job, minutes=15):
        return False

    return True


# -------------------------------
# UNIQUE JOB HASH
# -------------------------------
def job_id(company, job):
    base = f"{company}|{job['title']}|{job['url']}"
    return hashlib.md5(base.encode()).hexdigest()


# -------------------------------
# EMAIL SENDER
# -------------------------------
def send_email(new_jobs):
    import smtplib
    from email.mime.text import MIMEText

    if not new_jobs:
        print("[INFO] No new jobs found — not sending email.")
        return

    print(f"[INFO] Sending email with {len(new_jobs)} new jobs...")

    body = ""
    for j in new_jobs:
        body += f"{j['title']} — {j['company']}\n{j['url']}\n\n"

    msg = MIMEText(body)
    msg["Subject"] = f"{len(new_jobs)} New Jobs Found (Last 15 Minutes)"
    msg["From"] = "somaharsha71@gmail.com"
    msg["To"] = "somaharsha71@gmail.com"

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login("somaharsha71@gmail.com", "xzrs dgan dgdh noke")
        server.send_message(msg)

    print("[INFO] Email sent successfully.")


# -------------------------------
# MAIN FUNCTION
# -------------------------------
def main(request=None):
    print("\n======== JOB ALERT AGENT STARTED ========\n")

    # Firestore optional (disabled if no ADC)
    try:
        db = firestore.Client()
        print("[INFO] Firestore ENABLED.")
    except Exception as e:
        print(f"[INFO] Firestore DISABLED — running in dev mode. Reason: {e}")
        db = None

    companies = load_companies()
    seen = set()

    if db:
        seen = {doc.id for doc in db.collection("jobs_seen").stream()}

    print(f"[INFO] Loaded {len(seen)} previously seen job IDs.\n")

    new_jobs = []

    # Fetch jobs for each company
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


# Run main
if __name__ == "__main__":
    main()
