import requests


def fetch_lever_jobs(company, url):
    jobs = []

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        print(f"[LEVER] Found {len(data)} raw postings for {company}")

        for post in data:
            title = post.get("text", {}).get("title", "")
            location = post.get("categories", {}).get("location", "Not specified")
            job_url = post.get("hostedUrl", "")
            description = post.get("descriptionPlain", "")

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "url": job_url,
                "description": description,
            })

    except Exception as e:
        print(f"[ERROR] Lever scraper failed for {company}: {e}")

    return jobs
