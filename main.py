import json
import hashlib
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

LOCATION_KEYWORDS = ["us", "usa", "united states", "u.s."]


# -------------------------------
# LOAD COMPANIES
# -------------------------------
def load_companies():
    with open("config/companies.json") as f:
        return json.load(f)


# -------------------------------
# JOB FILTER CHECK
# -------------------------------
def job_matches(job):
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    loc = job.get("location", "").lower()

    if not any(role in text for role in TARGET_ROLES):
        return False

    if not any(exp in text for exp in EXPERIENCE_KEYWORDS):
        return False

    if not any(loc_kw in loc for loc_kw in LOCATION_KEYWORDS):
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
        return

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


# -------------------------------
# MAIN CLOUD FUNCTION
# -------------------------------
def main(request=None):
    db = firestore.Client()
    companies = load_companies()

    seen = {doc.id for doc in db.collection("jobs_seen").stream()}
    new_jobs = []

    for company in companies:
        name = company["name"]
        ats = company["ats"]
        url = company["careers_url"]

        # SELECT SCRAPER
        if ats == "greenhouse":
            jobs = fetch_greenhouse_jobs(name, url)
        elif ats == "lever":
            jobs = fetch_lever_jobs(name, url)
        elif ats == "workday":
            jobs = fetch_workday_jobs(name, url)
        else:
            jobs = []

        # PROCESS JOBS
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

            db.collection("jobs_seen").document(jid).set(record)
            new_jobs.append(record)

    send_email(new_jobs)
    return "OK"
