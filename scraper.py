import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
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
TOPLOKER_LIST_URLS = [
    value.strip()
    for value in os.getenv(
        "TOPLOKER_LIST_URLS",
        "https://toploker.com/loker/daftar,https://toploker.com/loker/aktif-merekrut"
    ).split(",")
    if value.strip()
]
TOPLOKER_MAX_LIST_PAGES = int(os.getenv("TOPLOKER_MAX_LIST_PAGES", "4"))
TOPLOKER_MAX_JOBS = int(os.getenv("TOPLOKER_MAX_JOBS", "60"))
BASE_URL = "https://www.loker.id"
TOPLOKER_BASE = "https://toploker.com"
TOPLOKER_LIST_URL = f"{TOPLOKER_BASE}/loker/daftar"
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

def fetch_public_text(url, headers=None, jina_fallback=False, jina_first=False):
    headers = headers or {"User-Agent": "Mozilla/5.0 (compatible; MyJOBS/1.0)"}

    def via_jina():
        # Jina's HTTPS reader handles JS-heavy pages more reliably than the
        # HTTP-origin form for Oracle Candidate Experience and TopLoker.
        proxy = "https://r.jina.ai/" + url
        proxy_response = requests.get(
            proxy,
            headers={"User-Agent": "MyJOBS/1.0"},
            timeout=max(TIMEOUT, 30),
        )
        proxy_response.raise_for_status()
        return proxy_response.text

    if jina_first:
        try:
            text = via_jina()
            if text.strip():
                return text, True
        except Exception:
            pass

    response = requests.get(url, headers=headers, timeout=max(TIMEOUT, 30))
    if response.status_code < 400:
        if response.text.strip():
            return response.text, False
        if jina_fallback:
            return via_jina(), True
        return response.text, False

    if not jina_fallback:
        response.raise_for_status()

    return via_jina(), True


def search_bing_links(query, url_pattern):
    try:
        response = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "count": 50, "setlang": "en-US"},
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MyJOBS/1.0)",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=max(TIMEOUT, 30),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        found = []
        for anchor in soup.select("li.b_algo h2 a, h2 a"):
            href = clean(anchor.get("href"))
            if href and re.search(url_pattern, href, flags=re.I):
                found.append(href)
        return list(dict.fromkeys(found))
    except Exception:
        return []


def search_bing_results(query, url_pattern):
    try:
        response = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "count": 50, "setlang": "en-US"},
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MyJOBS/1.0)",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=max(TIMEOUT, 30),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for item in soup.select("li.b_algo"):
            anchor = item.select_one("h2 a")
            if not anchor:
                continue
            href = clean(anchor.get("href"))
            if not href or not re.search(url_pattern, href, flags=re.I):
                continue
            title = clean(anchor.get_text(" ", strip=True))
            caption = item.select_one(".b_caption")
            snippet = clean(caption.get_text(" ", strip=True)) if caption else clean(item.get_text(" ", strip=True))
            results.append({"url": href, "title": title, "snippet": snippet})
        return results
    except Exception:
        return []




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
    ind_months = {"januari":1,"februari":2,"maret":3,"april":4,"mei":5,"juni":6,"juli":7,"agustus":8,"september":9,"oktober":10,"november":11,"desember":12}
    month_match = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", raw, flags=re.I)
    if month_match and month_match.group(2).lower() in ind_months:
        return datetime(
            int(month_match.group(3)),
            ind_months[month_match.group(2).lower()],
            int(month_match.group(1)),
            tzinfo=timezone.utc,
        )

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


