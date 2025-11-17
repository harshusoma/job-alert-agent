import re
import requests


def fetch_workday_jobs(company, url):
    jobs = []

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        html = resp.text

        # Extremely simple heuristic: any link that looks like ".../job/..."
        matches = re.findall(r'href="([^"]+?/job/[^"]+)"', html)
        unique_links = list(dict.fromkeys(matches))  # dedupe while preserving order

        print(f"[WORKDAY] Found {len(unique_links)} potential job links for {company}")

        for link in unique_links[:30]:  # safety limit
            if link.startswith("http"):
                job_url = link
            else:
                # crude base URL; works for many Workday setups
                job_url = "https://careers." + link.lstrip("/")

            # Title from last part of URL (rough approximation)
            slug = link.split("/")[-1]
            title = slug.replace("-", " ").replace("_", " ").title()

            jobs.append({
                "title": title,
                "company": company,
                "location": "Not specified",
                "url": job_url,
                "description": "",
            })

    except Exception as e:
        print(f"[ERROR] Workday scraper failed for {company}: {e}")

    return jobs
