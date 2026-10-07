import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
RELIEFWEB_APPNAME = os.getenv("RELIEFWEB_APPNAME", "").strip()
MAX_GOOGLE_QUERIES = int(os.getenv("MAX_GOOGLE_QUERIES", "8"))
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
RELIEFWEB_LIMIT = int(os.getenv("RELIEFWEB_LIMIT", "250"))
STALE_DAYS = int(os.getenv("STALE_DAYS", "7"))
BASE_URL = "https://www.loker.id"
RELIEFWEB_URL = "https://api.reliefweb.int/v2/jobs"
UN_RSS_URL = "https://careers.un.org/jobfeed?isPage=true&language=en"

INDONESIA_REGIONS = [
    "Aceh", "Bali", "Banten", "Bengkulu", "Gorontalo", "Jakarta",
    "Jambi", "Jawa Barat", "Jawa Tengah", "Jawa Timur", "Kalimantan Barat",
    "Kalimantan Selatan", "Kalimantan Tengah", "Kalimantan Timur",
    "Kalimantan Utara", "Kepulauan Bangka Belitung", "Kepulauan Riau",
    "Lampung", "Maluku", "Maluku Utara", "Nusa Tenggara Barat",
    "Nusa Tenggara Timur", "Papua", "Papua Barat", "Riau", "Sulawesi Barat",
    "Sulawesi Selatan", "Sulawesi Tengah", "Sulawesi Tenggara",
    "Sulawesi Utara", "Sumatera Barat", "Sumatera Selatan", "Sumatera Utara",
]

QUERIES = [
    "lowongan kerja Indonesia",
    "lowongan kerja Jakarta",
    "lowongan kerja Bandung",
    "lowongan kerja Surabaya",
    "lowongan kerja Bali",
    "lowongan kerja Kalimantan",
    "lowongan kerja Indonesia remote",
    "jobs Indonesia",
]

