# Phase 6: Map Stats Extraction - Research

**Researched:** 2026-02-15
**Domain:** HLTV map stats page parsing (scoreboard + round history), orchestrator integration
**Confidence:** HIGH

## Summary

Phase 6 extracts per-player scoreboards and round-by-round history from HLTV map stats pages (`/stats/matches/mapstatsid/{id}/{slug}`). Phase 3 already produced an exhaustive 872-line selector map (`map-stats.md`) verified against all 12 HTML samples, plus cross-page overlap and edge case documents. The HTML analysis work that roadmap plan 06-01 originally called for is **already complete** -- that plan should be eliminated.

The existing codebase provides a clear pattern to follow: `match_parser.py` (pure function, BeautifulSoup, dataclasses), `match_overview.py` (async orchestrator with fetch-first batching), and `repository.py` (UPSERT SQL constants with batch methods). The DB schema from migration 001 already has `player_stats` and `round_history` tables with all needed columns. The repository already has `upsert_map_player_stats()` and `upsert_map_rounds()` batch methods. No schema migration is needed.

The orchestrator for Phase 6 differs from Phase 5 in one key way: Phase 5 processes matches from `scrape_queue` (one page per match), while Phase 6 processes maps within already-scraped matches (one page per mapstatsid, multiple per match). The orchestrator needs to query the `maps` table for mapstatsids of scraped matches that don't yet have player_stats data, fetch each map stats page, parse it, and persist scoreboard + round history rows.

**Primary recommendation:** Three plans, not four. Skip the HTML analysis plan (recon already done). Plan 06-01: pure-function map stats parser. Plan 06-02: round history parser (separate because round extraction has distinct OT complexity). Plan 06-03: orchestrator integration. Alternatively, the parser could be a single module with both scoreboard and round history extraction (matching how `match_parser.py` combines all match overview extraction into one module), making it two plans total: parser + orchestrator. The two-plan approach is simpler and follows the Phase 5 pattern exactly.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| BeautifulSoup4 | (existing) | HTML parsing | Already used by match_parser.py; CSS selector-based extraction |
| lxml | (existing) | HTML parser backend | Already the default parser for BeautifulSoup in this project |
| dataclasses | stdlib | Structured return types | Already the pattern in match_parser.py |
| sqlite3 | stdlib | Database persistence | Already used throughout repository layer |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| re | stdlib | Regex parsing for compound fields | Parsing "14(9)" kills(hs), "2 : 5" op.K-D, "66.7%" KAST |
| logging | stdlib | Structured logging | Following match_parser.py pattern |
| gzip | stdlib | HTML sample loading in tests | Test helper for loading recon samples |
| pytest-asyncio | >=0.24 | Async test support | Orchestrator tests (same as test_match_overview.py) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CSS selectors | XPath | CSS selectors already verified in Phase 3 recon; switching adds risk |
| Separate parser modules | Single module | Single module follows Phase 5 pattern exactly; keeps all map stats extraction in one place |

**Installation:** No new dependencies needed. Everything is already in the project.

## Architecture Patterns

### Recommended Project Structure
```
src/scraper/
  map_stats_parser.py    # Pure function parser (NEW)
  map_stats.py           # Async orchestrator (NEW)
  repository.py          # UPSERT methods (EXISTING - already has needed methods)
  storage.py             # HTML save/load (EXISTING - already supports map_stats type)
  config.py              # Config (EXTEND - add map_stats_batch_size)
  discovery_repository.py # Queue management (EXISTING - may need minor extension)
tests/
  test_map_stats_parser.py  # Parser tests against 12 real samples (NEW)
  test_map_stats.py         # Orchestrator tests with mocked client (NEW)
```

