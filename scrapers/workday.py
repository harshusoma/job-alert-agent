import requests
import json

def fetch_workday_jobs(company, url):
    jobs = []

    try:
        # Workday API requires JSON POST for job search
        api_url = url + "/fs/api/public/embedded-job-search"

        payload = {
            "appliedFacets": {},
            "limit": 50,
            "offset": 0,
            "searchText": ""
        }

        resp = requests.post(api_url, json=payload, timeout=15)
        data = resp.json()

        for job in data.get("jobPostings", []):
            jobs.append({
                "title": job.get("title", ""),
                "company": company,
                "location": job.get("locationsText", "Not specified"),
                "url": url + "/job/" + job.get("externalPath", ""),
                "description": job.get("jobDescription", "")
            })

    except Exception as e:
        print(f"[ERROR] Workday scraper failed for {company}: {e}")

    return jobs
