import requests
from bs4 import BeautifulSoup

def fetch_greenhouse_jobs(company, url):
    jobs = []

    try:
        resp = requests.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        job_posts = soup.select("a[href*='/jobs/']")

        for post in job_posts:
            title = post.text.strip()
            job_url = "https://boards.greenhouse.io" + post["href"]

            # Try to extract location
            loc_div = post.find_next("div", class_="location")
            location = loc_div.text.strip() if loc_div else "Not specified"

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
