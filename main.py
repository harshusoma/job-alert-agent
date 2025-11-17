import os
import json
import hashlib

try:
    from google.cloud import firestore  # type: ignore
except Exception:
    firestore = None  # type: ignore


TARGET_ROLES = [
    "software engineer",
    "ml engineer",
    "machine learning engineer",
    "ai engineer",
    "data scientist",
    "data engineer",
    "security engineer",
    "cybersecurity",
    "security analyst",
]

EXPERIENCE_KEYWORDS = [
    "0-2 years",
    "0–2 years",
    "0 to 2 years",
    "entry level",
    "new grad",
    "graduate",
    "junior",
]

LOCATION_KEYWORDS = ["us", "usa", "united states", "u.s."]


def load_companies() -> list[dict]:
    print("[INFO] Loading companies.json...")
    with open("config/companies.json", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} companies.")
    return data


def job_matches(job: dict) -> bool:
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    loc = job.get("location", "").lower()

    return (
        any(role in text for role in TARGET_ROLES)
        and any(exp in text for exp in EXPERIENCE_KEYWORDS)
        and any(loc_kw in loc for loc_kw in LOCATION_KEYWORDS)
    )


def job_id(company: str, job: dict) -> str:
    base = f"{company}|{job.get('title','')}|{job.get('url','')}"
    # usedforsecurity=False avoids an OpenSSL warning on some platforms
    return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()


def send_email(new_jobs: list[dict]) -> None:
    import smtplib
    from email.mime.text import MIMEText

    if not new_jobs:
        print("[INFO] No new jobs found — not sending email.")
        return

    # READ FROM GITHUB SECRETS / ENV, NOT HARDCODED
    email_address = os.environ.get("EMAIL_ADDRESS")
    email_password = os.environ.get("EMAIL_PASSWORD")

    if not email_address or not email_password:
        print(
            "[WARN] EMAIL_ADDRESS or EMAIL_PASSWORD not set — "
            "skipping email send. Jobs will still be logged."
        )
        for j in new_jobs:
            print(f"JOB: {j['title']} — {j['company']} | {j['url']}")
        return

    print(f"[INFO] Sending email with {len(new_jobs)} new jobs...")

    lines = []
    for j in new_jobs:
        lines.append(f"{j['title']} — {j['company']}")
        lines.append(j["url"])
        lines.append("")
    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"{len(new_jobs)} New Jobs Found"
    msg["From"] = email_address
    msg["To"] = email_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_address, email_password)
        server.send_message(msg)

    print("[INFO] Email sent successfully.")


def get_firestore_client():
    """Return (db, use_firestore_flag)."""
    if firestore is None:
        print("[INFO] google.cloud.firestore not installed — dev mode.")
        return None, False

    try:
        db = firestore.Client()
        print("[INFO] Firestore ENABLED — using real database.")
        return db, True
    except Exception as e:
        print(
            "[INFO] Firestore DISABLED — running in development mode. "
            f"Reason: {e}"
        )
        return None, False


def main(_request=None) -> str:
    print("\n======== JOB ALERT AGENT STARTED ========\n")

    db, use_firestore = get_firestore_client()

    companies = load_companies()

    if use_firestore:
        seen_ids = {doc.id for doc in db.collection("jobs_seen").stream()}
    else:
        seen_ids = set()

    print(f"[INFO] Loaded {len(seen_ids)} previously seen job IDs.\n")

    # Imported here so that scrapers can be edited without circular issues
    from scrapers.greenhouse import fetch_greenhouse_jobs
    from scrapers.lever import fetch_lever_jobs
    from scrapers.workday import fetch_workday_jobs

    new_jobs: list[dict] = []

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
            if jid in seen_ids:
                continue

            record = {
                "company": name,
                "title": job.get("title", ""),
                "location": job.get("location", ""),
                "url": job.get("url", ""),
            }

            if use_firestore:
                db.collection("jobs_seen").document(jid).set(record)
            seen_ids.add(jid)
            new_jobs.append(record)

        print(f"[INFO] {name}: {len(new_jobs)} total new jobs accumulated so far.")

    print(f"\n[INFO] FINAL: Found {len(new_jobs)} new jobs.")
    send_email(new_jobs)

    print("\n======== JOB ALERT AGENT FINISHED ========\n")
    return "OK"


if __name__ == "__main__":
    main()