def normalize_toploker(item):
    title = clean(item.get("title"))
    company = clean(item.get("company")) or "TopLoker employer"
    location = clean(item.get("location"))
    location = re.sub(r"\s*\*\s*\*\s*\*\s*$", "", location).strip()
    posted_at = clean(item.get("posted_at"))
    expires_at = clean(item.get("expires_at"))
    description = clean(item.get("description"))
    requirements = clean(item.get("requirements"))
    status_type = clean(item.get("schedule_type"))
    url = clean(item.get("url"))

    full_description = "\n\n".join(
        part for part in [description, requirements] if part
    )

    return {
        "id": make_id("TopLoker", title, company, location, url),
        "title": title,
        "company": company,
        "location": location or "Indonesia",
        "district": clean(location) or infer_location(location or title, fallback=""),
        "province": infer_province(location or title),
        "country": "Indonesia",
        "via": "TopLoker",
        "source": "TopLoker",
        "source_family": "Job Portal — Indonesia",
        "posted_at": posted_at or "Unknown",
        "expires_at": expires_at,
        "schedule_type": status_type,
        "salary": clean(item.get("salary")),
        "description": full_description or "Open the original source for full job details.",
        "original_url": url or "#",
        "search_query": "TopLoker",
        "extensions": [clean(x) for x in (item.get("extensions") or []) if clean(x)],
        "remote": "remote" in canon(location) or "remote" in canon(full_description),
        "status": "current",
        "country_code": "ID",
        "details": make_source_details(
            "TopLoker",
            education=clean(item.get("education")),
            schedule=status_type,
            deadline=expires_at,
            location=location,
        ),
    }


def parse_toploker_detail(html, url):
    soup = BeautifulSoup(html, "html.parser")
    lines = [clean(x) for x in soup.get_text("\n", strip=True).splitlines() if clean(x)]

    def next_nonempty(start_index):
        for idx in range(start_index + 1, min(len(lines), start_index + 8)):
            value = clean(lines[idx])
            if value and value not in {":", "-", "—"}:
                return value
        return ""

    company = ""
    title = ""
    marker = next((idx for idx, value in enumerate(lines) if canon(value) == "membuka lowongan"), -1)
    if marker >= 0:
        title = next_nonempty(marker)
        if marker > 0:
            company = clean(lines[marker - 1])
    if not title:
        h1 = soup.find("h1")
        title = clean(h1.get_text(" ", strip=True)) if h1 else ""

    text_blob = " ".join(lines)
    deadline_match = re.search(
        r"Batas\s+Lamaran\s*:?\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})",
        text_blob,
        flags=re.I,
    )
    location_match = re.search(
        r"Lokasi\s+Kerja\s*:?\s*(.+?)(?=\s+Deskripsi\s+Pekerjaan\b)",
        text_blob,
        flags=re.I,
    )
    if not location_match:
        location_match = re.search(
            r"(?:ditempatkan|penempatan)\s+di\s+(.+?)(?=\.|\s+dan\s+bersedia\b|\s+serta\b|$)",
            text_blob,
            flags=re.I,
        )
    schedule_match = re.search(
        r"Status\s+Kerja\s*:?\s*(.+?)(?=\s+Batas\s+Lamaran\b)",
        text_blob,
        flags=re.I,
    )

    def section_between(start_label, end_label):
        try:
            start = next(i for i, value in enumerate(lines) if canon(value) == canon(start_label))
        except StopIteration:
            return ""
        try:
            end = next(i for i in range(start + 1, len(lines)) if canon(lines[i]) == canon(end_label))
        except StopIteration:
            end = len(lines)
        return clean(" ".join(lines[start + 1:end]))

    description = section_between("Deskripsi Pekerjaan", "Syarat Pekerjaan")
    requirements = section_between("Syarat Pekerjaan", "Kirim Lamaran")

    posted = ""
    date_match = re.match(r"https?://[^/]+/lowongan/(\d{4}-\d{2}-\d{2})!", url)
    if date_match:
        posted = date_match.group(1)

    return normalize_toploker({
        "title": title,
        "company": company,
        "location": clean(location_match.group(1)) if location_match else "",
        "posted_at": posted,
        "expires_at": clean(deadline_match.group(1)) if deadline_match else "",
        "description": description,
        "requirements": requirements,
        "schedule_type": clean(schedule_match.group(1)) if schedule_match else "",
        "url": url,
    })


