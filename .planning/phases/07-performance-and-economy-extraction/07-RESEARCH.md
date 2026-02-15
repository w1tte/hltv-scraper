# Phase 7: Performance and Economy Extraction - Research

**Researched:** 2026-02-16
**Domain:** HLTV performance page (FusionChart JSON extraction, kill matrix parsing) + economy page (per-round equipment values, buy type classification)
**Confidence:** HIGH

## Summary

Phase 7 extracts data from two HLTV sub-pages per played map: the performance page (`/stats/matches/performance/mapstatsid/{id}/{slug}`) and the economy page (`/stats/matches/economy/mapstatsid/{id}/{slug}`). Both pages have been thoroughly analyzed during Phase 3 reconnaissance with 12 HTML samples each (24 total) already archived in `data/recon/`. Detailed selector maps exist at `.planning/phases/03-page-reconnaissance/recon/map-performance.md` and `map-economy.md`.

The performance page data is embedded in FusionChart JSON (`data-fusionchart-config` attribute), not HTML tables. Each of the 10 player cards contains a bar chart with 6 bars (Rating 2.0) or 7 bars (Rating 3.0). The economy page data is also in FusionChart JSON (a multi-series line chart), plus supplementary HTML equipment category tables. Both are fully present in static HTML -- no JavaScript execution needed beyond the initial page load.

The codebase already has DB columns for `kpr`, `dpr`, and `impact` in the `player_stats` table (stubbed as NULL by Phase 6). The `economy` table already exists with the correct schema. However, several fields extracted by the Phase 6 parser (`opening_kills`, `opening_deaths`, `multi_kills`, `clutch_wins`, `traded_deaths`, `round_swing`) are NOT persisted to the DB because the schema lacks those columns. Phase 7 needs a migration to add these missing columns plus new ones (`mk_rating`, kill matrix tables).

**Primary recommendation:** Follow the Phase 6 pattern exactly (parser -> repository extension -> orchestrator). Consolidate from the roadmap's 6 plans down to 4 plans by eliminating the redundant HTML analysis tasks (07-01, 07-04) since Phase 3 recon already completed that work. The orchestrator should fetch both performance and economy pages per map in a single batch run (one orchestrator, two parsers, two URL templates).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| beautifulsoup4 | 4.x (installed) | HTML parsing, CSS selector queries | Already used by map_stats_parser; consistent pattern |
| json (stdlib) | N/A | Parse FusionChart JSON from data attributes | Primary data source for both pages |
| re (stdlib) | N/A | Player ID extraction from href patterns | Two patterns: `/player/{id}/` and `/stats/players/{id}/` |
| dataclasses (stdlib) | N/A | Typed return values from parsers | Matches Phase 6 pattern exactly |
| lxml | (installed) | BeautifulSoup parser backend | Already specified in map_stats_parser |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | (installed) | Unit tests against real HTML samples | All parser and orchestrator tests |
| pytest-asyncio | >=0.24 (installed) | Async orchestrator tests | Strict mode with `@pytest.mark.asyncio` |
| gzip (stdlib) | N/A | Load compressed HTML samples for tests | Same pattern as test_map_stats_parser.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BeautifulSoup CSS selectors | lxml XPath directly | CSS selectors are simpler and match recon docs |
| json.loads on attribute | Custom JSON extraction | FusionChart JSON is well-formed, stdlib json is sufficient |

**Installation:** No new packages needed. All dependencies already installed.

## Architecture Patterns

### Recommended Project Structure

```
src/scraper/
  performance_parser.py   # Pure function: HTML -> PerformanceData dataclass
  economy_parser.py       # Pure function: HTML -> EconomyData dataclass
  performance_economy.py  # Async orchestrator (single module for both)
  repository.py           # Extended with new UPSERT + pending query
  db.py                   # Unchanged (migrations in migrations/)
  storage.py              # Already supports map_performance + map_economy page types
  config.py               # Add perf_economy_batch_size

migrations/
  004_performance_economy.sql  # New columns + kill_matrix table

tests/
  test_performance_parser.py   # Against 12 real HTML samples
  test_economy_parser.py       # Against 12 real HTML samples
  test_performance_economy.py  # Orchestrator with mocked client + real DB
```

