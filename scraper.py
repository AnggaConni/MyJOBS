import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
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
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "").strip()
APIFY_UNCAREERS_ACTOR = os.getenv("APIFY_UNCAREERS_ACTOR", "nomad-agent/un-careers-scraper").strip()
APIFY_UNDP_ACTOR = os.getenv("APIFY_UNDP_ACTOR", "maydit/oracle-recruiting-jobs-scraper").strip()
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

INDONESIA_QUERIES = [
    {"q": "lowongan kerja Indonesia", "gl": "id", "country": "Indonesia"},
    {"q": "lowongan kerja Jakarta", "gl": "id", "country": "Indonesia"},
    {"q": "lowongan kerja Bandung", "gl": "id", "country": "Indonesia"},
    {"q": "lowongan kerja Surabaya", "gl": "id", "country": "Indonesia"},
    {"q": "lowongan kerja Bali", "gl": "id", "country": "Indonesia"},
    {"q": "lowongan kerja Kalimantan", "gl": "id", "country": "Indonesia"},
    {"q": "lowongan kerja Ketapang", "gl": "id", "country": "Indonesia"},
    {"q": "lowongan kerja Pontianak", "gl": "id", "country": "Indonesia"},
]

ASEAN_COUNTRIES = [
    {"country": "Brunei Darussalam", "code": "BN", "q": "jobs Brunei"},
    {"country": "Cambodia", "code": "KH", "q": "jobs Cambodia"},
    {"country": "Indonesia", "code": "ID", "q": "jobs Indonesia"},
    {"country": "Lao PDR", "code": "LA", "q": "jobs Laos"},
    {"country": "Malaysia", "code": "MY", "q": "jobs Malaysia"},
    {"country": "Myanmar", "code": "MM", "q": "jobs Myanmar"},
    {"country": "Philippines", "code": "PH", "q": "jobs Philippines"},
    {"country": "Singapore", "code": "SG", "q": "jobs Singapore"},
    {"country": "Thailand", "code": "TH", "q": "jobs Thailand"},
    {"country": "Timor-Leste", "code": "TL", "q": "jobs Timor-Leste"},
    {"country": "Viet Nam", "code": "VN", "q": "jobs Vietnam"},
]

INDONESIA_PROVINCE_BY_CITY = {
    "jakarta": "DKI Jakarta",
    "bandung": "Jawa Barat",
    "semarang": "Jawa Tengah",
    "yogyakarta": "DI Yogyakarta",
    "surabaya": "Jawa Timur",
    "medan": "Sumatera Utara",
    "palembang": "Sumatera Selatan",
    "denpasar": "Bali",
    "makassar": "Sulawesi Selatan",
    "pontianak": "Kalimantan Barat",
    "ketapang": "Kalimantan Barat",
    "singkawang": "Kalimantan Barat",
    "kubu raya": "Kalimantan Barat",
    "sintang": "Kalimantan Barat",
    "sambas": "Kalimantan Barat",
    "sanggau": "Kalimantan Barat",
    "sekadau": "Kalimantan Barat",
    "melawi": "Kalimantan Barat",
    "landak": "Kalimantan Barat",
    "bengkayang": "Kalimantan Barat",
    "kapuas hulu": "Kalimantan Barat",
    "mempawah": "Kalimantan Barat",
    "balikpapan": "Kalimantan Timur",
    "banjarmasin": "Kalimantan Selatan"
}

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

def infer_location(text, fallback="Indonesia"):
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
    return fallback or "Indonesia"

def infer_country(text, explicit=""):
    explicit = clean(explicit)
    if explicit:
        return explicit
    blob = clean(text).lower()
    if "indonesia" in blob:
        return "Indonesia"
    for city in CITY_ALIASES:
        if city in blob:
            return "Indonesia"
    for province in INDONESIA_REGIONS:
        if province.lower() in blob:
            return "Indonesia"
    return "Global"

