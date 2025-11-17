import os
import json
import hashlib
from datetime import datetime, timezone, timedelta

# Firestore (disabled automatically in GitHub Actions)
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except Exception:
    FIRESTORE_AVAILABLE = False

# Scrapers
from scrapers.greenhouse import fetch_greenhouse_jobs
from scrapers.lever import fetch_lever_jobs
from scrapers.workday import fetch_workday_jobs
from scrapers.ashby import fetch_ashby_jobs


# ============================================
#  FILTER CONFIG
# ============================================

TARGET_ROLES = [
    "software engineer",
    "associate software engineer",
    "ml engineer",
    "machine learning engineer",
    "ai engineer",
    "data scientist",
    "data engineer",
    "security engineer",
    "cybersecurity",
    "security analyst",
    "early career",
    "associate",
    "assistant",
]

EXPERIENCE_KEYWORDS = [
    "entry level",
    "new grad",
    "graduate",
    "junior",
    "early career",
    "associate",
    "assistant",
]

# Exclude internships
EXCLUDE_KEYWORDS = ["intern", "internship", "co-op"]

LOCATION_KEYWORDS = [
    "us",
    "usa",
    "u.s.",
    "united states",
    "remote",
    "remote-us",
    "remote us",
    "anywhere in the us",
    "us only",
    "hybrid",
]


# ============================================
#  LOAD COMPANIES
# ============================================

def load_companies():
    print("[INFO] Loading companies.json...")
    with open("config/companies.json") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} companies.")
    return data


# ============================================
#  JOB FILTERING
# ============================================

def posted_within(job, minutes=30):
    """
    job["posted"] should be an ISO datetime string.
    Greenhouse has "updated_at" → ISO format.
    """
    if "posted" not in job:
        return False

    try:
        posted_time = datetime.fromisoformat(job["posted"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - posted_time) <= timedelta(minutes=minutes)
    except:
        return False


def job_matches(job):
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()
    loc = job.get("location", "").lower()

    full_text = f"{title} {desc}"

    # Must match target titles
    if not any(role in full_text for role in TARGET_ROLES):
        return False

    # Must match junior experience
    if not any(exp in full_text for exp in EXPERIENCE_KEYWORDS):
        return False

    # Exclude internships
    if any(bad in full_text for bad in EXCLUDE_KEYWORDS):
        return False

    # Location must match US filters
    if not any(loc_kw in loc for loc_kw in LOCATION_KEYWORDS):
        return False

    # Must be fresh (last 30 min)
    if not posted_within(job, minutes=30):
        return False

    return True


# ============================================
#  DEDUPING
# ============================================

def job_id(company, job):
    base = f"{company}|{job['title']}|{job['url']}"
    return hashlib.md5(base.encode()).hexdigest()


# ============================================
#  EMAIL SENDER
# ============================================

def send_email(new_jobs):
    import smtplib
    from email.mime.text import MIMEText

    if not new_jobs:
        print("[INFO] No new jobs — skipping email.")
        return

    print(f"[INFO] Sending email with {len(new_jobs)} jobs...")

    body = ""
    for j in new_jobs:
        body += f"{j['title']} — {j['company']}\n{j['url']}\n\n"

    msg = MIMEText(body)
    msg["Subject"] = f"{len(new_jobs)} New Jobs Found"
    msg["From"] = os.getenv("EMAIL_ADDRESS")
    msg["To"] = os.getenv("EMAIL_ADDRESS")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.getenv("EMAIL_ADDRESS"), os.getenv("EMAIL_PASSWORD"))
        server.send_message(msg)

    print("[INFO] Email sent successfully.")


# ============================================
#  MAIN ENTRY
# ============================================

def main(request=None):
    print("\n======== JOB ALERT AGENT STARTED ========\n")

    # Firestore disabled in GitHub Actions
    if FIRESTORE_AVAILABLE:
        try:
            db = firestore.Client()
            seen = {doc.id for doc in db.collection("jobs_seen").stream()}
            print(f"[INFO] Firestore ENABLED. Loaded {len(seen)} seen job IDs.")
        except Exception as e:
            print(f"[INFO] Firestore DISABLED — running in dev mode. Reason: {e}")
            db = None
            seen = set()
    else:
        print("[INFO] Firestore not available — dev mode ON.")
        db = None
        seen = set()

    companies = load_companies()
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
                "url": job["url"],
                "posted": job["posted"],
            }

            if db:
                db.collection("jobs_seen").document(jid).set(record)

            new_jobs.append(record)

    print(f"\n[INFO] FINAL: Found {len(new_jobs)} new jobs.")
    send_email(new_jobs)

    print("\n======== JOB ALERT AGENT FINISHED ========\n")
    return "OK"


if __name__ == "__main__":
    main()