### Pattern 1: Pure-Function Parser (Established)

**What:** Parser takes HTML string, returns a dataclass. No side effects, no DB access, no network calls.
**When to use:** Always for parsing. This is the project standard from Phase 5 and 6.
**Example:**
```python
# Source: src/scraper/map_stats_parser.py (line 87)
def parse_map_stats(html: str, mapstatsid: int) -> MapStats:
    """Pure function: HTML string in, MapStats out. No side effects."""
    soup = BeautifulSoup(html, "lxml")
    # ... extraction logic ...
    return MapStats(...)
```

### Pattern 2: FusionChart JSON Extraction (Phase 7 Specific)

**What:** Extract structured data from `data-fusionchart-config` HTML attribute using `json.loads()`.
**When to use:** Both performance and economy parsers. This is the primary data source for Phase 7.
**Example:**
```python
# Source: Phase 3 recon selector map (map-performance.md, lines 416-447)
import json

chart_el = soup.select_one('[data-fusionchart-config]')
config = json.loads(chart_el['data-fusionchart-config'])
bars = config['dataSource']['data']
bar_map = {bar['label']: bar['displayValue'] for bar in bars}
# CRITICAL: Use 'displayValue', NOT 'value' (which is normalized chart height)
```

### Pattern 3: Atomic Batch Orchestrator (Established)

**What:** Fetch all pages in batch first, then parse and persist. Fetch failure discards entire batch; parse failure is per-map.
**When to use:** The orchestrator module.
**Example:** See `src/scraper/map_stats.py` -- `run_map_stats()` function.

### Pattern 4: UPSERT with UPDATE for Phase 7 Fields

**What:** Phase 7 needs to UPDATE existing `player_stats` rows (already created by Phase 6) rather than INSERT new ones. The UPSERT pattern handles this naturally -- ON CONFLICT DO UPDATE SET will update `kpr`, `dpr`, `impact`, `mk_rating` on rows that already have kills, deaths, etc.
**When to use:** Repository layer for performance data persistence.
**Example:**
```python
# The existing UPSERT_PLAYER_STATS already handles this:
# ON CONFLICT(match_id, map_number, player_id) DO UPDATE SET
#   kpr = excluded.kpr, dpr = excluded.dpr, impact = excluded.impact ...
# Phase 7 just needs to include the new columns in the UPDATE SET clause.
```

### Anti-Patterns to Avoid
- **Separate orchestrators for performance and economy:** Both pages share the same mapstatsid and fetch pattern. One orchestrator that fetches both pages per map is simpler and avoids duplicate batch management.
- **Using `value` instead of `displayValue` from FusionChart:** The `value` field is a normalized chart rendering value, NOT the actual stat. Always use `displayValue`.
- **Hardcoding bar indices for metrics:** Use label-based lookup (`bar_map['KPR']`) not index-based (`bars[0]`). This is robust to future reordering.
- **Two-pass persistence (Phase 6 then Phase 7):** The orchestrator should UPDATE existing player_stats rows in-place, not create new ones. The UPSERT conflict target `(match_id, map_number, player_id)` handles this.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Buy type classification | Custom threshold logic | Derive from FusionChart trendline thresholds ($5K/$10K/$20K) | HLTV defines the thresholds in the chart JSON itself |
| Rating version detection | Date-based heuristic | FusionChart last bar label ("Rating 2.0" vs "Rating 3.0") | Reliable signal verified across 12 samples, date-based is unreliable |
| Player ID from performance href | Custom URL parser | `re.search(r'/player/(\d+)/', href)` pattern from map_stats_parser | Already proven, handles both `/player/` and `/stats/players/` patterns |
| HTML storage paths | New naming convention | Existing `HtmlStorage` page types `map_performance` and `map_economy` | Already defined in storage.py, tested |

**Key insight:** The entire FusionChart JSON structure has been fully documented in the Phase 3 recon selector maps, including annotated snippets for both Rating 2.0 and 3.0 formats. The parser implementation can be written directly from these documents without any additional HTML analysis.

