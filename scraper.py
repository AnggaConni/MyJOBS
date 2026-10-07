import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
RELIEFWEB_APPNAME = os.getenv("RELIEFWEB_APPNAME", "").strip()
MAX_GOOGLE_QUERIES = int(os.getenv("MAX_GOOGLE_QUERIES", "6"))
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
RELIEFWEB_LIMIT = int(os.getenv("RELIEFWEB_LIMIT", "250"))
BASE_URL = "https://www.loker.id"
RELIEFWEB_URL = "https://api.reliefweb.int/v2/jobs"
UN_RSS_URL = "https://careers.un.org/jobfeed?isPage=true&language=en"

CITIES = [
    "Ketapang", "Pontianak", "Singkawang", "Kubu Raya", "Sintang",
    "Sambas", "Sanggau", "Sekadau", "Melawi", "Landak",
    "Bengkayang", "Kapuas Hulu", "Mempawah"
]

INDONESIA_TERMS = CITIES + [
    "Indonesia", "Jakarta", "Surabaya", "Bandung", "Denpasar", "Medan",
    "Makassar", "Papua", "Jayapura", "Bali"
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


def make_id(*parts):
    seed = "|".join(canon(part) for part in parts)
    return "job-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def city_of(text):
    text = clean(text).lower()
    for alias, city in ALIASES.items():
        if alias in text:
            return city
    return "Kalimantan Barat"


def parse_datetime(value):
    if not value:
        return None

    raw = clean(value)
    candidates = [
        raw,
        raw.replace("Z", "+00:00"),
        raw.replace(" UTC", "+00:00"),
    ]

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass

    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def extract_deadline(text):
    text = clean(text)
    if not text:
        return ""

    patterns = [
        r"Deadline\s*:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"Closing\s*Date\s*:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"Application\s+Deadline\s*:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


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
        "source_family": "Jobs Search",
        "posted_at": clean(detected.get("posted_at") or "Unknown"),
        "expires_at": "",
        "schedule_type": clean(detected.get("schedule_type")),
        "salary": clean(detected.get("salary")),
        "description": description[:500],
        "original_url": source_url or "#",
        "search_query": query,
        "extensions": [clean(x) for x in (item.get("extensions") or []) if clean(x)],
        "remote": bool(detected.get("work_from_home")),
        "status": "current",
    }


def fetch_google():
    if not SERPAPI_KEY:
        return [], {
            "status": "skipped",
            "count": 0,
            "message": "SERPAPI_KEY not configured",
        }

    jobs, errors = [], []
    used_queries = QUERIES[:max(1, MAX_GOOGLE_QUERIES)]

    for query in used_queries:
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
        "queries": used_queries,
        "errors": errors,
    }


def fetch_loker():
    jobs, errors = [], []

    for city in CITIES[:6]:
        try:
            response = requests.get(
                f"{BASE_URL}/cari-lowongan-kerja",
                params={"q": city},
                headers={"User-Agent": "Mozilla/5.0 (compatible; ketapangJOBS/2.1)"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.select("h2 a, h3 a, h4 a"):
                title = clean(anchor.get_text(" ", strip=True))
                href = clean(anchor.get("href"))
                url = urljoin(BASE_URL, href)

                if not title or not href:
                    continue
                if "lowongan-kerja" not in urlparse(url).path.lower():
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
                    "source_family": "Job Portal",
                    "posted_at": "Unknown",
                    "expires_at": "",
                    "schedule_type": "",
                    "salary": "",
                    "description": "Open the original source for qualification and company details.",
                    "original_url": url,
                    "search_query": f"loker {city}",
                    "extensions": [],
                    "remote": False,
                    "status": "current",
                })
        except Exception as exc:
            errors.append(f"{city}: {type(exc).__name__}: {exc}")

    return jobs, {
        "status": "ok" if jobs else ("error" if errors else "empty"),
        "count": len(jobs),
        "errors": errors,
    }


def reliefweb_fields(item):
    return item.get("fields") or {}