### Pattern 1: Pure Function Parser (follow match_parser.py exactly)
**What:** Single module with dataclasses for return types and a pure `parse_map_stats(html, mapstatsid)` function that delegates to internal `_extract_*` helpers.
**When to use:** All parser modules in this project.
**Example:**
```python
# Source: existing match_parser.py pattern
@dataclass
class PlayerStats:
    player_id: int
    player_name: str
    team_id: int
    kills: int
    deaths: int
    assists: int
    flash_assists: int
    hs_kills: int
    kd_diff: int
    adr: float
    kast: float
    fk_diff: int
    rating: float
    rating_version: str  # "2.0" or "3.0"
    # Optional fields (Rating 3.0 only)
    round_swing: float | None
    # Composite extraction fields
    opening_kills: int
    opening_deaths: int
    multi_kills: int
    clutch_wins: int
    traded_deaths: int

@dataclass
class RoundOutcome:
    round_number: int
    winner_team_id: int
    winner_side: str      # "CT" or "T"
    win_type: str         # "elimination", "bomb_exploded", "bomb_defused", "time"

@dataclass
class MapStats:
    mapstatsid: int
    team_left_id: int
    team_left_name: str
    team_right_id: int
    team_right_name: str
    team_left_score: int
    team_right_score: int
    map_name: str
    rating_version: str
    # Half breakdown
    team_left_ct_rounds: int
    team_left_t_rounds: int
    team_right_ct_rounds: int
    team_right_t_rounds: int
    team_left_starting_side: str  # "CT" or "T"
    # Per-player data
    players: list[PlayerStats]
    # Round history
    rounds: list[RoundOutcome]

def parse_map_stats(html: str, mapstatsid: int) -> MapStats:
    soup = BeautifulSoup(html, "lxml")
    # ... delegate to _extract_* helpers
```

### Pattern 2: Fetch-First Batch Orchestrator (follow match_overview.py exactly)
**What:** Async function that queries for work, fetches pages, stores HTML, parses, persists.
**When to use:** All orchestrator modules.
**Key difference from Phase 5:** The work items come from the `maps` table (mapstatsids) rather than `scrape_queue`. The orchestrator needs a way to find maps that have been discovered (Phase 5 populated mapstatsid) but not yet processed for player_stats/round_history.

**Orchestrator work discovery approach:**
```python
# Query: maps that have a mapstatsid but no player_stats rows yet
SELECT m.match_id, m.map_number, m.mapstatsid
FROM maps m
WHERE m.mapstatsid IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM player_stats ps
    WHERE ps.match_id = m.match_id AND ps.map_number = m.map_number
  )
ORDER BY m.match_id, m.map_number
LIMIT :batch_size
```

This approach:
- Uses existing tables (no new status tracking table needed)
- Is idempotent (re-running finds only unprocessed maps)
- Naturally skips forfeit/unplayed maps (they have NULL mapstatsid)
- Does not require a separate queue table for map-level processing

### Pattern 3: Team ID Mapping (map stats team-left/right to match team1/team2)
**What:** Map stats pages use team-left/team-right ordering which may differ from match overview's team1/team2. The parser must extract team IDs from the page and let the orchestrator map them to the correct team1/team2 positions using data already in the matches table.
**When to use:** When persisting player_stats rows (which use team_id from the match, not from the map stats page).

The map stats page provides team IDs via `.team-left a[href]` and `.team-right a[href]` (extracting from `/stats/teams/{id}/{slug}`). These IDs match the team1_id/team2_id from the matches table. The orchestrator can look up which is team1 and which is team2.

### Anti-Patterns to Avoid
- **Separate HTML analysis plan:** The 872-line map-stats.md selector map from Phase 3 recon already covers everything. Do not waste a plan re-analyzing HTML.
- **Separate status tracking table for maps:** Adding a map_scrape_queue table duplicates the pattern. Instead, use the presence/absence of player_stats rows to determine processing state.
- **Parsing CT/T side tables separately:** The hidden `.ctstats` and `.tstats` tables have the same data that can be derived from round history. Extract only from `.totalstats` tables for Phase 6.
- **Extracting eco-adjusted data:** Marked as "future" in recon. Phase 6 should only extract traditional data columns.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Finding unprocessed maps | Custom status column on maps table | NOT EXISTS subquery against player_stats | Idempotent, no schema change needed |
| HTML save/load for map_stats | New storage methods | `HtmlStorage.save(html, match_id, page_type="map_stats", mapstatsid=X)` | Already supports map_stats page type |
| UPSERT for player_stats | New SQL | `MatchRepository.upsert_map_player_stats(stats_data)` | Already exists in repository.py |
| UPSERT for round_history | New SQL | `MatchRepository.upsert_map_rounds(rounds_data)` | Already exists in repository.py |
| Rating version detection | Custom logic | `th.st-rating` text check (see recon selector map) | Already documented with code snippet in edge-cases.md |

**Key insight:** The Phase 2 schema and repository layer was designed ahead of time to support Phase 6. The `player_stats` table has all the columns, the `round_history` table has the right structure, and the repository has batch UPSERT methods for both. The only new code needed is the parser and orchestrator.

