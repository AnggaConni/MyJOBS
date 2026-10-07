# ketapangJOBS

Local Job Aggregator & Labour-Market Radar for West Kalimantan, Indonesia.

The project started as a Ketapang-focused vacancy collector and is being expanded into a regional job intelligence pipeline.

## Sources

- Google Jobs via SerpApi
- Loker.id
- ReliefWeb Jobs API
- UN Careers RSS feed
- OCHA vacancies are detected from UN Careers / humanitarian sources

ReliefWeb currently requires a pre-approved `appname` for API use. Configure it as the GitHub Actions secret `RELIEFWEB_APPNAME`.

## Expiry handling

Jobs with an explicit source deadline are removed automatically once the deadline passes.

Jobs whose source reports a closed/past/expired/inactive status are also removed.

The scraper does **not** invent a deadline for Google Jobs or Loker.id when the source does not provide one.

The latest run reports the number of removed expired jobs as `expired_removed`.

## External source buttons

`sources.json` contains button labels and official destination URLs for ReliefWeb Jobs, UN Careers and UN OCHA vacancies.

## Data contract

`vacancy.json` keeps the frontend fields `last_updated`, `total` and `jobs`.

It additionally provides:

- `status`
- `schema_version`
- `coverage`
- `summary`
- `sources`
- `external_links`
- `errors`
- `expired_removed`

No fake or dummy vacancy is created when all sources fail.

## Coverage

Ketapang, Pontianak, Singkawang, Kubu Raya, Sintang, Sambas, Sanggau, Sekadau, Melawi, Landak, Bengkayang, Kapuas Hulu and Mempawah.

## Automation

GitHub Actions refreshes the dataset twice per day and supports manual execution.

## Roadmap

1. Add more employer-owned and local sources.
2. Track first-seen / last-seen timestamps.
3. Normalize skills, sectors, salary and employment type.
4. Add map-based vacancy exploration.
5. Build a labour-market trend dashboard.