def normalize_reliefweb(item):
    fields = reliefweb_fields(item)

    source = fields.get("source") or {}
    country = fields.get("country") or {}
    city = fields.get("city") or {}
    experience = fields.get("experience") or {}
    job_type = fields.get("type") or {}

    source_name = clean(source.get("name") or source.get("shortname"))
    country_name = clean(country.get("name") or country.get("shortname"))
    city_name = clean(city.get("name"))
    closing_date = clean((fields.get("date") or {}).get("closing"))

    text = " ".join([
        clean(fields.get("title")),
        clean(fields.get("body")),
        city_name,
        country_name,
    ])
    district = city_of(text)

    return {
        "id": make_id("reliefweb", fields.get("id") or item.get("id"), fields.get("url")),
        "title": clean(fields.get("title")),
        "company": source_name or "ReliefWeb source",
        "location": city_name or country_name or district,
        "district": district,
        "province": "West Kalimantan",
        "country": country_name or "Indonesia",
        "via": "ReliefWeb",
        "source": "ReliefWeb",
        "source_family": "Humanitarian / UN ecosystem",
        "posted_at": clean((fields.get("date") or {}).get("created")),
        "expires_at": closing_date,
        "schedule_type": clean(job_type.get("name")),
        "salary": "",
        "description": clean(fields.get("body"))[:500],
        "original_url": clean(fields.get("url")),
        "search_query": "ReliefWeb jobs",
        "extensions": [clean(experience.get("name"))] if experience.get("name") else [],
        "remote": False,
        "status": clean(fields.get("status") or "current"),
        "o​cha": "ocha" in canon(source_name),
    }