## Common Pitfalls

### Pitfall 1: Compound Field Parsing
**What goes wrong:** Fields like kills(headshots), assists(flash), deaths(traded), and Op.K-D have compound formats that require careful regex extraction.
**Why it happens:** The HTML renders "14(9)" as a text node "14" plus a `<span>` containing "(9)". Using `get_text(strip=True)` produces "14(9)" but regex must handle edge cases.
**How to avoid:** Use a single robust regex pattern: `r'(\d+)\((\d+)\)'` for kills/assists/deaths, and `r'(\d+)\s*:\s*(\d+)'` for Op.K-D. Test against all 12 samples.
**Warning signs:** Parser returns 0 or None for kills/deaths on a sample that should have real values.

### Pitfall 2: Rating 2.0 Column Differences
**What goes wrong:** Rating 2.0 pages (sample 162345) lack the `st-roundSwing` column and have "null" for eco-adjusted values. A parser assuming Rating 3.0 structure will crash or extract wrong columns.
**Why it happens:** Only 1 of 12 samples uses Rating 2.0; easy to miss in testing.
**How to avoid:** Detect rating version FIRST via `th.st-rating` text before extracting player rows. When Rating 2.0, set `round_swing=None`. Always test against sample 162345 explicitly.
**Warning signs:** IndexError or KeyError when parsing sample 162345.

### Pitfall 3: Overtime Round History Structure
**What goes wrong:** Three distinct OT patterns exist in the round history. Parsers that only handle the common case (1 container, 24 rounds) will miss or misparse OT rounds.
**Why it happens:** Regular matches (10/12 samples), single OT (1/12), and extended OT (1/12) each have different DOM structures.
**How to avoid:**
1. Count `.round-history-con` containers (1 or 2)
2. If 1 container: all rounds (regulation + any inline OT) are in one container
3. If 2 containers: regulation in first, OT in second
4. Count actual `img.round-history-outcome` elements per team row (exclude `emptyHistory.svg`)
5. Test against samples 162345 (single OT, 30 rounds) and 206389 (extended OT, 36 rounds)
**Warning signs:** Round count doesn't match expected total score, or rounds beyond 24/30 are missing.

### Pitfall 4: Team-Left/Right vs Team1/Team2 Mismatch
**What goes wrong:** Map stats pages use team-left/team-right which may not correspond to team1/team2 from the matches table. Player stats need the correct team_id for the DB.
**Why it happens:** HLTV's map stats page orders teams independently from the match overview page.
**How to avoid:** The parser should return team IDs extracted from the page. The orchestrator should use match data from the DB to map team-left-id/team-right-id to team1_id/team2_id. The player_stats UPSERT uses the team_id from the match, not from the map stats page ordering.
**Warning signs:** All players for a match show the same team_id, or team_ids don't match matches table.

### Pitfall 5: Round Winner Side Determination
**What goes wrong:** The round history shows outcomes per team row, but determining which SIDE (CT/T) won each round requires knowing which team started which side and when sides swap.
**Why it happens:** The outcome images (ct_win, t_win, bomb_exploded, bomb_defused, stopwatch) tell you the WIN TYPE but the team rows tell you WHO won. The side is embedded in the win type (ct_win = CT side won by elimination, bomb_defused = CT side won).
**How to avoid:** Map outcome image to winner_side directly:
- `ct_win.svg` -> winner_side = "CT"
- `bomb_defused.svg` -> winner_side = "CT"
- `stopwatch.svg` -> winner_side = "CT"
- `t_win.svg` -> winner_side = "T"
- `bomb_exploded.svg` -> winner_side = "T"

Then determine `winner_team_id` from which team row the non-empty outcome appears on. Parse from ONE team row only (the top row), iterating outcomes and noting which are wins vs losses.
**Warning signs:** Inconsistent winner_side values that don't align with half scores.

### Pitfall 6: DB Schema win_type Values
**What goes wrong:** The DB schema comment says `win_type` can be "bomb_planted", "elimination", "defuse", "time". But the HLTV outcome images use different terms: `bomb_exploded`, `ct_win`/`t_win` (both are eliminations), `bomb_defused`, `stopwatch`.
**Why it happens:** The schema was designed before recon confirmed the exact image filenames.
**How to avoid:** Normalize image filenames to DB win_type values:
- `ct_win.svg` / `t_win.svg` -> "elimination"
- `bomb_exploded.svg` -> "bomb_planted" (matches schema)
- `bomb_defused.svg` -> "defuse"
- `stopwatch.svg` -> "time"
**Warning signs:** win_type values that don't match what downstream code expects.

