import requests
from bs4 import BeautifulSoup


def fetch_greenhouse_jobs(company, url):
    jobs = []

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Typical Greenhouse structure: div.opening > a + span.location
        postings = soup.select("div.opening")

        print(f"[GREENHOUSE] Found {len(postings)} raw postings for {company}")

        for post in postings:
            link_el = post.select_one("a")
            if not link_el:
                continue

            title = link_el.text.strip()
            href = link_el.get("href", "")

            # Some boards use relative links like "/databricks/job/123..."
            if href.startswith("http"):
                job_url = href
            else:
                job_url = "https://boards.greenhouse.io" + href

            loc_el = post.select_one(".location")
            location = loc_el.text.strip() if loc_el else "Not specified"

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "url": job_url,
                "description": ""
            })

    except Exception as e:
        print(f"[ERROR] Greenhouse scraper failed for {company}: {e}")

    return jobs
