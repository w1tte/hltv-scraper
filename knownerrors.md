# Known Errors

Errors observed during scraping that are expected/benign and do not indicate bugs.

## 1. "Expected 2 .stats-table.totalstats tables, found 1"

- **Source**: `map_stats_parser.py`
- **Effect**: All player_stats quarantined for that map (0 players extracted)
- **Cause**: HLTV sometimes only renders one team's scoreboard on the map stats page. Likely incomplete/bugged pages on HLTV's side (e.g. forfeits, admin decisions, or page rendering errors).
- **Examples**: mapstatsid 219647, 219671, 219476, 219551
- **Resolution**: Maps are retried on next scrape. If HLTV never fixes the page, the map stays in quarantine.

## 2. "Response too short" fetch failures

- **Source**: `http_client.py` / `performance_economy.py`
- **Effect**: Fetch returns 0 or 1024 chars instead of a full page
- **Cause**: Cloudflare returned an error page or empty response, typically after heavy rate limiting from too many concurrent browsers. The 1024-char responses are Cloudflare's "Access Denied" HTML.
- **Resolution**: Reduce worker count (especially perf workers). Maps are retried on next scrape up to `max_attempts` times.

## 3. "Content marker 'data-fusionchart-config' not found"

- **Source**: `http_client.py`
- **Effect**: Performance or economy page fetch treated as failure
- **Cause**: The page loaded (12k-50k chars) but didn't contain the FusionCharts JSON data. Either a Cloudflare interstitial that passed the size check, or an HLTV page that genuinely lacks economy/performance data (e.g. very old matches, or matches with incomplete stats).
- **Resolution**: Retried on next scrape. If persistent, the map hits `max_attempts` and is skipped.

## 4. "Fewer than 2 veto boxes found"

- **Source**: `match_parser.py`
- **Effect**: Vetoes not extracted for that match (match still saved successfully)
- **Cause**: Some matches (especially BO1s, showmatches, or lower-tier events) don't have veto information on HLTV. This is expected and common.
- **Resolution**: None needed. The match is saved without veto data.

## 5. Validation: e_kast > 100%

- **Source**: `PlayerStatsModel` validation (fixed)
- **Effect**: Previously quarantined players with eco-adjusted KAST above 100%
- **Cause**: HLTV's eco-adjusted KAST uses round weighting that can legitimately exceed 100% (observed values: 100.4%, 100.9%, 101.0%, 101.8%, 104.8%, 104.9%).
- **Resolution**: Fixed — removed `le=100.0` constraint on `e_kast` field.

## 6. Rate limiter exponential backoff stalls

- **Source**: `rate_limiter.py` / `http_client.py`
- **Effect**: Scraper appears stuck for minutes at a time, delay escalates (0.6s -> 1.2s -> 2.4s -> 4.8s -> 9.6s -> 16.5s)
- **Cause**: Too many concurrent perf workers (e.g. 20) all hitting Cloudflare challenges simultaneously. Each challenge triggers retry + backoff, compounding across all workers.
- **Resolution**: Keep perf workers at 4-6. Recommended config: `--overview-workers 3 --map-workers 6 --perf-workers 4`.