### Pitfall 7: kd_diff and fk_diff Mapping
**What goes wrong:** The DB has `kd_diff` (kill-death difference) and `fk_diff` (first kills difference) as integer columns. The map stats page provides kills, deaths (for kd_diff = kills - deaths) and Op.K-D as "2 : 5" format (for fk_diff = opening_kills - opening_deaths).
**Why it happens:** These are derived values that must be computed from parsed fields.
**How to avoid:** Compute in the parser: `kd_diff = kills - deaths`, `fk_diff = opening_kills - opening_deaths`.
**Warning signs:** kd_diff or fk_diff stored as NULL when they should have values.

### Pitfall 8: rating_2 vs rating_3 Column Assignment
**What goes wrong:** The DB has separate `rating_2` and `rating_3` columns. The parser must detect the rating version and store the value in the correct column (the other should be NULL).
**Why it happens:** Both columns exist to preserve historical data where different rating formulas were used.
**How to avoid:** After detecting rating version:
- Rating 2.0 -> `rating_2 = <value>`, `rating_3 = None`
- Rating 3.0 -> `rating_2 = None`, `rating_3 = <value>`
**Warning signs:** Both rating columns populated for the same row, or both NULL.

## Code Examples

Verified patterns from Phase 3 recon selector map:

### Rating Version Detection
```python
# Source: map-stats.md Section "Rating Version Note" + edge-cases.md
def _detect_rating_version(soup: BeautifulSoup) -> str:
    th = soup.select_one('th.st-rating')
    if th:
        text = th.get_text(strip=True)
        if '3.0' in text:
            return '3.0'
        if '2.0' in text:
            return '2.0'
    # Fallback: check for st-roundSwing presence
    if soup.select_one('th.st-roundSwing'):
        return '3.0'
    return '3.0'  # Default to 3.0 for modern pages
```

### Map Name Extraction (Bare Text Node)
```python
# Source: map-stats.md Section 1 "Map Name"
# Verified against all 12 samples
from bs4 import NavigableString

match_info_box = soup.select_one('.match-info-box')
for child in match_info_box.children:
    if isinstance(child, NavigableString) and child.strip():
        map_name = child.strip()
        break
```

### Team ID Extraction from Map Stats
```python
# Source: map-stats.md Section 1 "Team Names and Scores"
import re

team_left_a = soup.select_one('.team-left a')
team_left_name = team_left_a.get_text(strip=True)
team_left_id = int(re.search(r'/stats/teams/(\d+)/', team_left_a['href']).group(1))

team_right_a = soup.select_one('.team-right a')
team_right_name = team_right_a.get_text(strip=True)
team_right_id = int(re.search(r'/stats/teams/(\d+)/', team_right_a['href']).group(1))
```

