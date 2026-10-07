# MyJOBS

**Indonesia-first job aggregator.**

MyJOBS brings together job opportunities from multiple sources into a lightweight, source-linked interface.

## Sources

- Google Jobs via SerpApi
- Loker.id
- ReliefWeb Jobs API
- UN Careers RSS
- OCHA-related vacancies detected from UN / humanitarian sources

## Scope

The aggregator is **Indonesia-first**. Location detection in the frontend helps users filter the indexed dataset by area, but the scraper itself is no longer restricted to Ketapang or West Kalimantan.

## Expiry handling

Jobs are filtered out when the source provides an explicit expired/closed/past/inactive status or when an explicit closing date has passed.

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
5. Optional ASEAN expansion after source, privacy and jurisdiction review.
