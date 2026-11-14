# MyJOBS

**Indonesia-first job aggregator.**

MyJOBS brings together job opportunities from multiple sources into a lightweight, source-linked interface.

## Sources

- Google Jobs via SerpApi
- Loker.id
- Agent-Reach public web discovery (LinkedIn, JobStreet, Glints, Kalibrr, Dealls, KitaLulus and employer career pages)
- ReliefWeb Jobs API
- UN Careers RSS
- OCHA-related vacancies detected from UN / humanitarian sources

## Scope

The aggregator is **Indonesia-first**. Location detection in the frontend helps users filter the indexed dataset by area, but the scraper itself is no longer restricted to Ketapang or West Kalimantan.

## Expiry handling

Jobs are filtered out when the source provides an explicit expired/closed/past/inactive status or when an explicit closing date has passed.

For sources without an explicit closing date, MyJOBS removes a listing after **7 days** when a trustworthy `posted_at` date/age is available. Listings with no parseable date are retained rather than silently discarded.

MyJOBS does not invent deadlines for sources that do not provide one.

## Location UX

The landing page defaults to Indonesia and lets users:

- choose a location manually
- detect an approximate location using their internet connection/IP
- optionally use browser GPS after permission

Raw GPS coordinates are not written into the job dataset.

## Data contract

`vacancy.json` provides:

- `last_updated`
- `total`
- `region`
- `scope`
- `jobs`
- `summary`
- `sources`
- `expired_removed`
- `errors`

No fake vacancy is generated when a source fails.

## Roadmap

1. More Indonesian job sources and employer career pages.
2. Salary, skills, sector and employment-type normalization.
3. Better freshness and first-seen / last-seen tracking.
4. Nationwide location intelligence.
5. Global UN opportunities: UN Careers P-1 to P-7 and UNDP IPSA.
6. Optional ASEAN expansion after source, privacy and jurisdiction review.

## Source-specific adapters

MyJOBS treats each source as a separate adapter because data models, availability and application flows differ.

Agent-Reach is installed in GitHub Actions from the pinned official v1.6.1 GitHub release wheel (SHA-256 verified). The scheduled workflow uses its read-only public web search channel to discover candidate listing URLs from LinkedIn and selected Indonesian job portals, targeting up to 10 results per query (subject to provider availability and rate limits). It does not log in, use cookies, or access private LinkedIn content. Only allowlisted public job-detail URLs are normalized; full third-party job descriptions are not copied into the public dataset. Agent-Reach search failures are recorded in source health and do not stop the existing source adapters.

The local portal discovery is best-effort search-engine discovery, not a claim that each portal provides an official API or has granted bulk redistribution rights. MyJOBS retains source attribution and links applicants to the original listing. Portal-specific direct adapters should only be added after checking public access, terms and stable detail URLs.

UN Careers P-level ingestion first tries the public careers endpoints. If automated access is blocked, an optional Apify adapter can be enabled with the GitHub Actions secret APIFY_API_TOKEN. The adapter filters P-1 through P-7 only.

UNDP IPSA is parsed separately from the current UNDP vacancies page and keeps its own post-level, agency, location and apply-by metadata.


## Additional Indonesia-first sources

- **Karirhub Kemnaker:** public job-detail pages are discovered through search-engine indexing and parsed best-effort. No login, cookies or private endpoints are used; search indexing may be incomplete.
- **Public ATS boards:** Greenhouse, Lever, Ashby, SmartRecruiters, Workable and Recruitee boards are discovered by public search, then their unauthenticated public board endpoints are queried. Discovery is per employer and capped to reduce load.
- **Pasker ID:** official CSV/XLSX datasets are aggregate labour-market statistics, not individual vacancies. They are recorded as informational metadata and never converted into fake job records.
- **Freehire:** public reads are available without authentication, but its API documentation says redistribution/showing postings in a product requires an API plan. MyJOBS therefore does not ingest its listings until the appropriate licence is confirmed.