## Common Pitfalls

### Pitfall 1: Using `value` Instead of `displayValue` from FusionChart JSON
**What goes wrong:** Parser extracts meaningless normalized bar heights instead of actual stats.
**Why it happens:** The JSON has both `value` (chart rendering) and `displayValue` (actual stat), and `value` is the more obvious key name.
**How to avoid:** Always use `displayValue`. The recon doc explicitly warns about this (map-performance.md lines 450-453).
**Warning signs:** KPR values > 2.0 or KAST values that look like decimals instead of percentages.

### Pitfall 2: DB Schema Gap -- Missing Columns from Phase 6 Parser
**What goes wrong:** Phase 6 parser extracts `opening_kills`, `opening_deaths`, `multi_kills`, `clutch_wins`, `traded_deaths`, `round_swing` but the DB schema has NO columns for them. The Phase 6 orchestrator silently drops them.
**Why it happens:** The initial Phase 2 schema was designed before Phase 3 recon discovered all available fields. The Phase 6 parser was written to extract everything, but the orchestrator only maps to existing DB columns.
**How to avoid:** Phase 7 migration (004) must add these missing columns to `player_stats` AND update the UPSERT SQL. The Phase 6 orchestrator should also be updated to persist these fields.
**Warning signs:** `opening_kills`, `multi_kills`, `clutch_wins`, `traded_deaths`, `round_swing` are always NULL in the database despite being extracted by the parser.

### Pitfall 3: PERF-01 Requirements Mismatch with Actual Data
**What goes wrong:** PERF-01 says "opening kills/deaths, multi-kill round counts" but recon proved these are NOT on the performance page.
**Why it happens:** Requirements were written before recon. Phase 3 recon (state decision 03-05) explicitly states: "Multi-kill counts (2k-5k) and clutch stats are NOT on performance page -- performance page has rates and ratings only."
**How to avoid:** The performance parser extracts what IS there (KPR, DPR, KAST, ADR, MK rating, Swing, Impact, Rating, kill matrix). Opening kills/deaths come from the map stats page (already extracted by Phase 6 parser but not persisted). Multi-kill counts also come from map stats (same situation).
**Warning signs:** Attempting to find `.st-opkd` or `.st-mks` selectors on performance page HTML and getting None.

### Pitfall 4: Economy-to-Round History FK Constraint
**What goes wrong:** Inserting economy data fails because round_history rows don't exist yet for that map.
**Why it happens:** The `economy` table has a FK to `round_history(match_id, map_number, round_number)`. If the orchestrator processes economy before map stats, the FK constraint blocks insertion.
**How to avoid:** Phase 7 orchestrator must only process maps that already have round_history data (i.e., maps already processed by Phase 6). The pending query should check for existence of round_history, not just player_stats.
**Warning signs:** `sqlite3.IntegrityError: FOREIGN KEY constraint failed` during economy upsert.

### Pitfall 5: OT Economy Data Missing for MR12 Matches
**What goes wrong:** Parser tries to match economy rounds to total score and fails for MR12 OT matches.
**Why it happens:** FusionChart shows only 24 regulation round labels for MR12 matches, even when score indicates OT (e.g., 19-17 = 36 rounds). OT economy data is simply not on the page.
**How to avoid:** Count rounds in FusionChart categories. If fewer than total score, extract regulation rounds only and note the gap.
**Warning signs:** `len(categories[0].category) < team1_score + team2_score` for an OT MR12 match.

### Pitfall 6: Two Different Player ID URL Patterns on Performance Page
**What goes wrong:** Parser uses only one regex pattern and misses player IDs from kill matrix.
**Why it happens:** Player cards use `/player/{id}/{slug}` but kill matrix uses `/stats/players/{id}/{slug}`.
**How to avoid:** Use a general regex that handles both: `re.search(r'(?:/player/|/stats/players/)(\d+)/', href)`.
**Warning signs:** Player IDs from kill matrix are all 0 or None.

## Code Examples

### Performance Page: Extract Player Metrics (Rating 3.0)

