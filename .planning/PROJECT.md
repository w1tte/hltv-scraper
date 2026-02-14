# HLTV Match Scraper

## What This Is

A web scraper that extracts comprehensive match data from HLTV.org for all CS2-era matches (late 2023 onward). Supports bulk historical scraping and incremental updates. Designed to produce clean, structured datasets for statistical analysis and prediction modeling.

## Core Value

Reliably extract every available stat from HLTV match pages into a structured, queryable dataset — without getting blocked.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Scrape match listing pages to discover all CS2-era matches
- [ ] Extract full match data: teams, scores, date, event, maps played
- [ ] Extract detailed map stats: rounds, player performance, economy data
- [ ] Extract player-level stats per map: kills, deaths, ADR, KAST, rating, etc.
- [ ] Handle HLTV's anti-scraping measures (rate limiting, headers, retries)
- [ ] Store data in structured format suitable for analysis/ML pipelines
- [ ] Bulk scrape mode for initial historical data collection
- [ ] Incremental update mode to pick up new matches since last run
- [ ] Resume capability — don't re-scrape already collected matches
- [ ] All match tiers included (majors, online leagues, lower tier)

### Out of Scope

- Real-time/live match data — this is historical only
- HLTV rankings or team profile pages — match pages only
- Web UI or dashboard — this is a data pipeline, not a product
- API integration — HLTV doesn't offer a public API, scraping only

## Context

- HLTV.org is the primary statistics site for professional Counter-Strike
- HLTV is known for aggressive anti-scraping measures (rate limiting, IP blocking, Cloudflare protection)
- Match pages contain rich nested data: match overview → map details → player stats → round history
- The match results listing page at `/results` is the entry point for discovering matches
- CS2 launched September 2023, replacing CS:GO — the cutoff point for data collection
- Data will feed into prediction models and statistical analysis, so completeness and accuracy matter

## Constraints

- **Anti-scraping**: Must respect rate limits and avoid triggering blocks — slow and steady over fast and banned
- **Data source**: HTML scraping only — no official API available
- **Scope**: CS2 era only (post September 2023) to keep dataset focused and manageable

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| CS2 era only | Keeps scope manageable, data consistent (no CS:GO mixing) | — Pending |
| All match tiers | More data for modeling, can always filter down later | — Pending |
| Bulk + incremental | Need historical backfill and ongoing updates | — Pending |

---
*Last updated: 2026-02-14 after initialization*