CITY_ALIASES = {
    "jakarta": "Jakarta",
    "bandung": "Bandung",
    "surabaya": "Surabaya",
    "semarang": "Semarang",
    "yogyakarta": "Yogyakarta",
    "medan": "Medan",
    "denpasar": "Denpasar",
    "makassar": "Makassar",
    "palembang": "Palembang",
    "pontianak": "Pontianak",
    "ketapang": "Ketapang",
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
    return "job-" + hashlib.sha1("|".join(canon(p) for p in parts).encode("utf-8")).hexdigest()[:16]

def infer_location(text):
    blob = clean(text).lower()
    for alias, city in CITY_ALIASES.items():
        if alias in blob:
            return city
    for region in INDONESIA_REGIONS:
        if region.lower() in blob:
            return region
    if any(term in blob for term in ("remote", "home based", "home-based")):
        return "Remote"
    if "global" in blob:
        return "Global"
    return "Indonesia"

def parse_datetime(value):
    if not value:
        return None
    raw = clean(value)
    for candidate in (raw, raw.replace("Z", "+00:00"), raw.replace(" UTC", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    relative = re.match(r"^(just posted|today|yesterday|(\d+)\+?\s+days?\s+ago)$", raw, flags=re.I)
    if relative:
        now = datetime.now(timezone.utc)
        value_lower = raw.lower()
        if value_lower in {"just posted", "today"}:
            return now
        if value_lower == "yesterday":
            return now - timedelta(days=1)
        return now - timedelta(days=int(relative.group(2)))

    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None

def extract_deadline(text):
    text = clean(text)
    for pattern in [
        r"Deadline\s*:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"Closing\s*Date\s*:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
        r"Application\s+Deadline\s*:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
    ]:
        match = re.search(pattern, text, flags=re.I)
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

    return {
        "id": make_id(title, company, location, source_url),
        "title": title,
        "company": company or "Unknown company",
        "location": location or "Indonesia",
        "district": infer_location(location or description),
        "province": infer_location(location or description),
        "country": "Indonesia",
        "via": clean(item.get("via") or "Google Jobs"),
        "source": "Google Jobs",
        "source_family": "Jobs Search",
        "posted_at": clean(detected.get("posted_at") or "Unknown"),
        "expires_at": "",
        "schedule_type": clean(detected.get("schedule_type")),
        "salary": clean(detected.get("salary")),
        "description": description[:600],
        "original_url": source_url or "#",
        "search_query": query,
        "extensions": [clean(x) for x in (item.get("extensions") or []) if clean(x)],
        "remote": bool(detected.get("work_from_home")),
        "status": "current",
        "country_code": "ID",
    }

def fetch_google():
    if not SERPAPI_KEY:
        return [], {"status": "skipped", "count": 0, "message": "SERPAPI_KEY not configured"}

    jobs, errors = [], []
    queries = QUERIES[:max(1, MAX_GOOGLE_QUERIES)]
    for query in queries:
        try:
            response = requests.get(
                "https://serpapi.com/search.json",
                params={"engine": "google_jobs", "q": query, "hl": "id", "gl": "id", "api_key": SERPAPI_KEY},
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

    return jobs, {"status": "ok" if jobs else ("error" if errors else "empty"), "count": len(jobs), "queries": queries, "errors": errors}

def fetch_loker():
    jobs, errors = [], []
    for query in ["Indonesia", "Jakarta", "Bandung", "Surabaya", "Kalimantan", "Bali"]:
        try:
            response = requests.get(
                f"{BASE_URL}/cari-lowongan-kerja",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; MyJOBS/1.0)"},
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
                location = query if query != "Indonesia" else "Indonesia"
                jobs.append({
                    "id": make_id("loker.id", title, url),
                    "title": title,
                    "company": "See source page",
                    "location": location,
                    "district": infer_location(f"{location} {title}"),
                    "province": infer_location(f"{location} {title}"),
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
                    "search_query": query,
                    "extensions": [],
                    "remote": False,
                    "status": "current",
                    "country_code": "ID",
                })
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {exc}")

    return jobs, {"status": "ok" if jobs else ("error" if errors else "empty"), "count": len(jobs), "errors": errors}

def normalize_reliefweb(item):
    fields = item.get("fields") or {}
    source = fields.get("source") or {}
    country = fields.get("country") or {}
    city = fields.get("city") or {}
    source_name = clean(source.get("name") or source.get("shortname"))
    country_name = clean(country.get("name") or country.get("shortname"))
    city_name = clean(city.get("name"))
    closing_date = clean((fields.get("date") or {}).get("closing"))
    blob = f"{fields.get('title','')} {fields.get('body','')} {city_name} {country_name}"

    return {
        "id": make_id("reliefweb", fields.get("id") or item.get("id"), fields.get("url")),
        "title": clean(fields.get("title")),
        "company": source_name or "ReliefWeb source",
        "location": city_name or country_name or "Indonesia",
        "district": infer_location(blob),
        "province": infer_location(blob),
        "country": country_name or "Indonesia",
        "via": "ReliefWeb",
        "source": "ReliefWeb",
        "source_family": "Humanitarian / UN ecosystem",
        "posted_at": clean((fields.get("date") or {}).get("created")),
        "expires_at": closing_date,
        "schedule_type": clean((fields.get("type") or {}).get("name")),
        "salary": "",
        "description": clean(fields.get("body"))[:600],
        "original_url": clean(fields.get("url")),
        "search_query": "ReliefWeb jobs",
        "extensions": [],
        "remote": False,
        "status": clean(fields.get("status") or "current"),
        "ocha": "ocha" in canon(source_name),
        "country_code": "ID" if country_name.lower() == "indonesia" else "",
    }

def fetch_reliefweb():
    if not RELIEFWEB_APPNAME:
        return [], {"status": "skipped", "count": 0, "message": "RELIEFWEB_APPNAME not configured"}

    payload = {
        "limit": min(max(1, RELIEFWEB_LIMIT), 1000),
        "profile": "full",
        "sort": ["date.created:desc"],
        "filter": {"operator": "AND", "conditions": [{"field": "status", "value": "current"}]},
    }

    try:
        response = requests.post(
            RELIEFWEB_URL,
            params={"appname": RELIEFWEB_APPNAME},
            json=payload,
            headers={"User-Agent": "MyJOBS/1.0"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json().get("data") or []
        jobs = [normalize_reliefweb(item) for item in data]
        return jobs, {"status": "ok", "count": len(jobs), "api_results": len(data), "errors": []}
    except Exception as exc:
        return [], {"status": "error", "count": 0, "errors": [f"{type(exc).__name__}: {exc}"]}

def xml_text(element):
    return clean(" ".join(element.itertext())) if element is not None else ""

def extract_un_field(text, label, next_labels):
    pattern = rf"{re.escape(label)}\s*:\s*(.+?)(?=\s+(?:{next_labels})\s*:|$)"
    match = re.search(pattern, text, flags=re.I)
    return clean(match.group(1)) if match else ""

def normalize_un_professional(item):
    if isinstance(item, dict):
        title = clean(item.get("title"))
        link = clean(item.get("link"))
        description = clean(item.get("description"))
        guid = clean(item.get("guid"))
    else:
        title = xml_text(item.find("title"))
        link = xml_text(item.find("link"))
        description = xml_text(item.find("description"))
        guid = xml_text(item.find("guid"))
    level_match = re.search(r"\bP-([1-7])\b", description, flags=re.I)
    level = f"P-{level_match.group(1)}" if level_match else ""
    duty_station = extract_un_field(description, "Duty Station", "Staffing Exercise|Date Posted|Deadline")
    posted = extract_un_field(description, "Date Posted", "Deadline|Job ID|Job Network")
    deadline = extract_un_field(description, "Deadline", "Job ID|Job Network|Job Family|Category")
    office = extract_un_field(description, "Department/Office", "Duty Station|Staffing Exercise|Date Posted|Deadline")
    network = extract_un_field(description, "Job Network", "Job Family|Category|Recruitment Type|Department/Office")
    family = extract_un_field(description, "Job Family", "Category|Recruitment Type|Department/Office")
    return {
        "id": make_id("UN P", guid or link, title),
        "title": title,
        "company": "United Nations Secretariat",
        "location": duty_station or "Global",
        "district": duty_station or "Global",
        "province": "",
        "country": "Global",
        "via": "UN Careers",
        "source": "UN Careers — P-level",
        "source_family": "UN Secretariat — Professional",
        "posted_at": posted,
        "expires_at": deadline,
        "schedule_type": level,
        "salary": "",
        "description": description[:700],
        "original_url": link or guid or "https://careers.un.org/job-openings",
        "search_query": "UN global P-level",
        "extensions": [x for x in [level, network, family, office] if x],
        "remote": "home-based" in description.lower(),
        "status": "current",
        "contract_level": level,
    }

def fetch_un_professional_global():
    try:
        response = requests.get(UN_RSS_URL, headers={"User-Agent": "MyJOBS/1.0"}, timeout=TIMEOUT)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        jobs = []
        for item in root.findall(".//item"):
            description = xml_text(item.find("description"))
            category_ok = "Professional and Higher Categories" in description
            level_ok = bool(re.search(r"\bP-[1-7]\b", description, flags=re.I))
            if not (category_ok and level_ok):
                continue
            jobs.append(normalize_un_professional(item))
        return jobs, {"status": "ok", "count": len(jobs), "feed": UN_RSS_URL, "filter": "P-1 through P-7 only", "errors": []}
    except Exception as exc:
        return [], {"status": "error", "count": 0, "errors": [f"{type(exc).__name__}: {exc}"]}

def fetch_un_careers():
    try:
        response = requests.get(UN_RSS_URL, headers={"User-Agent": "MyJOBS/1.0"}, timeout=TIMEOUT)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        jobs = []

        for item in root.findall(".//item"):
            title = xml_text(item.find("title"))
            link = xml_text(item.find("link"))
            description = xml_text(item.find("description"))
            guid = xml_text(item.find("guid"))
            blob = f"{title} {description}"
            if "indonesia" not in blob.lower() and not any(name.lower() in blob.lower() for name in CITY_ALIASES):
                continue

            deadline = extract_deadline(description)
            ocha = bool(re.search(r"\bocha\b|office for the coordination of humanitarian affairs", blob, flags=re.I))

            jobs.append({
                "id": make_id("UN Careers", guid or link, title),
                "title": title,
                "company": "United Nations Secretariat",
                "location": infer_location(blob),
                "district": infer_location(blob),
                "province": infer_location(blob),
                "country": "Indonesia",
                "via": "UN Careers",
                "source": "UN Careers",
                "source_family": "UN Secretariat",
                "posted_at": "",
                "expires_at": deadline,
                "schedule_type": "",
                "salary": "",
                "description": description[:600],
                "original_url": link or guid or "https://careers.un.org/job-openings",
                "search_query": "UN Careers RSS",
                "extensions": ["OCHA"] if ocha else [],
                "remote": False,
                "status": "current",
                "ocha": ocha,
                "country_code": "ID",
            })

        return jobs, {"status": "ok", "count": len(jobs), "feed": UN_RSS_URL, "errors": []}
    except Exception as exc:
        return [], {"status": "error", "count": 0, "errors": [f"{type(exc).__name__}: {exc}"]}

UNDP_URL = "https://jobs.undp.org/cj_view_jobs.cfm?cur_categ_id=100"

def parse_undp_job_anchor(anchor):
    title_text = clean(anchor.get_text(" ", strip=True))
    href = urljoin("https://jobs.undp.org/", clean(anchor.get("href")))
    level = re.search(r"\b(IPSA-\d+)\b", title_text, flags=re.I)
    if not level:
        return None
    apply_by = re.search(r"Apply by\s+([A-Z][a-z]{2}-\d{1,2}-\d{2})", title_text, flags=re.I)
    agency = re.search(r"Agency\s+(.+?)\s+Location\s+", title_text, flags=re.I)
    location = re.search(r"Location\s+(.+)$", title_text, flags=re.I)
    job_title = re.sub(r"^Job Title\s*", "", title_text, flags=re.I)
    job_title = re.split(r"\s+Post level\s+", job_title, flags=re.I)[0]
    return {
        "id": make_id("UNDP IPSA", href, job_title),
        "title": job_title,
        "company": clean(agency.group(1)) if agency else "UNDP",
        "location": clean(location.group(1)) if location else "Global",
        "district": clean(location.group(1)) if location else "Global",
        "province": "",
        "country": "Global",
        "via": "UNDP Careers",
        "source": "UNDP — IPSA",
        "source_family": "UN Development Programme — International",
        "posted_at": "",
        "expires_at": clean(apply_by.group(1)) if apply_by else "",
        "schedule_type": clean(level.group(1)).upper(),
        "salary": "",
        "description": title_text[:700],
        "original_url": href,
        "search_query": "UNDP IPSA global",
        "extensions": [clean(level.group(1)).upper()],
        "remote": "home based" in title_text.lower(),
        "status": "current",
        "contract_level": clean(level.group(1)).upper(),
    }

def fetch_undp_ipsa_global():
    try:
        response = requests.get(UNDP_URL, headers={"User-Agent": "MyJOBS/1.0"}, timeout=TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        jobs = []
        for anchor in soup.select('a[href*="cj_view_job.cfm"]'):
            job = parse_undp_job_anchor(anchor)
            if job:
                jobs.append(job)
        unique = dedupe(jobs)
        return unique, {"status": "ok" if unique else "empty", "count": len(unique), "url": UNDP_URL, "filter": "IPSA only", "errors": []}
    except Exception as exc:
        return [], {"status": "error", "count": 0, "errors": [f"{type(exc).__name__}: {exc}"]}

def filter_expired(jobs):
    now = datetime.now(timezone.utc)
    active, expired, stale = [], 0, 0

    for job in jobs:
        status = canon(job.get("status"))
        if status in {"past", "closed", "expired", "inactive"}:
            expired += 1
            continue

        expires_at = parse_datetime(job.get("expires_at"))
        if expires_at and expires_at <= now:
            expired += 1
            continue

        # Sources without a closing date get a seven-day stale cleanup
        # only when they provide a parseable posted_at value.
        if not job.get("expires_at"):
            posted_at = parse_datetime(job.get("posted_at"))
            if posted_at and (now - posted_at).days >= STALE_DAYS:
                stale += 1
                continue

        active.append(job)

    return active, expired, stale

def dedupe(jobs):
    unique = {}
    for job in jobs:
        url = canon(job.get("original_url"))
        title = canon(job.get("title"))
        key = f"url:{url}" if url and url != "#" else f"text:{title}|{canon(job.get('company'))}|{canon(job.get('location'))}"
        if key not in unique:
            unique[key] = job
    return list(unique.values())

def summary(jobs):
    return {
        "by_location": dict(Counter(j.get("district", "Indonesia") for j in jobs).most_common()),
        "by_source": dict(Counter(j.get("source", "Unknown") for j in jobs).most_common()),
        "humanitarian_jobs": sum("humanitarian" in canon(j.get("source_family")) or j.get("source") == "ReliefWeb" for j in jobs),
        "un_jobs": sum(str(j.get("source", "")).startswith("UN Careers") for j in jobs),
        "un_p_jobs": sum(j.get("source") == "UN Careers — P-level" for j in jobs),
        "undp_ipsa_jobs": sum(j.get("source") == "UNDP — IPSA" for j in jobs),
    }

def main():
    started = time.time()
    all_jobs, sources = [], {}

    for fetcher, name in [
        (fetch_google, "Google Jobs"),
        (fetch_loker, "Loker.id"),
        (fetch_reliefweb, "ReliefWeb"),
        (fetch_un_professional_global, "UN Careers — P-level"),
        (fetch_undp_ipsa_global, "UNDP — IPSA"),
        (fetch_un_careers, "UN Careers — Indonesia"),
    ]:
        jobs, health = fetcher()
        all_jobs.extend(jobs)
        sources[name] = health

    unique_jobs = dedupe(all_jobs)
    active_jobs, expired_count, stale_count = filter_expired(unique_jobs)
    errors = sum((s.get("errors", []) for s in sources.values()), [])

    output = {
        "schema_version": 4,
        "last_updated": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "total": len(active_jobs),
        "expired_removed": expired_count,
        "stale_removed": stale_count,
        "stale_days": STALE_DAYS,
        "status": "ok" if active_jobs else ("error" if errors else "empty"),
        "region": "Indonesia",
        "scope": "Indonesia-first job aggregator",
        "jobs": active_jobs,
        "summary": summary(active_jobs),
        "sources": sources,
        "errors": errors[:50],
        "runtime_seconds": round(time.time() - started, 2),
    }

    with open("vacancy.json", "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)

    print(f"MyJOBS: {len(active_jobs)} active jobs; expired removed={expired_count}; stale removed={stale_count}; status={output['status']}")

if __name__ == "__main__":
    main()