```python
# Source: Phase 3 recon map-performance.md (verified against 12 samples)
import json
import re
from dataclasses import dataclass

@dataclass
class PlayerPerformance:
    player_id: int
    player_name: str
    kpr: float
    dpr: float
    kast: float       # Percentage (0-100), stripped of '%'
    adr: float
    rating: float
    rating_version: str  # "2.0" or "3.0"
    mk_rating: float | None   # 3.0 only
    round_swing: float | None  # 3.0 only, signed percentage
    impact: float | None       # 2.0 only

def _parse_player_card(box_el, rating_version: str) -> PlayerPerformance:
    """Extract metrics from a single .standard-box player card."""
    # Player identity
    link = box_el.select_one('.headline a[href]')
    nick = box_el.select_one('.player-nick').get_text(strip=True)
    pid_m = re.search(r'/player/(\d+)/', link['href'])
    player_id = int(pid_m.group(1))

    # FusionChart data
    chart_el = box_el.select_one('[data-fusionchart-config]')
    config = json.loads(chart_el['data-fusionchart-config'])
    bars = config['dataSource']['data']
    bar_map = {bar['label']: bar['displayValue'] for bar in bars}

    # Common metrics
    kpr = float(bar_map['KPR'])
    dpr = float(bar_map['DPR'])
    kast = float(bar_map['KAST'].rstrip('%'))
    adr = float(bar_map['ADR'])

    # Version-specific
    if rating_version == '3.0':
        return PlayerPerformance(
            player_id=player_id, player_name=nick,
            kpr=kpr, dpr=dpr, kast=kast, adr=adr,
            rating=float(bar_map['Rating 3.0']),
            rating_version='3.0',
            mk_rating=float(bar_map['MK rating']),
            round_swing=float(bar_map['Swing'].rstrip('%')),
            impact=None,
        )
    else:
        return PlayerPerformance(
            player_id=player_id, player_name=nick,
            kpr=kpr, dpr=dpr, kast=kast, adr=adr,
            rating=float(bar_map['Rating 2.0']),
            rating_version='2.0',
            mk_rating=None, round_swing=None,
            impact=float(bar_map['Impact']),
        )
```

### Performance Page: Rating Version Detection

```python
# Source: Phase 3 recon map-performance.md (lines 106-142)
def detect_rating_version(soup):
    """Detect rating version from FusionChart bar labels."""
    chart_el = soup.select_one('[data-fusionchart-config]')
    if not chart_el:
        return 'unknown'
    config = json.loads(chart_el['data-fusionchart-config'])
    bars = config['dataSource']['data']
    if bars and bars[-1]['label'] == 'Rating 3.0':
        return '3.0'
    if bars and bars[-1]['label'] == 'Rating 2.0':
        return '2.0'
    return 'unknown'
```

### Performance Page: Kill Matrix Extraction

```python
# Source: Phase 3 recon map-performance.md (Section 3, lines 258-328)
@dataclass
class KillMatrixEntry:
    player1_id: int      # Row player (team2)
    player2_id: int      # Column player (team1)
    player1_kills: int   # Row player kills
    player2_kills: int   # Column player kills

def _parse_kill_matrix(container_el) -> list[KillMatrixEntry]:
    """Parse a single kill matrix (All, First kills, or AWP)."""
    entries = []
    table = container_el.select_one('.stats-table')
    if not table:
        return entries

    # Column headers = team1 players
    topbar = table.select_one('.killmatrix-topbar')
    col_links = topbar.select('td a')
    col_ids = []
    for a in col_links:
        m = re.search(r'/stats/players/(\d+)/', a.get('href', ''))
        col_ids.append(int(m.group(1)) if m else 0)

    # Data rows = team2 players
    rows = table.select('tr:not(.killmatrix-topbar)')
    for row in rows:
        row_td = row.select_one('td.team2')
        if not row_td:
            continue
        row_link = row_td.select_one('a')
        m = re.search(r'/stats/players/(\d+)/', row_link.get('href', ''))
        row_id = int(m.group(1)) if m else 0

        cells = row.select('td.text-center')
        for i, cell in enumerate(cells):
            if i >= len(col_ids):
                break
            t2_score = cell.select_one('.team2-player-score')
            t1_score = cell.select_one('.team1-player-score')
            entries.append(KillMatrixEntry(
                player1_id=row_id,
                player2_id=col_ids[i],
                player1_kills=int(t2_score.get_text(strip=True)) if t2_score else 0,
                player2_kills=int(t1_score.get_text(strip=True)) if t1_score else 0,
            ))
    return entries
```