def infer_province(text, explicit=""):
    explicit = clean(explicit)
    if explicit:
        return explicit
    blob = clean(text).lower()
    for city, province in INDONESIA_PROVINCE_BY_CITY.items():
        if city in blob:
            return province
    for province in INDONESIA_REGIONS:
        if province.lower() in blob:
            return province
    return ""

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

    for fmt in ("%b-%d-%y", "%b-%d-%Y", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

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

def make_source_details(source, **kwargs):
    details = {"source": source}
    for key, value in kwargs.items():
        if value not in (None, "", [], {}):
            details[key] = value
    return details

def normalize_google(item, query, market_country="Indonesia"):
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
        "district": infer_location(location or description, fallback=""),
        "province": infer_province(location or description),
        "country": infer_country(location or description, explicit=market_country),
        "market": "ASEAN" if any(m["country"] == market_country for m in ASEAN_COUNTRIES) else "Indonesia",
        "region": "ASEAN" if any(m["country"] == market_country for m in ASEAN_COUNTRIES) else "Indonesia",
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
        "country_code": next((m["code"] for m in ASEAN_COUNTRIES if m["country"] == market_country), "ID"),
        "details": make_source_details(
            "Google Jobs",
            via=clean(item.get("via")),
            posted_at=clean(detected.get("posted_at")),
            schedule_type=clean(detected.get("schedule_type")),
            salary=clean(detected.get("salary")),
            extensions=[clean(x) for x in (item.get("extensions") or []) if clean(x)],
        ),
    }

def fetch_google():
    if not SERPAPI_KEY:
        return [], {"status": "skipped", "count": 0, "message": "SERPAPI_KEY not configured"}

    query_specs = INDONESIA_QUERIES + ASEAN_COUNTRIES
    queries = []
    for item in query_specs:
        queries.append({
            "q": item["q"],
            "gl": item["gl"] if "gl" in item else item["code"].lower(),
            "country": item["country"],
        })

    queries = queries[:max(1, MAX_GOOGLE_QUERIES)]
    jobs, errors, by_country = [], [], Counter()

    for spec in queries:
        query = spec["q"]
        market_country = spec["country"]
        try:
            response = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_jobs",
                    "q": query,
                    "hl": "id" if market_country == "Indonesia" else "en",
                    "gl": spec["gl"],
                    "api_key": SERPAPI_KEY,
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                errors.append(f"{query}: {payload['error']}")
                continue

            count = 0
            for item in payload.get("jobs_results") or []:
                job = normalize_google(item, query, market_country=market_country)
                if job["title"]:
                    jobs.append(job)
                    count += 1
            by_country[market_country] += count
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {exc}")

    return jobs, {
        "status": "ok" if jobs else ("error" if errors else "empty"),
        "count": len(jobs),
        "queries": [x["q"] for x in queries],
        "markets": [x["country"] for x in queries],
        "by_country": dict(by_country),
        "errors": errors,
    }

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
                    "district": infer_location(f"{location} {title}", fallback=""),
                    "province": infer_province(f"{location} {title}"),
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

def first_reliefweb_value(value):
    if isinstance(value, list):
        return value[0] if value else {}
    return value or {}

