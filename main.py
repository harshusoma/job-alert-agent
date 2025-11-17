import json
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

# Firestore is optional now
try:
    from google.cloud import firestore
except ImportError:
    firestore = None

from scrapers.greenhouse import fetch_greenhouse_jobs
from scrapers.lever import fetch_lever_jobs
from scrapers.ashby import fetch_ashby_jobs
from scrapers.workday import fetch_workday_jobs


# -------------------------------
# CONFIG: ROLES / EXPERIENCE / LOCATION
# -------------------------------

TARGET_ROLE_KEYWORDS = [
    "software engineer",
    "swe",
    "backend engineer",
    "frontend engineer",
    "full stack engineer",
    "ml engineer",
    "machine learning engineer",
    "ai engineer",
    "data scientist",
    "data engineer",
    "security engineer",
    "application security engineer",
    "security analyst",
    "cybersecurity engineer",
    "site reliability engineer",
    "sre",
]

# Experience / level indicators for NEW GRAD / EARLY CAREER / ASSOCIATE
EXPERIENCE_KEYWORDS = [
    "entry level",
    "entry-level",
    "new grad",
    "new graduate",
    "university graduate",
    "recent graduate",
    "early career",
    "early-career",
    "junior",
    "associate",
    "assistant",
    "0-1 years",
    "0–1 years",
    "0 to 1 years",
    "0-2 years",
    "0–2 years",
    "0 to 2 years",
    "up to 2 years",
]

# Titles that we treat as okay even without explicit years in text
ASSOCIATE_TITLE_KEYWORDS = [
    "associate software engineer",
    "associate data engineer",
    "associate data scientist",
    "associate ml engineer",
    "associate machine learning engineer",
    "assistant software engineer",
    "assistant data scientist",
]

# Senior / staff / manager etc. to EXCLUDE
SENIOR_EXCLUDE_KEYWORDS = [
    "senior",
    "sr.",
    "sr ",
    "staff",
    "principal",
    "lead ",
    "lead-",
    "director",
    "manager",
    "head of",
    "architect",
    "vp ",
    "vice president",
]

# US location detection
US_LOCATION_KEYWORDS = [
    "united states",
    "u.s.",
    "u. s.",
    " us ",
    "(us)",
    " usa",
    "remote-us",
    "remote us",
    "anywhere in the us",
]

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


# -------------------------------
# HELPERS
# -------------------------------

def load_companies():
    print("[INFO] Loading companies.json...")
    with open("config/companies.json") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} companies.")
    return data