### Economy Page: Extract Per-Round Data

```python
# Source: Phase 3 recon map-economy.md (Section 3, lines 86-109)
@dataclass
class RoundEconomy:
    round_number: int
    team_name: str
    equipment_value: int
    buy_type: str          # "full_eco", "semi_eco", "semi_buy", "full_buy"
    won_round: bool
    side: str | None       # "CT" or "T" (from anchor image)

def _parse_economy(soup) -> list[RoundEconomy]:
    """Extract per-round economy data from FusionCharts JSON."""
    fc_el = soup.select_one('worker-ignore.graph[data-fusionchart-config]')
    config = json.loads(fc_el['data-fusionchart-config'])
    ds = config['dataSource']

    round_labels = [cat['label'] for cat in ds['categories'][0]['category']]
    results = []

    for dataset in ds['dataset']:
        team_name = dataset['seriesname']
        for i, point in enumerate(dataset['data']):
            round_num = int(round_labels[i])
            equip_val = int(point['value'])
            anchor = point.get('anchorImageUrl')

            won = anchor is not None
            side = None
            if anchor:
                if 'ctRoundWon' in anchor:
                    side = 'CT'
                elif 'tRoundWon' in anchor:
                    side = 'T'

            buy_type = _classify_buy_type(equip_val)
            results.append(RoundEconomy(
                round_number=round_num,
                team_name=team_name,
                equipment_value=equip_val,
                buy_type=buy_type,
                won_round=won,
                side=side,
            ))
    return results

def _classify_buy_type(value: int) -> str:
    """Classify equipment value into buy type using HLTV thresholds."""
    if value >= 20000:
        return "full_buy"
    elif value >= 10000:
        return "semi_buy"
    elif value >= 5000:
        return "semi_eco"
    else:
        return "full_eco"
```

### DB Migration: New Columns and Kill Matrix Table