def normalize_reliefweb(item):
    fields = item.get("fields") or {}
    source = first_reliefweb_value(fields.get("source"))
    country = first_reliefweb_value(fields.get("country"))
    city = first_reliefweb_value(fields.get("city"))
    source_name = clean(source.get("name") or source.get("shortname"))
    country_name = clean(country.get("name") or country.get("shortname"))
    city_name = clean(city.get("name"))
    date_info = first_reliefweb_value(fields.get("date"))
    job_type = first_reliefweb_value(fields.get("type"))
    closing_date = clean(date_info.get("closing"))
    created_date = clean(date_info.get("created"))
    blob = f"{fields.get('title','')} {fields.get('body','')} {city_name} {country_name}"
    state_info = first_reliefweb_value(fields.get("state") or fields.get("admin1") or fields.get("region") or fields.get("province"))
    state_name = clean(state_info.get("name"))
    country_final = infer_country(blob, explicit=country_name)
    location_fallback = country_final
    district_name = city_name or infer_location(blob, fallback="")
    province_name = infer_province(blob, explicit=state_name)
    return {
        "id": make_id("reliefweb", fields.get("id") or item.get("id"), fields.get("url")),
        "title": clean(fields.get("title")),
        "company": source_name or "ReliefWeb source",
        "location": city_name or country_name or "Indonesia",
        "district": district_name,
        "province": province_name,
        "country": country_final,
        "via": "ReliefWeb",
        "source": "ReliefWeb",
        "source_family": "Humanitarian / UN ecosystem",
        "posted_at": created_date,
        "expires_at": closing_date,
        "schedule_type": clean(job_type.get("name")),
        "salary": "",
        "description": clean(fields.get("body")),
        "details": make_source_details(
            "ReliefWeb",
            organization=source_name,
            country=country_name,
            city=city_name,
            type=clean(job_type.get("name")),
            experience=clean(first_reliefweb_value(fields.get("experience")).get("name")),
            date_created=created_date,
            date_closing=closing_date,
        ),
        "original_url": clean(fields.get("url")),
        "search_query": "ReliefWeb jobs",
        "extensions": [],
        "remote": False,
        "status": clean(fields.get("status") or "current"),
        "ocha": "ocha" in canon(source_name),
        "country_code": "ID" if country_final == "Indonesia" else "",
    }

def fetch_reliefweb():
    if not RELIEFWEB_APPNAME:
        return [], {"status": "skipped", "count": 0, "message": "RELIEFWEB_APPNAME not configured"}

    payload = {
        "limit": min(max(1, RELIEFWEB_LIMIT), 1000),
        "profile": "full",
        "sort": ["date.created:desc"],
        "filter": {"operator": "AND", "conditions": [{"field": "status", "value": "published"}]},
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
        jobs = []
        excluded = 0
        excluded_types = {"Tender/RFPs/EOIs", "Tender", "RFP", "EOI"}
        for item in data:
            job = normalize_reliefweb(item)
            if job.get("schedule_type") in excluded_types:
                excluded += 1
                continue
            jobs.append(job)

        return jobs, {
            "status": "ok",
            "count": len(jobs),
            "api_results": len(data),
            "excluded_non_job": excluded,
            "errors": [],
        }
    except Exception as exc:
        return [], {"status": "error", "count": 0, "errors": [f"{type(exc).__name__}: {exc}"]}

def xml_text(element):
    return clean(" ".join(element.itertext())) if element is not None else ""

def extract_un_field(text, label, next_labels):
    pattern = rf"{re.escape(label)}\s*:\s*(.+?)(?=\s+(?:{next_labels})\s*:|$)"
    match = re.search(pattern, text, flags=re.I)
    return clean(match.group(1)) if match else ""

def parse_key_value_fields(text):
    text = clean(text)
    fields = {}
    labels = [
        "Job ID", "Job Network", "Job Family", "Category and Level",
        "Recruitment Type", "Duty Station", "Department/Office",
        "Date Posted", "Deadline", "Post level", "Apply by", "Agency",
        "Location", "Country", "City", "Experience", "Type"
    ]
    for index, label in enumerate(labels):
        next_labels = "|".join(re.escape(x) for x in labels[index + 1:])
        if next_labels:
            pattern = rf"{re.escape(label)}\s*:\s*(.+?)\s+(?:{next_labels})\s*:|{re.escape(label)}\s*:\s*(.+)$"
        else:
            pattern = rf"{re.escape(label)}\s*:\s*(.+)$"
        match = re.search(pattern, text, flags=re.I)
        if match:
            value = match.group(1) or (match.group(2) if match.lastindex and match.lastindex >= 2 else "")
            fields[label] = clean(value)
    return fields

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
    fields = parse_key_value_fields(description)
    level_match = re.search(r"\bP-([1-7])\b", description, flags=re.I)
    level = f"P-{level_match.group(1)}" if level_match else clean(fields.get("Category and Level"))
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
        "description": description,
        "details": make_source_details(
            "UN Careers",
            job_id=fields.get("Job ID"),
            job_network=fields.get("Job Network"),
            job_family=fields.get("Job Family"),
            category_level=fields.get("Category and Level"),
            recruitment_type=fields.get("Recruitment Type"),
            duty_station=fields.get("Duty Station"),
            department_office=fields.get("Department/Office"),
            date_posted=fields.get("Date Posted"),
            deadline=fields.get("Deadline"),
            level=level,
        ),
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
        message = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, requests.HTTPError) and getattr(exc.response, "status_code", None) in {401, 403, 404}:
            return [], {"status": "skipped", "count": 0, "message": "UN Careers feed is not accessible to automated requests", "errors": [message]}
        if isinstance(exc, ET.ParseError):
            return [], {"status": "skipped", "count": 0, "message": "UN Careers feed no longer returns parseable XML from this endpoint", "errors": [message]}
        return [], {"status": "error", "count": 0, "errors": [message]}

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
        message = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, requests.HTTPError) and getattr(exc.response, "status_code", None) in {401, 403, 404}:
            return [], {"status": "skipped", "count": 0, "message": "UN Careers feed is not accessible to automated requests", "errors": [message]}
        if isinstance(exc, ET.ParseError):
            return [], {"status": "skipped", "count": 0, "message": "UN Careers feed no longer returns parseable XML from this endpoint", "errors": [message]}
        return [], {"status": "error", "count": 0, "errors": [message]}