### Scoreboard Extraction (Total Stats Tables)
```python
# Source: map-stats.md Section 2 "Per-Player Scoreboard"
# 6 tables per page; first 2 .totalstats are team-left and team-right
totalstats_tables = soup.select('.stats-table.totalstats')
team_left_table = totalstats_tables[0]
team_right_table = totalstats_tables[1]

for row in team_left_table.select('tbody tr'):
    # Player ID
    player_a = row.select_one('td.st-player a')
    player_id = int(re.search(r'/stats/players/(\d+)/', player_a['href']).group(1))
    player_name = player_a.get_text(strip=True)

    # Kills (headshots)
    kills_td = row.select_one('td.st-kills.traditional-data')
    kills_text = kills_td.get_text(strip=True)  # "14(9)"
    m = re.match(r'(\d+)\((\d+)\)', kills_text)
    kills, hs_kills = int(m.group(1)), int(m.group(2))

    # Assists (flash)
    assists_td = row.select_one('td.st-assists')
    assists_text = assists_td.get_text(strip=True)  # "2(0)"
    m = re.match(r'(\d+)\((\d+)\)', assists_text)
    assists, flash_assists = int(m.group(1)), int(m.group(2))

    # Deaths (traded)
    deaths_td = row.select_one('td.st-deaths.traditional-data')
    deaths_text = deaths_td.get_text(strip=True)  # "15(2)"
    m = re.match(r'(\d+)\((\d+)\)', deaths_text)
    deaths, traded_deaths = int(m.group(1)), int(m.group(2))

    # ADR
    adr_td = row.select_one('td.st-adr.traditional-data')
    adr = float(adr_td.get_text(strip=True))

    # KAST (strip %)
    kast_td = row.select_one('td.st-kast.gtSmartphone-only.traditional-data')
    kast_text = kast_td.get_text(strip=True)  # "66.7%"
    kast = float(kast_text.rstrip('%'))

    # Rating
    rating_td = row.select_one('td.st-rating')
    rating = float(rating_td.get_text(strip=True))

    # Op.K-D
    opkd_td = row.select_one('td.st-opkd.gtSmartphone-only.traditional-data')
    opkd_text = opkd_td.get_text(strip=True)  # "2 : 5"
    m = re.match(r'(\d+)\s*:\s*(\d+)', opkd_text)
    opening_kills, opening_deaths = int(m.group(1)), int(m.group(2))

    # Multi-kills
    mk_td = row.select_one('td.st-mks.gtSmartphone-only')
    multi_kills = int(mk_td.get_text(strip=True))

    # Clutch wins
    clutch_td = row.select_one('td.st-clutches.gtSmartphone-only')
    clutch_wins = int(clutch_td.get_text(strip=True))

    # Round swing (Rating 3.0 only)
    round_swing = None
    if rating_version == '3.0':
        swing_td = row.select_one('td.st-roundSwing')
        if swing_td:
            swing_text = swing_td.get_text(strip=True)  # "+2.90%"
            round_swing = float(swing_text.rstrip('%'))
```

### Round History Extraction
```python
# Source: map-stats.md Section 3 "Round History"
# Outcome image -> (winner_side, win_type) mapping
OUTCOME_MAP = {
    'ct_win.svg': ('CT', 'elimination'),
    't_win.svg': ('T', 'elimination'),
    'bomb_exploded.svg': ('T', 'bomb_planted'),
    'bomb_defused.svg': ('CT', 'defuse'),
    'stopwatch.svg': ('CT', 'time'),
}

containers = soup.select('.round-history-con')

# Parse from the FIRST team row in each container
# Each team row has outcomes; non-empty outcomes = rounds that team WON
# Use first team row (team-left) and track round numbers

all_outcomes = []
round_num = 1

for container in containers:
    team_rows = container.select('.round-history-team-row')
    # Get team IDs from img.round-history-team title
    team_left_img = team_rows[0].select_one('img.round-history-team')
    team_right_img = team_rows[1].select_one('img.round-history-team')

    left_outcomes = team_rows[0].select('img.round-history-outcome')
    right_outcomes = team_rows[1].select('img.round-history-outcome')

    for left_img, right_img in zip(left_outcomes, right_outcomes):
        left_src = left_img.get('src', '')
        right_src = right_img.get('src', '')

        # Determine winner from non-empty outcome
        if 'emptyHistory' not in left_src:
            filename = left_src.rsplit('/', 1)[-1]
            side, win_type = OUTCOME_MAP[filename]
            winner_team_id = team_left_id
        elif 'emptyHistory' not in right_src:
            filename = right_src.rsplit('/', 1)[-1]
            side, win_type = OUTCOME_MAP[filename]
            winner_team_id = team_right_id
        else:
            continue  # Should not happen

        all_outcomes.append(RoundOutcome(
            round_number=round_num,
            winner_team_id=winner_team_id,
            winner_side=side,
            win_type=win_type,
        ))
        round_num += 1
```

### Half Breakdown Extraction
```python
# Source: map-stats.md Section 1 "Half Score Breakdown"
breakdown_div = soup.select_one('.match-info-row:first-child .right')
spans = breakdown_div.select('span')

# Extract spans with ct-color/t-color classes for regulation halves
side_values = []
for span in spans:
    text = span.get_text(strip=True)
    if not text:
        continue
    try:
        val = int(text)
    except ValueError:
        continue
    classes = span.get('class', [])
    side = None
    if 'ct-color' in classes:
        side = 'CT'
    elif 't-color' in classes:
        side = 'T'
    if side is not None:
        side_values.append((val, side))

# First 4 side_values are regulation halves:
# [0] = team_left half1, [1] = team_right half1
# [2] = team_left half2, [3] = team_right half2
# side_values[0].side tells team_left's starting side
```