def fetch_reliefweb():
    if not RELIEFWEB_APPNAME:
        return [], {
            "status": "skipped",
            "count": 0,
            "message": "RELIEFWEB_APPNAME not configured; request a pre-approved ReliefWeb appname first",
        }

    payload = {
        "limit": min(max(1, RELIEFWEB_LIMIT), 1000),
        "profile": "full",
        "sort": ["date.created:desc"],
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "status", "value": "current"},
                {"field": "country", "value": "Indonesia"},
            ],
        },
    }

    try:
        response = requests.post(
            RELIEFWEB_URL,
            params={"appname": RELIEFWEB_APPNAME},
            json=payload,
            headers={"User-Agent": "ketapangJOBS/2.1"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json().get("data") or []

        jobs = []
        for item in data:
            job = normalize_reliefweb(item)
            text = canon(
                f"{job.get('title')} {job.get('description')} "
                f"{job.get('location')} {job.get('district')}"
            )
            if any(canon(term) in text for term in CITIES):
                jobs.append(job)

        return jobs, {
            "status": "ok",
            "count": len(jobs),
            "api_results": len(data),
            "errors": [],
        }
    except Exception as exc:
        return [], {
            "status": "error",
            "count": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def text_from_xml(element):
    return clean(" ".join(element.itertext())) if element is not None else ""


def fetch_un_careers():
    try:
        response = requests.get(
            UN_RSS_URL,
            headers={"User-Agent": "ketapangJOBS/2.1"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)
        jobs = []

        for item in root.findall(".//item"):
            title = clean(text_from_xml(item.find("title")))
            link = clean(text_from_xml(item.find("link")))
            description = clean(text_from_xml(item.find("description")))
            guid = clean(text_from_xml(item.find("guid")))

            blob = f"{title} {description}"
            if not any(canon(term) in canon(blob) for term in INDONESIA_TERMS):
                continue

            deadline = extract_deadline(description)
            ocha = "office for the coordination of humanitarian affairs" in blob.lower() or re.search(r"\bocha\b", blob, re.I)

            jobs.append({
                "id": make_id("UN Careers", guid or link, title),
                "title": title,
                "company": "United Nations Secretariat",
                "location": city_of(blob),
                "district": city_of(blob),
                "province": "West Kalimantan" if city_of(blob) in CITIES else "",
                "country": "Indonesia",
                "via": "UN Careers",
                "source": "UN Careers",
                "source_family": "UN Secretariat",
                "posted_at": "",
                "expires_at": deadline,
                "schedule_type": "",
                "salary": "",
                "description": description[:500],
                "original_url": link or guid or "https://careers.un.org/job-openings",
                "search_query": "UN Careers RSS",
                "extensions": ["OCHA"] if ocha else [],
                "remote": False,
                "status": "current",
                "ocha": bool(ocha),
            })

        return jobs, {
            "status": "ok",
            "count": len(jobs),
            "feed": UN_RSS_URL,
            "errors": [],
        }
    except Exception as exc:
        return [], {
            "status": "error",
            "count": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def filter_expired(jobs):
    now = datetime.now(timezone.utc)
    active = []
    expired = 0

    for job in jobs:
        status = canon(job.get("status"))
        if status in {"past", "closed", "expired", "inactive"}:
            expired += 1
            continue

        expires_at = parse_datetime(job.get("expires_at"))
        if expires_at and expires_at <= now:
            expired += 1
            continue

        active.append(job)

    return active, expired


def dedupe(jobs):
    unique = {}

    for job in jobs:
        url = canon(job.get("original_url"))
        title = canon(job.get("title"))
        company = canon(job.get("company"))
        district = canon(job.get("district"))

        key = (
            f"url:{url}"
            if url and url != "#"
            else f"text:{title}|{company}|{district}"
        )

        if key not in unique:
            unique[key] = job

    return list(unique.values())


def summary(jobs):
    return {
        "by_district": dict(
            Counter(j.get("district", "Unknown") for j in jobs).most_common()
        ),
        "by_source": dict(
            Counter(j.get("source", "Unknown") for j in jobs).most_common()
        ),
        "ocha_jobs": sum(bool(j.get("ocha")) for j in jobs),
    }


def main():
    start = time.time()
    all_jobs = []
    sources = {}

    google, google_health = fetch_google()
    loker, loker_health = fetch_loker()
    reliefweb, reliefweb_health = fetch_reliefweb()
    un_careers, un_health = fetch_un_careers()

    all_jobs.extend(google)
    all_jobs.extend(loker)
    all_jobs.extend(reliefweb)
    all_jobs.extend(un_careers)

    sources["Google Jobs"] = google_health
    sources["Loker.id"] = loker_health
    sources["ReliefWeb"] = reliefweb_health
    sources["UN Careers"] = un_health

    unique_jobs = dedupe(all_jobs)
    active_jobs, expired_count = filter_expired(unique_jobs)

    errors = sum(
        (source.get("errors", []) for source in sources.values()),
        [],
    )

    output = {
        "schema_version": 3,
        "last_updated": datetime.now(timezone.utc).astimezone().strftime(
            "%Y-%m-%d %H:%M %Z"
        ),
        "total": len(active_jobs),
        "expired_removed": expired_count,
        "status": "ok" if active_jobs else ("error" if errors else "empty"),
        "region": "West Kalimantan, Indonesia",
        "coverage": CITIES,
        "external_links": {
            "reliefweb_jobs": "https://reliefweb.int/jobs",
            "un_careers": "https://careers.un.org/job-openings",
            "un_ocha_vacancies": "https://careers.un.org/job-openings",
        },
        "jobs": active_jobs,
        "summary": summary(active_jobs),
        "sources": sources,
        "errors": errors[:50],
        "runtime_seconds": round(time.time() - start, 2),
    }

    with open("vacancy.json", "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)

    with open("sources.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "buttons": [
                    {
                        "id": "reliefweb",
                        "label": "ReliefWeb Jobs",
                        "url": "https://reliefweb.int/jobs",
                    },
                    {
                        "id": "un-careers",
                        "label": "UN Careers",
                        "url": "https://careers.un.org/job-openings",
                    },
                    {
                        "id": "ocha",
                        "label": "UN OCHA Vacancies",
                        "url": "https://careers.un.org/job-openings",
                    },
                ]
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Collected {len(active_jobs)} active jobs; "
        f"expired removed={expired_count}; status={output['status']}."
    )


if __name__ == "__main__":
    main()
