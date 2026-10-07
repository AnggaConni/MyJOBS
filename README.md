# ketapangJOBS

Local Job Aggregator & Labour-Market Radar for West Kalimantan, Indonesia.

The original project focused on Ketapang. The current development branch expands the data pipeline to multiple West Kalimantan cities while preserving the existing vacancy.json fields used by a frontend.

## Pipeline

Google Jobs + Loker.id -> normalization -> deduplication -> vacancy.json -> frontend

## Coverage

Ketapang, Pontianak, Singkawang, Kubu Raya, Sintang, Sambas, Sanggau, Sekadau, Melawi, Landak, Bengkayang, Kapuas Hulu and Mempawah.

## Data quality changes

- Multi-query Google Jobs collection.
- Explicit source health and error reporting.
- Better vacancy identity using source URL / title / company / district.
- Added district, province, source, salary, schedule type and remote fields.
- No fake or dummy vacancy is created when all sources fail.
- Existing fields `last_updated`, `total` and `jobs` remain available for frontend compatibility.

## Automation

GitHub Actions refreshes the JSON twice per day and supports manual execution.

## Roadmap

1. More local and employer-owned sources.
2. Vacancy expiry and freshness tracking.
3. Skill, sector and salary normalization.
4. Map-based vacancy exploration.
5. Labour-market trend dashboard.