UNDP_URL = "https://jobs.undp.org/cj_view_jobs.cfm?cur_categ_id=100"

def parse_undp_job_anchor(anchor):
    direct = clean(anchor.get_text(" ", strip=True))
    parent = clean(anchor.parent.get_text(" ", strip=True)) if anchor.parent else ""
    grand = clean(anchor.parent.parent.get_text(" ", strip=True)) if anchor.parent and anchor.parent.parent else ""
    title_text = max([direct, parent, grand], key=len)
    href = urljoin("https://jobs.undp.org/", clean(anchor.get("href")))

    level_match = re.search(r"\b(IPSA-\d+)\b", title_text, flags=re.I)
    if not level_match:
        return None

    apply_match = re.search(r"Apply by\s+([A-Z][a-z]{2}-\d{1,2}-\d{2})", title_text, flags=re.I)
    agency_match = re.search(r"Agency\s+(.+?)\s+Location\s+", title_text, flags=re.I)
    location_match = re.search(r"Location\s+(.+?)(?:\s*$)", title_text, flags=re.I)

    level = clean(level_match.group(1)).upper()
    apply_by = clean(apply_match.group(1)) if apply_match else ""
    agency = clean(agency_match.group(1)) if agency_match else "UNDP"
    location = clean(location_match.group(1)) if location_match else "Global"

    job_title = re.sub(r"^Job Title\s*", "", direct or title_text, flags=re.I)
    job_title = re.split(r"\s+Post level\s+", job_title, flags=re.I)[0]
    job_title = clean(job_title)

    return {
        "id": make_id("UNDP IPSA", href or job_title, job_title),
        "title": job_title,
        "company": agency,
        "location": location,
        "district": location,
        "province": "",
        "country": infer_country(location, explicit=""),
        "via": "UNDP Careers",
        "source": "UNDP — IPSA",
        "source_family": "UN Development Programme — International",
        "posted_at": "",
        "expires_at": apply_by,
        "schedule_type": level,
        "salary": "",
        "description": title_text,
        "original_url": href,
        "search_query": "UNDP IPSA global",
        "extensions": [level],
        "remote": "home based" in title_text.lower() or "home-based" in title_text.lower(),
        "status": "current",
        "contract_level": level,
        "details": make_source_details(
            "UNDP Careers",
            post_level=level,
            apply_by=apply_by,
            agency=agency,
            location=location,
        ),
    }