def fetch_toploker():
    errors = []
    detail_urls = []
    seen_urls = set()
    seen_pages = set()
    sample_page_text = ""
    page_queue = list(TOPLOKER_LIST_URLS)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MyJOBS/1.0)"}

    while page_queue and len(seen_pages) < TOPLOKER_MAX_LIST_PAGES:
        page = page_queue.pop(0)
        if page in seen_pages:
            continue
        seen_pages.add(page)

        try:
            text, proxied = fetch_public_text(page, headers=headers, jina_fallback=True, jina_first=True)
            if not sample_page_text:
                sample_page_text = clean(text[:600])
            soup = BeautifulSoup(text, "html.parser")

            for href in re.findall(
                r'https?://toploker\.com/lowongan/[^)\s]+',
                text,
                flags=re.I,
            ):
                job_url = href.replace("%21", "!")
                if "/lowongan/" in urlparse(job_url).path and job_url not in seen_urls:
                    seen_urls.add(job_url)
                    detail_urls.append(job_url)

            for href in re.findall(
                r'/lowongan/20\d{2}-\d{2}-\d{2}![^)\s)]+',
                text,
                flags=re.I,
            ):
                job_url = urljoin(TOPLOKER_BASE, href).replace("%21", "!")
                if "/lowongan/" in urlparse(job_url).path and job_url not in seen_urls:
                    seen_urls.add(job_url)
                    detail_urls.append(job_url)

            for anchor in soup.select('a[href*="/lowongan/"]'):
                href = clean(anchor.get("href"))
                if not href:
                    continue
                job_url = urljoin(TOPLOKER_BASE, href).split("#", 1)[0].replace("%21", "!")
                if "/lowongan/" in urlparse(job_url).path and job_url not in seen_urls:
                    seen_urls.add(job_url)
                    detail_urls.append(job_url)
                if len(detail_urls) >= TOPLOKER_MAX_JOBS:
                    break

            # TopLoker's pagination uses paths such as /loker/daftar/7764,
            # rather than numeric offsets. Discover the next few pages dynamically.
            for anchor in soup.select('a[href*="/loker/daftar/"], a[href*="/loker/aktif-merekrut/"]'):
                href = clean(anchor.get("href"))
                if not href:
                    continue
                next_page = urljoin(TOPLOKER_BASE, href).split("#", 1)[0]
                if next_page not in seen_pages and next_page not in page_queue:
                    page_queue.append(next_page)
                if len(page_queue) + len(seen_pages) >= TOPLOKER_MAX_LIST_PAGES:
                    break

        except Exception as exc:
            errors.append(
                f"{page}: {type(exc).__name__}: {exc}"
            )

        if len(detail_urls) >= TOPLOKER_MAX_JOBS:
            break

    if not detail_urls:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        bing_queries = [
            f'site:toploker.com/lowongan/ "{today}"',
            f'site:toploker.com/lowongan/ "{datetime.now(timezone.utc).year}"',
        ]
        for query in bing_queries:
            for job_url in search_bing_links(
                query,
                r"toploker\.com/lowongan/",
            ):
                if job_url not in seen_urls:
                    seen_urls.add(job_url)
                    detail_urls.append(job_url)
                if len(detail_urls) >= TOPLOKER_MAX_JOBS:
                    break
            if detail_urls or len(detail_urls) >= TOPLOKER_MAX_JOBS:
                break

    def fetch_detail(job_url):
        try:
            text, _ = fetch_public_text(
                job_url,
                headers=headers,
                jina_fallback=True,
                jina_first=True,
            )
            return parse_toploker_detail(text, job_url), None
        except Exception as exc:
            return None, f"{job_url}: {type(exc).__name__}: {exc}"

    jobs = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(fetch_detail, job_url)
            for job_url in detail_urls
        ]
        for future in as_completed(futures):
            job, error = future.result()
            if error:
                errors.append(error)
            elif job and job.get("title"):
                jobs.append(job)

    jobs = dedupe(jobs)
    return jobs, {
        "status": "ok" if jobs else ("error" if errors else "empty"),
        "count": len(jobs),
        "list_urls": TOPLOKER_LIST_URLS,
        "pages_crawled": list(seen_pages),
        "proxy_fallback": True,
        "discovered_urls": len(detail_urls),
        "sample_page_text": sample_page_text,
        "errors": errors[:25],
    }

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
    title = clean(item.get("title") or item.get("Title") or item.get("name"))
    description = clean(
        item.get("descriptionText")
        or item.get("shortDescription")
        or item.get("ExternalDescriptionStr")
        or item.get("ExternalDescription")
    )
    req_id = clean(
        item.get("requisitionId")
        or item.get("RequisitionId")
        or item.get("SearchId")
        or item.get("Id")
    )
    url = clean(item.get("url") or item.get("ExternalUrl") or item.get("ExternalUrlSeo"))
    location = clean(
        item.get("primaryLocation")
        or item.get("PrimaryLocation")
        or item.get("WorkLocation")
    )
    country_code = clean(
        item.get("primaryLocationCountry")
        or item.get("PrimaryLocationCountry")
    )
    posting_date = clean(
        item.get("postingDate")
        or item.get("PostedDate")
        or item.get("ExternalPostedStartDate")
        or item.get("PostedDateStr")
    )
    closing_date = clean(
        item.get("postingEndDate")
        or item.get("ExternalPostedEndDate")
        or item.get("PostingEndDate")
    )
    salary_text = clean(item.get("salaryText") or item.get("SalaryText"))
    qualifications = clean(
        item.get("qualificationsText")
        or item.get("ExternalQualificationsStr")
    )
    responsibilities = clean(
        item.get("responsibilitiesText")
        or item.get("ExternalResponsibilitiesStr")
    )

    level_blob = " ".join(
        clean(item.get(key))
        for key in (
            "JobGrade",
            "JobLevel",
            "CategoryAndLevel",
            "categoryAndLevel",
            "contractLevel",
            "title",
            "Title",
            "descriptionText",
            "ExternalDescriptionStr",
        )
        if clean(item.get(key))
    )
    level_match = re.search(r"\b(IPSA-\d+)\b", level_blob, flags=re.I)
    if not level_match:
        return None

    level = level_match.group(1).upper()
    full_description = "\n\n".join(
        x for x in [description, qualifications, responsibilities] if x
    )
    job_url = url or (
        f"{UNDP_ORACLE_BASE}/hcmUI/CandidateExperience/en/sites/"
        f"{UNDP_ORACLE_SITE}/job/{req_id}"
    )

    return {
        "id": make_id("UNDP IPSA", req_id or job_url, title),
        "title": title,
        "company": clean(
            item.get("employer")
            or item.get("EmployerName")
            or item.get("LegalEmployer")
            or "UNDP"
        ),
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
        "description": full_description or "Open the original UNDP source for full job details.",
        "original_url": job_url or "https://jobs.undp.org/",
        "search_query": "UNDP IPSA",
        "extensions": [
            level,
            clean(item.get("JobType") or item.get("jobType")),
            clean(item.get("JobSchedule") or item.get("jobSchedule")),
            clean(item.get("WorkerType") or item.get("workerType")),
            clean(item.get("WorkplaceType") or item.get("workplaceType")),
        ],
        "remote": (
            clean(item.get("WorkplaceType") or item.get("workplaceType")).lower() == "remote"
            or "home-based" in full_description.lower()
            or "home based" in full_description.lower()
        ),
        "status": "current",
        "contract_level": level,
        "details": make_source_details(
            "UNDP Careers",
            requisition_id=req_id,
            post_level=level,
            job_level=clean(item.get("JobLevel")),
            job_grade=clean(item.get("JobGrade")),
            job_type=clean(item.get("JobType") or item.get("jobType")),
            schedule=clean(item.get("JobSchedule") or item.get("jobSchedule")),
            worker_type=clean(item.get("WorkerType") or item.get("workerType")),
            workplace_type=clean(item.get("WorkplaceType") or item.get("workplaceType")),
            primary_location=location,
            country_code=country_code,
            organization=clean(item.get("Organization") or item.get("DepartmentName")),
            job_function=clean(item.get("JobFunction") or item.get("Function")),
            study_level=clean(item.get("StudyLevel")),
            number_of_openings=clean(item.get("NumberOfOpenings")),
            international_travel=clean(item.get("InternationalTravelRequired")),
            posted=posting_date,
            deadline=closing_date,
            external_url=clean(item.get("ExternalUrl") or item.get("ExternalUrlSeo")),
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

def normalize_undp_bing_result(item):
    title = clean(item.get("title"))
    snippet = clean(item.get("snippet"))
    url = clean(item.get("url"))
    blob = " ".join([title, snippet])

    grade_match = re.search(r"\b(IPSA-\d+)\b", blob, flags=re.I)
    if not grade_match:
        return None

    level = grade_match.group(1).upper()

    posting_match = re.search(
        r"Posting\s+Date\s+(\d{1,2}/\d{1,2}/\d{4},\s+\d{1,2}:\d{2}\s+[AP]M)",
        blob,
        flags=re.I,
    )
    deadline_match = re.search(
        r"Apply\s+Before\s+(\d{1,2}/\d{1,2}/\d{4},\s+\d{1,2}:\d{2}\s+[AP]M)",
        blob,
        flags=re.I,
    )
    location_match = re.search(
        r"^(?:[^,]+\s+)?([A-Z][A-Za-zÀ-ÖØ-öø-ÿ .'-]+,\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ .'-]+)\s+(?:Be the First to Apply|Job Info)",
        snippet,
        flags=re.I,
    )
    if not location_match:
        location_match = re.search(
            r"([A-Z][A-Za-zÀ-ÖØ-öø-ÿ .'-]+,\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ .'-]+)\s+Be the First",
            snippet,
            flags=re.I,
        )

    location = clean(location_match.group(1)) if location_match else ""
    location = re.sub(r"\s+Be the First.*$", "", location, flags=re.I).strip()
    clean_title = re.sub(r"\s*[|–—-]\s*UNDP Careers.*$", "", title, flags=re.I)
    clean_title = re.sub(r"\s*[|–—-]\s*UNDP.*$", "", clean_title, flags=re.I)
    clean_title = clean(clean_title)

    posting = posting_match.group(1) if posting_match else ""
    deadline = deadline_match.group(1) if deadline_match else ""

    return normalize_undp_oracle({
        "Id": clean((re.search(r"/job/(\d+)", url) or [None, ""])[1]),
        "Title": clean_title,
        "EmployerName": "UNDP",
        "PrimaryLocation": location,
        "PostedDate": posting,
        "ExternalPostedEndDate": deadline,
        "JobGrade": level,
        "ExternalDescriptionStr": snippet,
        "ExternalUrl": url,
    })


def fetch_undp_ipsa_bing():
    queries = [
        'site:estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/ "Grade IPSA-" "UNDP Careers"',
        'site:estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/ "Apply Before" "IPSA-"',
        'site:estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/ "Posting Date" "IPSA-"',
    ]
    results = []
    seen = set()

    for query in queries:
        for item in search_bing_results(
            query,
            r"estm\.fa\.em2\.oraclecloud\.com/hcmUI/CandidateExperience/en/sites/CX_1/job/\d+",
        ):
            url = clean(item.get("url"))
            if url and url not in seen:
                seen.add(url)
                results.append(item)

    jobs = []
    for item in results[:50]:
        job = normalize_undp_bing_result(item)
        if job:
            jobs.append(job)

    jobs = dedupe(jobs)
    return jobs, {
        "status": "ok" if jobs else "empty",
        "count": len(jobs),
        "queries": queries,
        "discovered_results": len(results),
        "errors": [],
    }


def parse_unvacancies_undp_card(anchor):
    title = clean(anchor.get_text(" ", strip=True))
    href = clean(anchor.get("href"))
    if not title or not href:
        return None

    context = clean(anchor.parent.get_text(" ", strip=True)) if anchor.parent else ""
    if anchor.parent and anchor.parent.parent:
        context = clean(
            f"{context} {anchor.parent.parent.get_text(' ', strip=True)}"
        )

    grade_match = re.search(r"\b(IPSA-\d+)\b", context, flags=re.I)
    if not grade_match:
        return None

    grade = grade_match.group(1).upper()

    location_match = re.search(
        r"UNDP\s*[·|]\s*(.+?)(?=\s+UNDP Tiers\b|\s+Nationals\b|\s+Locally recruited\b|\s+Closes\b|\s+Posted\b|$)",
        context,
        flags=re.I,
    )
    location = clean(location_match.group(1)) if location_match else ""

    deadline_match = re.search(
        r"Closes(?:\s+in\s+\d+\s+days?:)?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        context,
        flags=re.I,
    )
    deadline = deadline_match.group(1) if deadline_match else ""

    ref_match = re.search(r"-DP-(\d{4,6})", href, flags=re.I)
    requisition_id = ref_match.group(1) if ref_match else ""

    official_url = (
        f"{UNDP_ORACLE_BASE}/hcmUI/CandidateExperience/en/sites/"
        f"{UNDP_ORACLE_SITE}/job/{requisition_id}"
        if requisition_id else href
    )

    return normalize_undp_oracle({
        "Id": requisition_id,
        "Title": title,
        "EmployerName": "UNDP",
        "PrimaryLocation": location,
        "PostedDate": "",
        "ExternalPostedEndDate": deadline,
        "JobGrade": grade,
        "ExternalDescriptionStr": context,
        "ExternalUrl": official_url,
    })


def parse_unvacancies_undp_detail(html, source_url):
    soup = BeautifulSoup(html, "html.parser")
    lines = [clean(x) for x in soup.get_text("\n", strip=True).splitlines() if clean(x)]
    blob = " ".join(lines)

    grade_match = re.search(r"\b(IPSA-\d+)\b", blob, flags=re.I)
    if not grade_match:
        return None

    grade = grade_match.group(1).upper()
    heading = soup.find("h1")
    title = clean(heading.get_text(" ", strip=True)) if heading else ""

    location_match = re.search(
        r"UNDP\s*[·|]\s*(.+?)(?=\s+Posted\b|\s+Grade\b|\s+IPSA-\d+\b)",
        blob,
        flags=re.I,
    )
    location = clean(location_match.group(1)) if location_match else ""

    posted_match = re.search(
        r"Posted\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        blob,
        flags=re.I,
    )
    closed_match = re.search(
        r"(?:Closes|Close)\s+(?:in\s+\d+\s+days?:\s*)?(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        blob,
        flags=re.I,
    )

    official_url = ""
    for anchor in soup.select("a[href]"):
        href = clean(anchor.get("href"))
        if re.search(
            r"(?:estm\.fa\.em2\.oraclecloud\.com/hcmUI/|jobs\.undp\.org/)",
            href,
            flags=re.I,
        ):
            official_url = href
            break

    ref_match = re.search(r"(?:-DP-|/job/)(\d{4,6})", source_url, flags=re.I)
    requisition_id = ref_match.group(1) if ref_match else ""

    if not official_url and requisition_id:
        official_url = (
            f"{UNDP_ORACLE_BASE}/hcmUI/CandidateExperience/en/sites/"
            f"{UNDP_ORACLE_SITE}/job/{requisition_id}"
        )

    try:
        desc_start = next(
            i for i, line in enumerate(lines)
            if canon(line) in {"about this role", "job description", "description"}
        )
        description = clean(" ".join(lines[desc_start + 1:desc_start + 80]))
    except StopIteration:
        description = clean(blob[:6000])

    return normalize_undp_oracle({
        "Id": requisition_id,
        "Title": title,
        "EmployerName": "UNDP",
        "PrimaryLocation": location,
        "PostedDate": posted_match.group(1) if posted_match else "",
        "ExternalPostedEndDate": closed_match.group(1) if closed_match else "",
        "JobGrade": grade,
        "ExternalDescriptionStr": description[:6000],
        "ExternalUrl": official_url or source_url,
    })


def fetch_undp_ipsa_unvacancies():
    errors = []
    jobs = []
    detail_urls = set()
    page_urls = [
        "https://unvacancies.org/explore?organization=UNDP&q=IPSA",
        "https://unvacancies.org/explore?organization=UNDP&query=IPSA",
        "https://unvacancies.org/explore?organization=UNDP&keyword=IPSA",
        "https://unvacancies.org/explore?organization=UNDP&contract=International%20PSA",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MyJOBS/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    for page_url in page_urls:
        try:
            text, _ = fetch_public_text(
                page_url,
                headers=headers,
                jina_fallback=True,
                jina_first=False,
            )
            soup = BeautifulSoup(text, "html.parser")

            for anchor in soup.select('a[href*="/jobs/"]'):
                job = parse_unvacancies_undp_card(anchor)
                if job:
                    jobs.append(job)
                    href = clean(anchor.get("href"))
                    if href:
                        detail_urls.add(urljoin("https://unvacancies.org", href))
        except Exception as exc:
            errors.append(f"{page_url}: {type(exc).__name__}: {exc}")

    unique = dedupe(jobs)
    return unique, {
        "status": "ok" if unique else ("error" if errors else "empty"),
        "count": len(unique),
        "queries": page_urls,
        "card_jobs": len(jobs),
        "detail_urls": len(detail_urls),
        "errors": errors[:25],
        "source": "unvacancies.org (UNDP official application links)",
    }



def load_historical_source_jobs(source_name, max_commits=20):
    try:
        log = subprocess.run(
            ["git", "log", "--format=%H", "--", "vacancy.json"],
            capture_output=True,
            text=True,
            check=True,
        )
        for commit in log.stdout.splitlines()[:max_commits]:
            try:
                raw = subprocess.run(
                    ["git", "show", f"{commit}:vacancy.json"],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                payload = json.loads(raw)
                jobs = [
                    job for job in (payload.get("jobs") or [])
                    if job.get("source") == source_name
                ]
                if jobs:
                    return jobs
            except Exception:
                continue
    except Exception:
        pass
    return []


def load_previous_jobs():
    try:
        with open("vacancy.json", "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload.get("jobs") or []
    except Exception:
        return []

def carry_forward_source_jobs(all_jobs, previous_jobs, source_name):
    if any(job.get("source") == source_name for job in all_jobs):
        return 0
    retained = [
        job for job in (previous_jobs or [])
        if job.get("source") == source_name
    ]
    if retained:
        all_jobs.extend(retained)
        return len(retained)

    historical = load_historical_source_jobs(source_name)
    all_jobs.extend(historical)
    return len(historical)


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
    previous_jobs = load_previous_jobs()

    for fetcher, name in [
        (fetch_google, "Google Jobs"),
        (fetch_loker, "Loker.id"),
        (fetch_toploker, "TopLoker"),
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

    # UNDP IPSA: use Bing-indexed official Oracle job pages first. This is a
    # resilient fallback when Oracle's public REST endpoint is empty from CI.
    undp_bing_jobs, undp_bing_health = fetch_undp_ipsa_bing()
    all_jobs.extend(undp_bing_jobs)
    sources["UNDP — IPSA / Bing Oracle"] = undp_bing_health

    # UNDP IPSA: use the stable unvacancies live index, which links
    # each listing back to the official UNDP application page.
    undp_mirror_jobs, undp_mirror_health = fetch_undp_ipsa_unvacancies()
    all_jobs.extend(undp_mirror_jobs)
    sources["UNDP — IPSA / unvacancies"] = undp_mirror_health

    if not any(job.get("source") == "UNDP — IPSA" for job in all_jobs) and APIFY_API_TOKEN:
        undp_api_jobs, undp_api_health = fetch_undp_ipsa_apify()
        all_jobs.extend(undp_api_jobs)
        sources["UNDP — IPSA / Apify Oracle"] = undp_api_health

    for protected_source in ("UNDP — IPSA", "UN Careers — P-level"):
        if not any(job.get("source") == protected_source for job in all_jobs):
            retained = carry_forward_source_jobs(
                all_jobs,
                previous_jobs,
                protected_source,
            )
            if retained:
                sources[f"{protected_source} / carry-forward"] = {
                    "status": "carry-forward",
                    "count": retained,
                    "message": "Kept the last known jobs while the live source was unavailable.",
                }


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
