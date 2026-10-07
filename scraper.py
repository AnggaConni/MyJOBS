import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
MAX_GOOGLE_QUERIES = int(os.getenv("MAX_GOOGLE_QUERIES", "6"))
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
BASE_URL = "https://www.loker.id"

CITIES = [
    "Ketapang", "Pontianak", "Singkawang", "Kubu Raya", "Sintang",
    "Sambas", "Sanggau", "Sekadau", "Melawi", "Landak",
    "Bengkayang", "Kapuas Hulu", "Mempawah"
]

QUERIES = [
    "lowongan kerja Kalimantan Barat",
    "lowongan kerja Ketapang",
    "lowongan kerja Pontianak",
    "lowongan kerja Singkawang",
    "lowongan kerja Kubu Raya",
    "lowongan kerja Kalbar",
]

ALIASES = {
    "kabupaten ketapang": "Ketapang",
    "kab. ketapang": "Ketapang",
    "ketapang": "Ketapang",
    "pontianak": "Pontianak",
    "singkawang": "Singkawang",
    "kubu raya": "Kubu Raya",
    "sintang": "Sintang",
    "sambas": "Sambas",
    "sanggau": "Sanggau",
    "sekadau": "Sekadau",
    "melawi": "Melawi",
    "landak": "Landak",
    "bengkayang": "Bengkayang",
    "kapuas hulu": "Kapuas Hulu",
    "mempawah": "Mempawah",
}


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canon(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def city_of(text):
    text = clean(text).lower()
    for alias, city in ALIASES.items():
        if alias in text:
            return city
    return "Kalimantan Barat"


def make_id(*parts):
    seed = "|".join(canon(part) for part in parts)
    return "job-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def normalize_google(item, query):
    detected = item.get("detected_extensions") or {}
    apply_options = item.get("apply_options") or []
    apply_url = ""
    if isinstance(apply_options, list) and apply_options:
        apply_url = clean((apply_options[0] or {}).get("link"))

    title = clean(item.get("title"))
    company = clean(item.get("company_name"))
    location = clean(item.get("location"))
    description = clean(item.get("description"))
    source_url = apply_url or clean(item.get("share_link")) or clean(item.get("link"))
    district = city_of(f"{location} {title} {description}")

    return {
        "id": make_id(title, company, district, source_url),
        "title": title,
        "company": company or "Unknown company",
        "location": location or district,
        "district": district,
        "province": "West Kalimantan",
        "country": "Indonesia",
        "via": clean(item.get("via") or "Google Jobs"),
        "source": "Google Jobs",
        "posted_at": clean(detected.get("posted_at") or "Unknown"),
        "schedule_type": clean(detected.get("schedule_type")),
        "salary": clean(detected.get("salary")),
        "description": description[:500],
        "original_url": source_url or "#",
        "search_query": query,
        "extensions": [clean(x) for x in (item.get("extensions") or []) if clean(x)],
        "remote": bool(detected.get("work_from_home")),
    }


def fetch_google():
    if not SERPAPI_KEY:
        return [], {"status": "skipped", "count": 0, "message": "SERPAPI_KEY not configured"}

    jobs, errors = [], []
    for query in QUERIES[:max(1, MAX_GOOGLE_QUERIES)]:
        try:
            response = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_jobs",
                    "q": query,
                    "hl": "id",
                    "gl": "id",
                    "api_key": SERPAPI_KEY,
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                errors.append(f"{query}: {payload['error']}")
                continue
            for item in payload.get("jobs_results") or []:
                job = normalize_google(item, query)
                if job["title"]:
                    jobs.append(job)
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {exc}")

    return jobs, {
        "status": "ok" if jobs else ("error" if errors else "empty"),
        "count": len(jobs),
        "queries": QUERIES[:max(1, MAX_GOOGLE_QUERIES)],
        "errors": errors,
    }


def fetch_loker():
    jobs, errors = [], []
    for city in CITIES[:6]:
        try:
            response = requests.get(
                f"{BASE_URL}/cari-lowongan-kerja",
                params={"q": city},
                headers={"User-Agent": "Mozilla/5.0 (compatible; ketapangJOBS/2.0)"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.select("h2 a, h3 a, h4 a"):
                title = clean(anchor.get_text(" ", strip=True))
                href = clean(anchor.get("href"))
                url = urljoin(BASE_URL, href)
                if not title or not href or "lowongan-kerja" not in urlparse(url).path.lower():
                    continue
                district = city_of(f"{city} {title}")
                jobs.append({
                    "id": make_id("loker.id", title, url),
                    "title": title,
                    "company": "See source page",
                    "location": city,
                    "district": district,
                    "province": "West Kalimantan",
                    "country": "Indonesia",
                    "via": "Loker.id",
                    "source": "Loker.id",
                    "posted_at": "Unknown",
                    "schedule_type": "",
                    "salary": "",
                    "description": "Open the original source for qualification and company details.",
                    "original_url": url,
                    "search_query": f"loker {city}",
                    "extensions": [],
                    "remote": False,
                })
        except Exception as exc:
            errors.append(f"{city}: {type(exc).__name__}: {exc}")

    return jobs, {
        "status": "ok" if jobs else ("error" if errors else "empty"),
        "count": len(jobs),
        "errors": errors,
    }


def dedupe(jobs):
    unique = {}
    for job in jobs:
        url = canon(job.get("original_url"))
        title = canon(job.get("title"))
        key = f"url:{url}" if url and url != "#" else f"text:{title}|{canon(job.get('company'))}|{canon(job.get('district'))}"
        if key not in unique:
            unique[key] = job
    return list(unique.values())


def summary(jobs):
    return {
        "by_district": dict(Counter(j.get("district", "Unknown") for j in jobs).most_common()),
        "by_source": dict(Counter(j.get("source", "Unknown") for j in jobs).most_common()),
    }


def main():
    start = time.time()
    all_jobs = []
    sources = {}

    google, google_health = fetch_google()
    loker, loker_health = fetch_loker()
    all_jobs.extend(google)
    all_jobs.extend(loker)
    sources["Google Jobs"] = google_health
    sources["Loker.id"] = loker_health

    jobs = dedupe(all_jobs)
    errors = sum((source.get("errors", []) for source in sources.values()), [])

    output = {
        "schema_version": 2,
        "last_updated": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "total": len(jobs),
        "status": "ok" if jobs else ("error" if errors else "empty"),
        "region": "West Kalimantan, Indonesia",
        "coverage": CITIES,
        "jobs": jobs,
        "summary": summary(jobs),
        "sources": sources,
        "errors": errors[:50],
        "runtime_seconds": round(time.time() - start, 2),
    }

    with open("vacancy.json", "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)

    print(f"Collected {len(jobs)} unique jobs; status={output['status']}.")


if __name__ == "__main__":
    main()