```sql
-- migrations/004_performance_economy.sql
-- Phase 7: Performance and Economy Extraction
-- Adds missing columns to player_stats and creates kill_matrix table

-- Add columns that Phase 6 parser extracts but could not persist
ALTER TABLE player_stats ADD COLUMN opening_kills INTEGER;
ALTER TABLE player_stats ADD COLUMN opening_deaths INTEGER;
ALTER TABLE player_stats ADD COLUMN multi_kills INTEGER;
ALTER TABLE player_stats ADD COLUMN clutch_wins INTEGER;
ALTER TABLE player_stats ADD COLUMN traded_deaths INTEGER;
ALTER TABLE player_stats ADD COLUMN round_swing REAL;  -- Rating 3.0 only

-- Add columns for Phase 7 performance page metrics
ALTER TABLE player_stats ADD COLUMN mk_rating REAL;  -- Rating 3.0 MK rating

-- Kill matrix table (head-to-head kills between players)
CREATE TABLE IF NOT EXISTS kill_matrix (
    match_id      INTEGER NOT NULL,
    map_number    INTEGER NOT NULL,
    matrix_type   TEXT NOT NULL,          -- "all", "first_kill", "awp"
    player1_id    INTEGER NOT NULL,       -- Row player
    player2_id    INTEGER NOT NULL,       -- Column player
    player1_kills INTEGER NOT NULL,       -- Row player's kills against column player
    player2_kills INTEGER NOT NULL,       -- Column player's kills against row player
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, map_number, matrix_type, player1_id, player2_id),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE INDEX IF NOT EXISTS idx_kill_matrix_players
    ON kill_matrix(player1_id, player2_id);
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Performance data in HTML tables | FusionChart JSON in data-fusionchart-config attribute | Always (HLTV design) | json.loads() is the primary extraction method |
| Rating 2.0 (6 metrics, Impact) | Rating 3.0 (7 metrics, MK rating + Swing) | Gradual ~2023-2024 (retroactive) | Parser must handle both; 1/12 samples still 2.0 |
| MR15 format (30 round regulation) | MR12 format (24 round regulation) | ~2024 | Economy OT data missing for MR12 matches |
| kpr/dpr/impact columns as stubs (NULL) | Phase 7 populates them from performance page | Now | UPSERT ON CONFLICT updates existing rows |

**Deprecated/outdated:**
- PERF-01 requirement mentions "opening kills/deaths, multi-kill round counts" as performance page data. Phase 3 recon proved these are NOT on the performance page (they are on the map stats page, already extracted by Phase 6 parser). PERF-01 should be interpreted as: "extract the performance-page-specific metrics (KPR, DPR, rates/ratings) plus the kill matrix."

## Critical Finding: Plan Consolidation

The roadmap lists 6 plans for Phase 7:
- 07-01: Performance page HTML analysis and selector map
- 07-02: Performance data parser
- 07-03: Rating version detection and dual-format handling
- 07-04: Economy page HTML analysis and selector map
- 07-05: Economy data parser
- 07-06: Integration orchestrator

**07-01 and 07-04 are redundant.** Phase 3 recon (plans 03-05 and 03-06) already produced comprehensive selector maps with cross-sample verification for both pages. These are in `.planning/phases/03-page-reconnaissance/recon/map-performance.md` (872 lines) and `map-economy.md` (616 lines). No further HTML analysis is needed.

**07-03 can be merged into 07-02.** Rating version detection is ~15 lines of code (check last FusionChart bar label). It does not warrant a separate plan -- it is an if/else branch inside the parser.

**Recommended 4-plan breakdown:**
1. **07-01: Schema migration + repository extension** -- Add missing DB columns (opening_kills, opening_deaths, multi_kills, clutch_wins, traded_deaths, round_swing, mk_rating), create kill_matrix table, extend UPSERT SQL, add pending query, update Phase 6 orchestrator to persist newly-available columns.
2. **07-02: Performance page parser** -- Pure function parser with Rating 2.0/3.0 handling, player metrics extraction from FusionChart JSON, kill matrix extraction, tested against all 12 recon samples.
3. **07-03: Economy page parser** -- Pure function parser extracting per-round equipment values, buy type classification, team/round attribution, OT handling, tested against all 12 recon samples.
4. **07-04: Performance + economy orchestrator** -- Single async orchestrator that fetches both page types per map, stores HTML, parses, and persists atomically. Follows Phase 6 batch pattern.

## DB Schema Analysis

### Current State
The `player_stats` table already has stub columns for Phase 7: `kpr REAL`, `dpr REAL`, `impact REAL`. These are set to NULL by the Phase 6 orchestrator.

The `economy` table already exists with the correct schema: `(match_id, map_number, round_number, team_id, equipment_value, buy_type)` with a FK to `round_history`.

### Missing Columns (Must Add)
The Phase 6 parser extracts but cannot persist these fields because the DB schema lacks the columns:

| Field | Parser Source | DB Column Needed | Type |
|-------|-------------|------------------|------|
| opening_kills | map_stats_parser.py line 44 | `opening_kills INTEGER` | int |
| opening_deaths | map_stats_parser.py line 45 | `opening_deaths INTEGER` | int |
| multi_kills | map_stats_parser.py line 49 | `multi_kills INTEGER` | int |
| clutch_wins | map_stats_parser.py line 50 | `clutch_wins INTEGER` | int |
| traded_deaths | map_stats_parser.py line 51 | `traded_deaths INTEGER` | int |
| round_swing | map_stats_parser.py line 52 | `round_swing REAL` | float (nullable) |
| mk_rating | Performance page FusionChart | `mk_rating REAL` | float (nullable) |

### New Table Needed
Kill matrix requires a new table since it stores head-to-head relationships (N:N between players per map), not per-player stats.

### Orchestrator Update Required
The Phase 6 orchestrator (`map_stats.py` lines 108-133) must be updated to include the newly-added columns in its dict construction. Currently it maps `ps.opening_kills` etc. to nothing -- those fields are silently dropped. After the migration, the dict should include all new columns.

### Economy FK Consideration
The `economy` table has `FOREIGN KEY (match_id, map_number, round_number) REFERENCES round_history(...)`. This means economy data can only be inserted AFTER round_history rows exist. The pending query for economy extraction must check for `round_history` existence, which effectively means checking that Phase 6 has completed for that map.

## Pending State Detection Strategy

### For Performance Data
The Phase 7 orchestrator needs to find maps where performance data hasn't been extracted yet. The simplest signal: `kpr IS NULL` in `player_stats`. If Phase 6 has run (player_stats rows exist with kills/deaths/etc. populated) but Phase 7 hasn't (kpr is still NULL), the map needs performance extraction.

```sql
SELECT m.match_id, m.map_number, m.mapstatsid
FROM maps m
WHERE m.mapstatsid IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM player_stats ps
    WHERE ps.match_id = m.match_id AND ps.map_number = m.map_number
  )
  AND EXISTS (
    SELECT 1 FROM player_stats ps
    WHERE ps.match_id = m.match_id AND ps.map_number = m.map_number
      AND ps.kpr IS NULL
  )