### Orchestrator: Finding Unprocessed Maps
```python
# Source: analysis of existing schema and patterns
GET_PENDING_MAPS = """
    SELECT m.match_id, m.map_number, m.mapstatsid
    FROM maps m
    WHERE m.mapstatsid IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM player_stats ps
        WHERE ps.match_id = m.match_id AND ps.map_number = m.map_number
      )
    ORDER BY m.match_id, m.map_number
    LIMIT ?
"""
```

### Orchestrator: Building player_stats Dict for UPSERT
```python
# Source: repository.py UPSERT_PLAYER_STATS parameter names
player_stats_data = {
    "match_id": match_id,
    "map_number": map_number,
    "player_id": ps.player_id,
    "player_name": ps.player_name,
    "team_id": ps.team_id,
    "kills": ps.kills,
    "deaths": ps.deaths,
    "assists": ps.assists,
    "flash_assists": ps.flash_assists,
    "hs_kills": ps.hs_kills,
    "kd_diff": ps.kills - ps.deaths,
    "adr": ps.adr,
    "kast": ps.kast,
    "fk_diff": ps.opening_kills - ps.opening_deaths,
    "rating_2": ps.rating if ps.rating_version == '2.0' else None,
    "rating_3": ps.rating if ps.rating_version == '3.0' else None,
    "kpr": None,       # Populated in Phase 7
    "dpr": None,       # Populated in Phase 7
    "impact": None,    # Populated in Phase 7
    "scraped_at": now,
    "source_url": source_url,
    "parser_version": PARSER_VERSION,
}
```

### Orchestrator: Building round_history Dict for UPSERT
```python
# Source: repository.py UPSERT_ROUND parameter names
round_data = {
    "match_id": match_id,
    "map_number": map_number,
    "round_number": ro.round_number,
    "winner_side": ro.winner_side,
    "win_type": ro.win_type,
    "winner_team_id": ro.winner_team_id,
    "scraped_at": now,
    "source_url": source_url,
    "parser_version": PARSER_VERSION,
}
```

## DB Schema Analysis

### player_stats Table - Column Mapping

| DB Column | Map Stats Source | Extraction Method | Notes |
|-----------|-----------------|-------------------|-------|
| match_id | orchestrator context | passed from maps table query | Not on the page |
| map_number | orchestrator context | passed from maps table query | Not on the page |
| player_id | `td.st-player a[href]` | regex `/stats/players/(\d+)/` | |
| player_name | `td.st-player a` text | get_text(strip=True) | |
| team_id | `.team-left a[href]` / `.team-right a[href]` | regex `/stats/teams/(\d+)/` | Based on which table the row is in |
| kills | `td.st-kills.traditional-data` | regex `(\d+)\((\d+)\)` group 1 | |
| deaths | `td.st-deaths.traditional-data` | regex `(\d+)\((\d+)\)` group 1 | |
| assists | `td.st-assists` | regex `(\d+)\((\d+)\)` group 1 | |
| flash_assists | `td.st-assists` | regex `(\d+)\((\d+)\)` group 2 | Inside span |
| hs_kills | `td.st-kills.traditional-data` | regex `(\d+)\((\d+)\)` group 2 | Inside span |
| kd_diff | computed | kills - deaths | |
| adr | `td.st-adr.traditional-data` | float(text) | |
| kast | `td.st-kast.gtSmartphone-only.traditional-data` | float(text.rstrip('%')) | |
| fk_diff | `td.st-opkd.gtSmartphone-only.traditional-data` | parse "K : D", compute K - D | |
| rating_2 | `td.st-rating` (if version 2.0) | float(text) | NULL for 3.0 pages |
| rating_3 | `td.st-rating` (if version 3.0) | float(text) | NULL for 2.0 pages |
| kpr | N/A | NULL | Populated in Phase 7 (performance page) |
| dpr | N/A | NULL | Populated in Phase 7 (performance page) |
| impact | N/A | NULL | Populated in Phase 7 (performance page) |

### round_history Table - Column Mapping