def fetch_undp_ipsa_global():
    try:
        response = requests.get(
            UNDP_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MyJOBS/1.0)"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        jobs = []

        for anchor in soup.select("a[href]"):
            job = parse_undp_job_anchor(anchor)
            if job:
                jobs.append(job)

        unique = dedupe(jobs)
        return unique, {
            "status": "ok" if unique else "empty",
            "count": len(unique),
            "url": UNDP_URL,
            "filter": "IPSA only",
            "errors": [],
        }
    except Exception as exc:
        return [], {
            "status": "error",
            "count": 0,
            "url": UNDP_URL,
            "filter": "IPSA only",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def normalize_un_apify(item):
    title = clean(item.get("title") or item.get("jobTitle") or item.get("name"))
    link = clean(item.get("url") or item.get("applyUrl") or item.get("jobUrl"))
    description = clean(item.get("description") or item.get("jobDescription") or item.get("summary"))
    level = clean(item.get("level") or item.get("categoryAndLevel") or item.get("grade"))
    match = re.search(r"\bP-([1-7])\b", f"{level} {description}", flags=re.I)
    if not match:
        return None

    level = f"P-{match.group(1)}"
    duty = clean(item.get("dutyStation") or item.get("location"))
    deadline = clean(item.get("deadline") or item.get("closingDate"))
    posted = clean(item.get("datePosted") or item.get("publishedAt"))
    job_id = clean(item.get("jobId") or item.get("id"))
    network = clean(item.get("jobNetwork"))
    family = clean(item.get("jobFamily"))
    category = clean(item.get("category") or item.get("categoryAndLevel"))
    recruitment = clean(item.get("recruitmentType"))
    office = clean(item.get("departmentOffice") or item.get("department"))

    return {
        "id": make_id("UN P", job_id or link or title, title),
        "title": title,
        "company": "United Nations Secretariat",
        "location": duty or "Global",
        "district": duty or "Global",
        "province": "",
        "country": "Global",
        "via": "UN Careers",
        "source": "UN Careers — P-level",
        "source_family": "UN Secretariat — Professional",
        "posted_at": posted,
        "expires_at": deadline,
        "schedule_type": level,
        "salary": "",
        "description": description,
        "original_url": link or "https://careers.un.org/job-opening",
        "search_query": "UN global P-level",
        "extensions": [x for x in [level, network, family, category, recruitment, office] if x],
        "remote": "home-based" in f"{duty} {description}".lower(),
        "status": "current",
        "contract_level": level,
        "details": make_source_details(
            "UN Careers",
            job_id=job_id,
            job_network=network,
            job_family=family,
            category_level=category,
            recruitment_type=recruitment,
            duty_station=duty,
            department_office=office,
            date_posted=posted,
            deadline=deadline,
            level=level,
        ),
    }

def fetch_un_professional_apify():
    if not APIFY_API_TOKEN:
        return [], {
            "status": "skipped",
            "count": 0,
            "message": "APIFY_API_TOKEN not configured",
            "actor": APIFY_UNCAREERS_ACTOR,
        }

    url = (
        "https://api.apify.com/v2/acts/"
        + APIFY_UNCAREERS_ACTOR.replace("/", "~")
        + "/run-sync-get-dataset-items"
    )

    try:
        response = requests.post(
            url,
            params={"token": APIFY_API_TOKEN},
            json={"maxItems": 150, "includeDescription": True, "sortDirection": "newest"},
            headers={"User-Agent": "MyJOBS/1.0"},
            timeout=max(TIMEOUT, 60),
        )
        response.raise_for_status()
        data = response.json()
        jobs = []
        for item in data if isinstance(data, list) else []:
            job = normalize_un_apify(item)
            if job:
                jobs.append(job)

        unique = dedupe(jobs)
        return unique, {
            "status": "ok" if unique else "empty",
            "count": len(unique),
            "actor": APIFY_UNCAREERS_ACTOR,
            "filter": "P-1 through P-7 only",
            "errors": [],
        }
    except Exception as exc:
        return [], {
            "status": "error",
            "count": 0,
            "actor": APIFY_UNCAREERS_ACTOR,
            "filter": "P-1 through P-7 only",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }

def normalize_undp_oracle(item):
    title = clean(item.get("title"))
    description = clean(item.get("descriptionText") or item.get("shortDescription"))
    req_id = clean(item.get("requisitionId"))
    url = clean(item.get("url"))
    location = clean(item.get("primaryLocation"))
    country_code = clean(item.get("primaryLocationCountry"))
    posting_date = clean(item.get("postingDate"))
    closing_date = clean(item.get("postingEndDate"))
    salary_text = clean(item.get("salaryText"))
    qualifications = clean(item.get("qualificationsText"))
    responsibilities = clean(item.get("responsibilitiesText"))

    level_match = re.search(r"\b(IPSA-\d+)\b", f"{title} {description}", flags=re.I)
    if not level_match:
        return None

    level = level_match.group(1).upper()
    full_description = "\n\n".join(
        x for x in [description, qualifications, responsibilities] if x
    )

    return {
        "id": make_id("UNDP IPSA", req_id or url, title),
        "title": title,
        "company": clean(item.get("employer") or "UNDP"),
        "location": location or "Global",
        "district": infer_location(location, fallback=""),
        "province": infer_province(location),
        "country": infer_country(location, explicit=""),
        "via": "UNDP Careers",
        "source": "UNDP — IPSA",
        "source_family": "UN Development Programme — International",
        "posted_at": posting_date,
        "expires_at": closing_date,
        "schedule_type": level,
        "salary": salary_text,
        "description": full_description,
        "original_url": url or "https://jobs.undp.org/",
        "search_query": "UNDP IPSA",
        "extensions": [
            level,
            clean(item.get("category")),
            clean(item.get("jobFunction")),
            clean(item.get("jobSchedule")),
            clean(item.get("workplaceType")),
        ],
        "remote": (
            clean(item.get("workplaceType")).lower() == "remote"
            or "home-based" in full_description.lower()
            or "home based" in full_description.lower()
        ),
        "status": "current",
        "contract_level": level,
        "details": make_source_details(
            "UNDP Careers",
            requisition_id=req_id,
            post_level=level,
            category=clean(item.get("category")),
            job_function=clean(item.get("jobFunction")),
            schedule=clean(item.get("jobSchedule")),
            workplace=clean(item.get("workplaceType")),
            primary_location=location,
            country_code=country_code,
            secondary_locations=item.get("secondaryLocations") or [],
            posting_date=posting_date,
            closing_date=closing_date,
            salary=salary_text,
            detail_fetched=item.get("detailFetched"),
        ),
    }

UNDP_ORACLE_BASE = "https://estm.fa.em2.oraclecloud.com"
UNDP_ORACLE_SITE = "CX_1"

def first_json_item(payload):
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list) and items:
            return items[0]
        return payload
    if isinstance(payload, list) and payload:
        return payload[0]
    return {}