ORDER BY m.match_id, m.map_number
LIMIT ?
```

### For Economy Data
Economy data has its own table. Pending = maps with round_history but no economy rows:

```sql
SELECT m.match_id, m.map_number, m.mapstatsid
FROM maps m
WHERE m.mapstatsid IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM round_history rh
    WHERE rh.match_id = m.match_id AND rh.map_number = m.map_number
  )
  AND NOT EXISTS (
    SELECT 1 FROM economy e
    WHERE e.match_id = m.match_id AND e.map_number = m.map_number
  )
ORDER BY m.match_id, m.map_number
LIMIT ?
```

### Combined Approach
Since the orchestrator processes both performance and economy together, use the UNION or simply query for maps where EITHER performance OR economy is pending. A practical approach: use the performance pending query (kpr IS NULL) since performance and economy will always be fetched together.

## URL Templates

```python
PERF_URL_TEMPLATE = "/stats/matches/performance/mapstatsid/{mapstatsid}/x"
ECON_URL_TEMPLATE = "/stats/matches/economy/mapstatsid/{mapstatsid}/x"
```

The `/x` placeholder slug pattern is established by Phase 6 (MAP_STATS_URL_TEMPLATE). HLTV routes by numeric mapstatsid, ignoring the slug text.

## Test Strategy

### Performance Parser Tests (12 samples)
All 12 performance HTML samples in `data/recon/` follow the naming pattern `performance-{mapstatsid}.html.gz`:
- performance-162345 (Rating 2.0, 6 bars, Impact metric)
- performance-164779, 164780, 173424, 174112, 174116, 179210, 188093, 206389, 206393, 219128, 219151 (Rating 3.0, 7 bars)

Test classes should mirror Phase 6 test structure:
- `TestPlayerMetricsExtraction` -- verify KPR, DPR, KAST, ADR, rating values
- `TestRating20Handling` -- 6 bars, Impact present, MK rating/Swing absent
- `TestRating30Handling` -- 7 bars, MK rating/Swing present, Impact absent
- `TestKillMatrixExtraction` -- 3 types, 5x5 dimensions, player IDs
- `TestTeamOverview` -- kills/deaths/assists team totals
- `TestAllSamplesParseWithoutCrash` -- smoke test across all 12 samples

### Economy Parser Tests (12 samples)
All 12 economy samples: `economy-{mapstatsid}.html.gz`:
- economy-162345 (MR15, 30 rounds including OT, all data present)
- economy-206389 (MR12, OT match, only 24 regulation rounds in data)
- Others: standard MR12 regulation matches

Test classes:
- `TestPerRoundExtraction` -- equipment values, buy types, round outcomes
- `TestBuyTypeClassification` -- threshold boundaries ($5K, $10K, $20K)
- `TestOvertimeHandling` -- MR15 OT (all rounds) vs MR12 OT (regulation only)
- `TestTeamAttribution` -- team names from dataset seriesname
- `TestAllSamplesParseWithoutCrash` -- smoke test across all 12 samples

### Orchestrator Tests
Follow `test_map_stats.py` pattern:
- Mock HLTVClient with real HTML samples
- Real in-memory DB with migrations applied
- Seed match/map/player_stats rows (Phase 6 must have already run)
- Verify performance fields populated (kpr, dpr, impact/mk_rating)
- Verify economy rows inserted
- Verify kill_matrix rows inserted
- Test fetch failure discards batch
- Test parse failure continues per-map

## Open Questions

1. **Should Phase 6 orchestrator be retroactively updated?**
   - What we know: Phase 6 parser extracts opening_kills, multi_kills, etc. but the orchestrator drops them. After migration 004 adds the columns, the Phase 6 orchestrator COULD be updated to persist them.
   - What's unclear: Should this be done as part of Phase 7 plan 01, or left as tech debt?
   - Recommendation: Update the Phase 6 orchestrator dict mapping in plan 07-01 since the migration adds the columns and the code change is minimal (add ~6 dict keys). This ensures re-running Phase 6 populates the new columns.

2. **Economy table FK to round_history: relax or keep?**
   - What we know: The FK ensures economy data can only exist for rounds that have round_history. This is correct but means Phase 6 must complete before Phase 7 economy can run.
   - What's unclear: Could there be edge cases where round_history has fewer rounds than economy data (e.g., economy shows 24 rounds but round_history has 21)?
   - Recommendation: Keep the FK. The pending query already ensures Phase 6 has completed (round_history exists). If a round count mismatch occurs, the parser should only insert economy rows for rounds that exist in round_history.

3. **Kill matrix data granularity: store per-cell or per-player-pair?**
   - What we know: Each cell has (player1_kills, player2_kills). Storing per-cell means 25 rows per matrix type, 75 rows per map.
   - What's unclear: Is this the right granularity or should we aggregate somehow?
   - Recommendation: Store per-cell (per player pair). The PK `(match_id, map_number, matrix_type, player1_id, player2_id)` is natural and query-friendly. 75 rows per map is minimal.

## Sources

### Primary (HIGH confidence)
- `.planning/phases/03-page-reconnaissance/recon/map-performance.md` -- 872-line selector map verified against 12 HTML samples
- `.planning/phases/03-page-reconnaissance/recon/map-economy.md` -- 616-line selector map verified against 12 HTML samples
- `.planning/phases/03-page-reconnaissance/recon/cross-page-summary.md` -- Canonical extraction sources and overlap map
- `.planning/phases/03-page-reconnaissance/recon/edge-cases.md` -- All edge cases documented
- `src/scraper/map_stats_parser.py` -- Current parser pattern (Phase 6, verified working)
- `src/scraper/map_stats.py` -- Current orchestrator pattern (Phase 6, verified working)
- `src/scraper/repository.py` -- Current UPSERT patterns and pending queries
- `migrations/001_initial_schema.sql` -- Current DB schema with player_stats and economy tables
- `src/scraper/storage.py` -- Already supports `map_performance` and `map_economy` page types
- `data/recon/performance-*.html.gz` -- 12 real HTML samples for testing
- `data/recon/economy-*.html.gz` -- 12 real HTML samples for testing

### Secondary (MEDIUM confidence)
- None needed -- all findings verified against primary sources

### Tertiary (LOW confidence)
- None -- no web searches required; all data available in codebase and recon artifacts

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- using identical libraries and patterns as Phase 6
- Architecture: HIGH -- following established parser/repository/orchestrator pattern from Phases 5-6
- DB schema changes: HIGH -- gap analysis performed by comparing parser dataclass fields to DB columns and UPSERT SQL
- Pitfalls: HIGH -- all identified from concrete code analysis and recon document review
- Code examples: HIGH -- adapted directly from Phase 3 recon annotated snippets verified against 12 real samples

**Research date:** 2026-02-16
**Valid until:** Indefinite (HTML structure verified across 2023-2026 samples; economy page "Beta" label is the only risk signal for future changes)
