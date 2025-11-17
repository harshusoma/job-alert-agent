import requests

def fetch_lever_jobs(company, url):
    jobs = []

    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()

        for job in data:
            jobs.append({
                "title": job.get("text", {}).get("title", ""),
                "company": company,
                "location": job.get("categories", {}).get("location", "Not specified"),
                "url": job.get("hostedUrl", ""),
                "description": job.get("descriptionPlain", "")
            })
    except Exception as e:
        print(f"[ERROR] Lever scraper failed for {company}: {e}")

    return jobs