| DB Column | Map Stats Source | Extraction Method | Notes |
|-----------|-----------------|-------------------|-------|
| match_id | orchestrator context | | |
| map_number | orchestrator context | | |
| round_number | positional | 1-based counter across all outcomes | |
| winner_side | outcome image src | OUTCOME_MAP lookup | "CT" or "T" |
| win_type | outcome image src | OUTCOME_MAP lookup, normalized | "bomb_planted", "elimination", "defuse", "time" |
| winner_team_id | which team row has non-empty outcome | team ID from that row | |

### Schema Migration Assessment

**No migration needed.** All required columns already exist in `player_stats` and `round_history` tables from migration 001. The `maps` table already has `mapstatsid` populated by Phase 5. The repository already has `upsert_map_player_stats()` and `upsert_map_rounds()` methods.

The only extension needed is a query method in the repository (or a new query in the orchestrator) to find unprocessed maps.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate HTML analysis plan per page type | Recon phase covers ALL page types upfront | Phase 3 (already done) | Plan 06-01 from roadmap is redundant |
| One plan per parser concern (scoreboard, rounds) | Single parser module combining all extraction | Phase 5 precedent | Consolidate 06-02 and 06-03 into single parser plan |
| Separate scrape queue per page type | Derive processing state from data presence | Phase 6 analysis | No new queue table needed |

**Deprecated/outdated from original roadmap:**
- 06-01 (HTML analysis): Fully covered by Phase 3 recon. The 872-line map-stats.md is the HTML analysis.
- 06-02 + 06-03 (separate parser plans): Can be consolidated into one plan following Phase 5 pattern.

## Recommended Plan Structure (Revised from Roadmap)

The original roadmap had 4 plans. Based on research, the recommended structure is **3 plans**:

### Plan 06-01: Map Stats Parser (Wave 1, no dependencies)
- Create `src/scraper/map_stats_parser.py` with pure function `parse_map_stats(html, mapstatsid)`
- Dataclasses: `PlayerStats`, `RoundOutcome`, `MapStats`
- Internal helpers: `_detect_rating_version()`, `_extract_metadata()`, `_extract_scoreboard()`, `_extract_round_history()`, `_extract_half_breakdown()`
- Handles both Rating 2.0 and 3.0
- Handles all 3 OT patterns (no OT, single OT, extended OT)
- Tests against all 12 recon samples

### Plan 06-02: Repository Extension + Config (Wave 1, no dependencies)
- Add `get_pending_map_stats()` method to `MatchRepository` (or new query method)
- Add `map_stats_batch_size` to `ScraperConfig`
- Add `upsert_map_stats_complete()` convenience method that atomically writes player_stats + round_history for one map
- Tests for new repository methods

### Plan 06-03: Map Stats Orchestrator (Wave 2, depends on 06-01 + 06-02)
- Create `src/scraper/map_stats.py` with `run_map_stats()` async function
- Follows match_overview.py pattern exactly: fetch-first batch, per-map error handling
- Fetches map stats pages using mapstatsid URLs
- Stores raw HTML via storage (page_type="map_stats")
- Parses with `parse_map_stats()`, builds dicts for UPSERT
- Persists player_stats + round_history rows atomically per map
- Tests with mocked client and real DB

**Alternative: 2-plan structure** (if simpler is preferred):
- 06-01: Parser + repository extension (combine above 06-01 and 06-02)
- 06-02: Orchestrator (same as above 06-03)

This matches Phase 5's structure exactly (05-01 = schema/repo, 05-02 = parser, 05-03 = orchestrator) but Phase 6 needs less schema work, so combining plan 1 and 2 is viable.

## Available Test Data

12 map stats HTML samples in `data/recon/`, covering all edge cases:

| Sample | MapStatsID | Characteristics | Key Test Coverage |
|--------|------------|-----------------|-------------------|
| mapstats-162345-stats.html.gz | 162345 | Rating 2.0, single OT (16-14, 30 rounds), Nuke | Rating 2.0 handling, no st-roundSwing, inline OT rounds |
| mapstats-164779-stats.html.gz | 164779 | Rating 3.0, regular (8-13), 21 rounds | Standard extraction baseline |
| mapstats-164780-stats.html.gz | 164780 | Rating 3.0, regular | Standard |
| mapstats-173424-stats.html.gz | 173424 | Rating 3.0, regular | Standard |
| mapstats-174112-stats.html.gz | 174112 | Rating 3.0, regular | Standard |
| mapstats-174116-stats.html.gz | 174116 | Rating 3.0, regular | Standard |
| mapstats-179210-stats.html.gz | 179210 | Rating 3.0, regular | Standard |
| mapstats-188093-stats.html.gz | 188093 | Rating 3.0, regular | Standard |
| mapstats-206389-stats.html.gz | 206389 | Rating 3.0, extended OT (19-17, 36 rounds), 2 containers | Extended OT with separate "Overtime" container |
| mapstats-206393-stats.html.gz | 206393 | Rating 3.0, regular | Standard |
| mapstats-219128-stats.html.gz | 219128 | Rating 3.0, regular (most recent) | Modern page structure |
| mapstats-219151-stats.html.gz | 219151 | Rating 3.0, regular (most recent) | Modern page structure |

