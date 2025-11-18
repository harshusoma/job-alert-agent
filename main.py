import os
import json
import hashlib
from datetime import datetime, timedelta, timezone

from google.cloud import firestore
from google.auth.exceptions import DefaultCredentialsError

# --- SCRAPERS ---
from scrapers.greenhouse import fetch_greenhouse_jobs
from scrapers.lever import scrape as scrape_lever
# from scrapers.workday import fetch_workday_jobs   # DISABLED by your request


# -----------------------------------
# FILTERING CONFIG
# -----------------------------------
ROLE_KEYWORDS = [
    "software engineer",
    "swe",
    "ml engineer",
    "machine learning engineer",
    "ai engineer",
    "ai/ml engineer",
    "data scientist",
    "data science",
    "data engineer",
    "security engineer",
    "cybersecurity",
    "security analyst",
    "application security",
    "cloud security",
    "site reliability engineer",
    "sre",
    "platform engineer"
]

LEVEL_KEYWORDS = [
    "entry level",
    "new grad",
    "new graduate",
    "graduate",
    "junior",
    "early career",
    "associate",
    "assistant"
]

EXCLUDE_KEYWORDS = [
    "intern",
    "internship",
    "intern -",
    "intern,",
    "senior",
    "sr.",
    "sr ",
    "staff",
    "principal",
    "lead ",
    "manager",
    "director",
    "vp ",
    "vice president",
    "iii",
    "iv",
    "v "
]

LOCATION_KEYWORDS = [
    "us",
    "usa",
    "u.s.",
    "united states",
    "remote-us",
    "remote us",
    "remote (us)",
    "anywhere in the us",
    "across the us",
    "within the united states",
    "hybrid",
    "onsite",
    "on-site"
]


# -----------------------------------
# HELPERS
# -----------------------------------
def _norm(text: str) -> str:
    return (text or "").lower()


def load_companies():
    print("[INFO] Loading companies.json...")
    with open("config/companies.json") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} companies.")
    return data


def job_matches(job: dict) -> bool:
    title = _norm(job.get("title"))
    desc = _norm(job.get("description"))
    loc = _norm(job.get("location"))
    combined = f"{title} {desc}"

    # 1) ROLE match
    if not any(key in combined for key in ROLE_KEYWORDS):
        return False

    # 2) LEVEL match
    if not any(key in combined for key in LEVEL_KEYWORDS):
        return False

    # 3) EXCLUSIONS
    if any(key in combined for key in EXCLUDE_KEYWORDS):
        return False

    # 4) US-only locations
    if LOCATION_KEYWORDS and not any(key in loc for key in LOCATION_KEYWORDS):
        return False

    return True


def job_id(company: str, job: dict) -> str:
    base = f"{company}|{job.get('title','')}|{job.get('url','')}"
    return hashlib.md5(base.encode()).hexdigest()


def get_firestore_client():
    try:
        client = firestore.Client()
        print("[INFO] Firestore ENABLED — using jobs_seen collection.")
        return client
    except DefaultCredentialsError as e:
        print(
            "[INFO] Firestore DISABLED — running in dev mode. "
            f"Reason: {e}"
        )
        return None
    except Exception as e:
        print(
            "[INFO] Firestore DISABLED — unexpected error, running in dev mode. "
            f"Reason: {e}"
        )
        return None


def send_email(new_jobs):
    import smtplib
    from email.mime.text import MIMEText

    if not new_jobs:
        print("[INFO] No new jobs — skipping email.")
        return

    email_address = os.environ.get("EMAIL_ADDRESS", "").strip()
    email_password = os.environ.get("EMAIL_PASSWORD", "").strip()

    if not email_address or not email_password:
        print(
            "[WARN] EMAIL_ADDRESS or EMAIL_PASSWORD env variable is missing. "
            "Cannot send email."
        )
        return

    print(f"[INFO] Sending email with {len(new_jobs)} new jobs to {email_address}...")

    lines = []
    for j in new_jobs:
        lines.append(f"{j['title']} — {j['company']}")
        lines.append(j["url"])
        loc = j.get("location")
        if loc:
            lines.append(f"Location: {loc}")
        lines.append("")  # blank line

    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"{len(new_jobs)} New Jobs Found"
    msg["From"] = email_address
    msg["To"] = email_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_address, email_password)
        server.send_message(msg)

    print("[INFO] Email sent successfully.")


# -----------------------------------
# MAIN LOGIC
# -----------------------------------
def main(request=None):
    print("\n======== JOB ALERT AGENT STARTED ========\n")

    db = get_firestore_client()
    companies = load_companies()

    if db:
        seen_ids = {doc.id for doc in db.collection("jobs_seen").stream()}
        print(f"[INFO] Loaded {len(seen_ids)} previously seen job IDs.\n")
    else:
        seen_ids = set()
        print("[INFO] Dev mode: not loading seen IDs (no Firestore).\n")

    new_jobs = []

    for company_cfg in companies:
        name = company_cfg["name"]
        ats = company_cfg["ats"]
        url = company_cfg["careers_url"]

        print(f"\n[INFO] Fetching jobs for: {name} ({ats})")

        # Dispatch scraper
        if ats == "greenhouse":
            jobs = fetch_greenhouse_jobs(name, url)

        elif ats == "lever":
            jobs = scrape_lever(name, url)

        # Workday disabled (you requested removal)
        # elif ats == "workday":
        #     jobs = fetch_workday_jobs(name, url)

        else:
            print(f"[WARN] Unsupported ATS '{ats}' for {name}, skipping.")
            jobs = []

        print(f"[INFO] {name}: scraper returned {len(jobs)} raw jobs.")

        # Filtering
        for job in jobs:
            if not job_matches(job):
                continue

            jid = job_id(name, job)
            if jid in seen_ids:
                continue

            record = {
                "company": name,
                "title": job.get("title", ""),
                "location": job.get("location", ""),
                "url": job.get("url", "")
            }

            if db:
                db.collection("jobs_seen").document(jid).set(record)

            new_jobs.append(record)

        print(f"[INFO] {name}: {len(new_jobs)} total new jobs accumulated so far.")

    print(f"\n[INFO] FINAL: Found {len(new_jobs)} new jobs.")
    send_email(new_jobs)

    print("\n======== JOB ALERT AGENT FINISHED ========\n")
    return "OK"


if __name__ == "__main__":
    main()