def normalize_ts(ts):
    """
    Convert a timestamp to a timezone-aware datetime in UTC.
    Supports:
    - datetime already
    - ISO strings like '2025-11-17T12:34:56Z'
    - None -> None
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    if isinstance(ts, str):
        s = ts.strip()
        # Add UTC if 'Z'
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    return None


def posted_within_window(job, minutes=30):
    posted_at = normalize_ts(job.get("posted_at"))
    if posted_at is None:
        return False
    now = datetime.now(timezone.utc)
    delta = now - posted_at
    return delta <= timedelta(minutes=minutes)


def is_us_location(loc: str) -> bool:
    if not loc:
        return False
    loc_l = f" {loc.lower()} "

    # 1) simple keyword match
    for kw in US_LOCATION_KEYWORDS:
        if kw in loc_l:
            return True

    # 2) check for ", CA", ", NY" etc
    m = re.search(r",\s*([A-Z]{2})(?:\s|$)", loc)
    if m:
        state = m.group(1).upper()
        if state in US_STATE_CODES:
            return True

    return False


def is_entry_or_associate(title: str, text: str) -> bool:
    # title, text should already be lower()
    # A: explicit experience / level words
    if any(exp in text for exp in EXPERIENCE_KEYWORDS):
        return True

    # B: associate-type titles
    if any(k in title for k in ASSOCIATE_TITLE_KEYWORDS):
        return True

    return False


def is_relevant_role(title: str, text: str) -> bool:
    if any(role in title for role in TARGET_ROLE_KEYWORDS):
        return True
    if any(role in text for role in TARGET_ROLE_KEYWORDS):
        return True
    return False


def looks_senior(title: str) -> bool:
    return any(bad in title for bad in SENIOR_EXCLUDE_KEYWORDS)


def job_matches(job) -> bool:
    """
    Apply ALL filters:
    - Fresh (posted within last 30 min)
    - US-only (including remote/hybrid if US-based)
    - Full-time (no internships)
    - Role in SWE / ML / Data / Security family
    - Level: entry / new grad / junior / early-career / associate
    - Exclude senior/staff/lead/etc.
    """
    title = (job.get("title") or "").strip()
    desc = job.get("description") or ""
    loc = job.get("location") or ""
    employment_type = (job.get("employment_type") or "").lower()

    title_l = title.lower()
    text_l = f"{title_l} {desc.lower()}"

    # 1) fresh
    if not posted_within_window(job, minutes=30):
        return False

    # 2) US-only (including remote US / hybrid US)
    if not is_us_location(loc):
        return False

    # 3) no internships
    if "intern" in title_l or "internship" in title_l or employment_type == "intern":
        return False

    # 4) exclude senior-level
    if looks_senior(title_l):
        return False

    # 5) must look like entry / early-career / associate
    if not is_entry_or_associate(title_l, text_l):
        return False

    # 6) must be one of our target role families
    if not is_relevant_role(title_l, text_l):
        return False

    return True


def job_id(company, job):
    base = f"{company}|{job.get('title','')}|{job.get('url','')}"
    return hashlib.md5(base.encode()).hexdigest()


def send_email(new_jobs):
    import smtplib
    from email.mime.text import MIMEText

    if not new_jobs:
        print("[INFO] No new jobs — skipping email.")
        return

    email_address = os.getenv("EMAIL_ADDRESS")
    email_password = os.getenv("EMAIL_PASSWORD")

    if not email_address or not email_password:
        print("[WARN] EMAIL_ADDRESS or EMAIL_PASSWORD not set — cannot send email.")
        return

    print(f"[INFO] Sending email with {len(new_jobs)} new jobs...")

    lines = []
    for j in new_jobs:
        lines.append(f"{j['title']} — {j['company']}")
        lines.append(j["url"])
        if j.get("location"):
            lines.append(f"Location: {j['location']}")
        lines.append("")  # blank line

    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"{len(new_jobs)} new SWE/ML/Data/Security jobs (last 30 min)"
    msg["From"] = email_address
    msg["To"] = email_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_address, email_password)
        server.send_message(msg)

    print("[INFO] Email sent successfully.")


def get_firestore_client():
    if firestore is None:
        print("[INFO] google-cloud-firestore not installed — skipping Firestore.")
        return None

    try:
        client = firestore.Client()
        print("[INFO] Firestore client initialized.")
        return client
    except Exception as e:
        print(f"[INFO] Firestore DISABLED — running in dev mode. Reason: {e}")
        return None


def main(request=None):
    print("\n======== JOB ALERT AGENT STARTED ========\n")

    db = get_firestore_client()
    if db is not None:
        try:
            seen_ids = {doc.id for doc in db.collection("jobs_seen").stream()}
            print(f"[INFO] Loaded {len(seen_ids)} previously seen job IDs from Firestore.")
        except Exception as e:
            print(f"[WARN] Could not read Firestore: {e}")
            seen_ids = set()
    else:
        seen_ids = set()

    companies = load_companies()
    new_jobs = []

    for company in companies:
        name = company["name"]
        ats = company["ats"]
        careers_url = company.get("careers_url")
        board_name = company.get("board_name")  # for Ashby

        print(f"\n[INFO] Fetching jobs for: {name} ({ats})")

        try:
            if ats == "greenhouse":
                jobs = fetch_greenhouse_jobs(name, careers_url)
            elif ats == "lever":
                jobs = fetch_lever_jobs(name, careers_url)
            elif ats == "ashby":
                jobs = fetch_ashby_jobs(name, board_name or careers_url)
            elif ats == "workday":
                jobs = fetch_workday_jobs(name, careers_url)
            else:
                print(f"[WARN] Unsupported ATS: {ats}")
                jobs = []
        except Exception as e:
            print(f"[ERROR] {ats} scraper failed for {name}: {e}")
            jobs = []

        print(f"[INFO] {name}: scraper returned {len(jobs)} raw jobs.")

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
                "url": job.get("url", ""),
                "employment_type": job.get("employment_type", ""),
                "posted_at": job.get("posted_at").isoformat()
                if isinstance(job.get("posted_at"), datetime)
                else str(job.get("posted_at")),
            }

            if db is not None:
                try:
                    db.collection("jobs_seen").document(jid).set(record)
                    seen_ids.add(jid)
                except Exception as e:
                    print(f"[WARN] Failed to write to Firestore for {name}: {e}")

            new_jobs.append(record)

        print(f"[INFO] {name}: {len(new_jobs)} total new jobs accumulated so far.")

    print(f"\n[INFO] FINAL: Found {len(new_jobs)} new jobs.")
    send_email(new_jobs)

    print("\n======== JOB ALERT AGENT FINISHED ========\n")
    return "OK"


if __name__ == "__main__":
    main()