**Critical test samples:**
- 162345: MUST test (only Rating 2.0 sample, only single OT sample)
- 206389: MUST test (only extended OT sample with 2 containers)
- 164779: Good baseline (normal Rating 3.0 match)

## Open Questions

Things that could not be fully resolved:

1. **Map stats URL slug construction**
   - What we know: The URL format is `/stats/matches/mapstatsid/{id}/{slug}`. The mapstatsid is stored in the maps table from Phase 5. The slug is cosmetic (HLTV routes by ID).
   - What's unclear: Whether HLTV will redirect a request with a wrong/empty slug to the correct page, or if we need to construct the slug from team names.
   - Recommendation: Fetch with a placeholder slug (e.g., `mapstatsid/{id}/x`) and see if HLTV redirects. If it works, no slug construction needed. The integration test will validate this. Alternatively, construct from the team names already in the DB.

2. **Batch size for map stats processing**
   - What we know: Phase 5 uses batch_size=10 (matches). Each match can have 1-5 maps. Processing 10 matches would mean 10-50 map stats page fetches.
   - What's unclear: Optimal batch size for map stats. Should it be per-match (fetch all maps for N matches) or per-map (fetch N individual map stats pages)?
   - Recommendation: Use per-map batch size (e.g., 10 map stats pages per batch). This is simpler and gives more granular progress tracking. The orchestrator fetches 10 mapstatsids regardless of which matches they belong to.

3. **round_swing field storage**
   - What we know: The DB schema does not have a `round_swing` column in `player_stats`. The parser can extract it from Rating 3.0 pages. The schema comment mentions `rating_2` and `rating_3` but not round_swing.
   - What's unclear: Whether to add a round_swing column via migration, or defer to Phase 8 validation.
   - Recommendation: The round_swing data is available but has no DB column. Options: (a) Add a migration to add the column, (b) skip extracting it and note as a gap. Given the "extract everything" philosophy, option (a) is preferred but should be evaluated during planning. This is not a blocker -- the core requirements (MAPS-01) list kills, deaths, assists, flash assists, HS kills, K/D diff, ADR, KAST%, first kills diff, and rating. Round swing is not in the requirements.

## Sources

### Primary (HIGH confidence)
- `.planning/phases/03-page-reconnaissance/recon/map-stats.md` -- 872-line selector map verified against 12 HTML samples
- `.planning/phases/03-page-reconnaissance/recon/edge-cases.md` -- Consolidated edge cases
- `.planning/phases/03-page-reconnaissance/recon/cross-page-summary.md` -- Cross-page data overlap
- `src/scraper/match_parser.py` -- Existing parser pattern to follow
- `src/scraper/match_overview.py` -- Existing orchestrator pattern to follow
- `src/scraper/repository.py` -- Existing UPSERT methods and SQL
- `migrations/001_initial_schema.sql` -- DB schema with player_stats and round_history tables
- `data/recon/mapstats-*-stats.html.gz` -- 12 real HTML samples for testing

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` -- Accumulated decisions affecting Phase 6
- `.planning/ROADMAP.md` -- Original 4-plan structure (being revised based on research)
- Phase 5 plan files (05-01, 05-02, 05-03) -- Pattern reference for plan structure

### Tertiary (LOW confidence)
- None. All findings are based on direct code/document inspection.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using exact same tools/patterns as Phase 5 (already implemented)
- Architecture: HIGH - Following established project patterns; all infrastructure exists
- Pitfalls: HIGH - Based on direct analysis of 12 HTML samples and existing code
- DB schema mapping: HIGH - Verified against migration SQL and UPSERT parameter names

**Research date:** 2026-02-15
**Valid until:** Indefinite (all sources are local project files, not external APIs/docs)