def fetch_undp_oracle_detail(requisition_id):
    finder = f'ById;Id="{requisition_id}",siteNumber={UNDP_ORACLE_SITE}'
    url = f"{UNDP_ORACLE_BASE}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
    params = {"onlyData": "true", "expand": "all", "finder": finder}
    response = requests.get(
        url,
        params=params,
        headers={
            "User-Agent": "MyJOBS/1.0",
            "Accept": "application/json",
            "Ora-Irc-Language": "en",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return first_json_item(response.json())

def fetch_undp_ipsa_oracle_public():
    jobs = []
    errors = []
    seen = set()
    offset = 0
    page_size = 100
    max_pages = 5

    list_url = f"{UNDP_ORACLE_BASE}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

    try:
        for _ in range(max_pages):
            finder = (
                f"findReqs;siteNumber={UNDP_ORACLE_SITE},"
                "facetsList=LOCATIONS;WORK_LOCATIONS;TITLES;CATEGORIES;"
                "ORGANIZATIONS;POSTING_DATES"
            )
            response = requests.get(
                list_url,
                params={
                    "onlyData": "true",
                    "expand": "requisitionList.secondaryLocations",
                    "finder": finder,
                    "limit": page_size,
                    "offset": offset,
                },
                headers={
                    "User-Agent": "MyJOBS/1.0",
                    "Accept": "application/json",
                    "Ora-Irc-Language": "en",
                    "Referer": f"{UNDP_ORACLE_BASE}/hcmUI/CandidateExperience/en/sites/{UNDP_ORACLE_SITE}/jobs",
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()

            requisitions = []
            for item in payload.get("items", []) if isinstance(payload, dict) else []:
                nested = item.get("requisitionList")
                if isinstance(nested, list):
                    requisitions.extend(nested)
                elif isinstance(item, dict) and item.get("Id"):
                    requisitions.append(item)

            if not requisitions:
                break

            ids = []
            for item in requisitions:
                rid = clean(item.get("Id") or item.get("RequisitionId") or item.get("requisitionId"))
                if rid and rid not in seen:
                    seen.add(rid)
                    ids.append(rid)

            def get_detail(rid):
                try:
                    return rid, fetch_undp_oracle_detail(rid), None
                except Exception as exc:
                    return rid, None, f"{rid}: {type(exc).__name__}: {exc}"

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(get_detail, rid) for rid in ids]
                for future in as_completed(futures):
                    rid, detail, err = future.result()
                    if err:
                        errors.append(err)
                        continue
                    if not detail:
                        continue

                    level = clean(detail.get("JobGrade") or detail.get("JobLevel"))
                    level_match = re.search(r"\b(IPSA-\d+)\b", level, flags=re.I)
                    if not level_match:
                        level_match = re.search(
                            r"\b(IPSA-\d+)\b",
                            f"{detail.get('Title','')} {detail.get('ExternalDescriptionStr','')}",
                            flags=re.I,
                        )
                    if not level_match:
                        continue

                    level = level_match.group(1).upper()
                    title = clean(detail.get("Title"))
                    location = clean(detail.get("PrimaryLocation") or detail.get("WorkLocation"))
                    country_code = clean(detail.get("PrimaryLocationCountry"))
                    description = clean(
                        detail.get("ExternalDescriptionStr")
                        or detail.get("ExternalDescription")
                        or ""
                    )
                    qualifications = clean(detail.get("ExternalQualificationsStr"))
                    responsibilities = clean(detail.get("ExternalResponsibilitiesStr"))
                    full_description = "\n\n".join(
                        x for x in [description, qualifications, responsibilities] if x
                    )
                    rid_final = clean(detail.get("RequisitionId") or detail.get("Id") or rid)

                    job_url = (
                        f"{UNDP_ORACLE_BASE}/hcmUI/CandidateExperience/en/sites/"
                        f"{UNDP_ORACLE_SITE}/job/{rid_final}"
                    )

                    job = {
                        "id": make_id("UNDP IPSA", rid_final, title),
                        "title": title,
                        "company": clean(detail.get("LegalEmployer") or "UNDP"),
                        "location": location or "Global",
                        "district": infer_location(location, fallback=""),
                        "province": infer_province(location),
                        "country": infer_country(location, explicit=""),
                        "via": "UNDP Careers",
                        "source": "UNDP — IPSA",
                        "source_family": "UN Development Programme — International",
                        "posted_at": clean(
                            detail.get("ExternalPostedStartDate")
                            or detail.get("PostedDate")
                            or detail.get("postingDate")
                        ),
                        "expires_at": clean(
                            detail.get("ExternalPostedEndDate")
                            or detail.get("PostingEndDate")
                            or detail.get("postingEndDate")
                        ),
                        "schedule_type": level,
                        "salary": "",
                        "description": full_description,
                        "original_url": job_url,
                        "search_query": "UNDP IPSA",
                        "extensions": [
                            level,
                            clean(detail.get("JobType")),
                            clean(detail.get("JobSchedule")),
                            clean(detail.get("WorkerType")),
                            clean(detail.get("WorkplaceType")),
                        ],
                        "remote": clean(detail.get("WorkplaceType")).lower() == "remote"
                            or "home-based" in full_description.lower()
                            or "home based" in full_description.lower(),
                        "status": "current",
                        "contract_level": level,
                        "details": make_source_details(
                            "UNDP Careers",
                            requisition_id=rid_final,
                            post_level=level,
                            job_level=clean(detail.get("JobLevel")),
                            job_grade=clean(detail.get("JobGrade")),
                            job_type=clean(detail.get("JobType")),
                            job_schedule=clean(detail.get("JobSchedule")),
                            worker_type=clean(detail.get("WorkerType")),
                            workplace_type=clean(detail.get("WorkplaceType")),
                            primary_location=location,
                            country_code=country_code,
                            organization=clean(detail.get("Organization")),
                            job_function=clean(detail.get("JobFunction")),
                            study_level=clean(detail.get("StudyLevel")),
                            number_of_openings=clean(detail.get("NumberOfOpenings")),
                            international_travel=clean(detail.get("InternationalTravelRequired")),
                            posted=clean(detail.get("ExternalPostedStartDate")),
                            deadline=clean(detail.get("ExternalPostedEndDate")),
                        ),
                    }
                    jobs.append(job)

            has_more = bool(payload.get("hasMore")) if isinstance(payload, dict) else False
            if not has_more:
                break
            offset += page_size

        unique = dedupe(jobs)
        return unique, {
            "status": "ok" if unique else "empty",
            "count": len(unique),
            "endpoint": list_url,
            "filter": "IPSA only",
            "site": UNDP_ORACLE_SITE,
            "errors": errors[:25],
        }
    except Exception as exc:
        return [], {
            "status": "error",
            "count": 0,
            "endpoint": list_url,
            "filter": "IPSA only",
            "errors": errors[:20] + [f"{type(exc).__name__}: {exc}"],
        }

def fetch_undp_ipsa_apify():
    if not APIFY_API_TOKEN:
        return [], {
            "status": "skipped",
            "count": 0,
            "message": "APIFY_API_TOKEN not configured",
            "actor": APIFY_UNDP_ACTOR,
            "filter": "IPSA only",
        }

    url = (
        "https://api.apify.com/v2/acts/"
        + APIFY_UNDP_ACTOR.replace("/", "~")
        + "/run-sync-get-dataset-items"
    )
    careers_url = "https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions"

    try:
        response = requests.post(
            url,
            params={"token": APIFY_API_TOKEN},
            json={
                "careersUrls": [careers_url],
                "maxJobsPerSite": 500,
                "includeDetails": True,
                "keyword": "IPSA",
                "sortBy": "POSTING_DATES_DESC",
                "maxRunSeconds": 240,
            },
            headers={"User-Agent": "MyJOBS/1.0"},
            timeout=max(TIMEOUT, 90),
        )
        response.raise_for_status()
        data = response.json()
        jobs = []

        for item in data if isinstance(data, list) else []:
            job = normalize_undp_oracle(item)
            if job:
                jobs.append(job)

        unique = dedupe(jobs)
        return unique, {
            "status": "ok" if unique else "empty",
            "count": len(unique),
            "actor": APIFY_UNDP_ACTOR,
            "filter": "IPSA only",
            "errors": [],
        }
    except Exception as exc:
        return [], {
            "status": "error",
            "count": 0,
            "actor": APIFY_UNDP_ACTOR,
            "filter": "IPSA only",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }

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

    # If direct UN Careers access is blocked, use the optional Apify adapter.
    if not any(job.get("source") == "UN Careers — P-level" for job in all_jobs) and APIFY_API_TOKEN:
        un_api_jobs, un_api_health = fetch_un_professional_apify()
        all_jobs.extend(un_api_jobs)
        sources["UN Careers — P-level / Apify"] = un_api_health

    # UNDP current vacancies are served from Oracle Recruiting Cloud.
    # Use the dedicated Oracle adapter when direct HTML extraction returns no IPSA jobs.
    undp_public_jobs, undp_public_health = fetch_undp_ipsa_oracle_public()
    all_jobs.extend(undp_public_jobs)
    sources["UNDP — IPSA / Oracle public JSON"] = undp_public_health

    if not any(job.get("source") == "UNDP — IPSA" for job in all_jobs) and APIFY_API_TOKEN:
        undp_api_jobs, undp_api_health = fetch_undp_ipsa_apify()
        all_jobs.extend(undp_api_jobs)
        sources["UNDP — IPSA / Apify Oracle"] = undp_api_health

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
        "region": "Indonesia + ASEAN",
        "scope": "Indonesia-first with Phase 2 ASEAN job discovery",
        "asean_members": [x["country"] for x in ASEAN_COUNTRIES],
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
