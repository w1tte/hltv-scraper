# Phase 5: Match Overview Extraction - Research

**Researched:** 2026-02-15
**Domain:** HTML parsing of HLTV match overview pages, data persistence to SQLite
**Confidence:** HIGH

## Summary

Phase 5 extracts match-level data from HLTV match overview pages (`/matches/{match_id}/{slug}`). This phase consumes the scrape queue populated by Phase 4 (discovery) and produces structured match, map, veto, and roster data stored in the database and raw HTML on disk.

The existing codebase provides all infrastructure needed: `HLTVClient` for fetching, `HtmlStorage` for raw HTML archival, `MatchRepository` for database persistence, `DiscoveryRepository` for queue management, and BeautifulSoup/lxml for parsing. The match overview selector map from Phase 3 recon has been verified against 9 real HTML samples covering BO1, BO3, BO5, forfeit, partial forfeit, overtime, and unranked teams. All selectors are confirmed working.

The main new work is: (1) a pure-function parser for match overview HTML, (2) schema additions for vetoes and rosters (not covered by current tables), (3) methods on DiscoveryRepository to pull pending matches from the queue and update their status, and (4) an orchestrator that ties fetch/store/parse/persist together in batched runs.

**Primary recommendation:** Follow the Phase 4 pattern exactly -- pure parser function (HTML in, structured data out), tested against real gzipped samples, with a thin orchestrator that coordinates fetch/store/parse/persist.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| beautifulsoup4 | >=4.12 | HTML parsing and CSS selector queries | Already in project deps; used by Phase 4 parser |
| lxml | >=5.0 | Fast HTML parser backend for BeautifulSoup | Already in project deps; 5-10x faster than html.parser |
| sqlite3 | stdlib | Database persistence via UPSERT | Already used by repository.py, discovery_repository.py |
| nodriver | >=0.38 | Chrome-based page fetching with Cloudflare bypass | Already in project deps; only working approach for HLTV |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| re | stdlib | Regex for ID extraction from hrefs | Team IDs, event IDs, mapstatsids, player IDs from URL patterns |
| gzip | stdlib | Compress/decompress stored HTML | Already used by HtmlStorage |
| dataclasses | stdlib | Structured return types from parser | Same pattern as DiscoveredMatch in Phase 4 |
| logging | stdlib | Parser warnings for edge cases | Same pattern as discovery.py |
| datetime | stdlib | ISO 8601 timestamps for provenance | Same pattern as discovery.py |

### Alternatives Considered
None -- all tools are already in the project and proven.

**Installation:**
No new dependencies needed. All libraries are already in `pyproject.toml`.

## Architecture Patterns

### Existing Project Structure (for reference)
```
src/scraper/
  __init__.py          # Package init
  config.py            # ScraperConfig dataclass
  db.py                # Database connection manager + migrations
  discovery.py         # DiscoveredMatch + parse_results_page + run_discovery
  discovery_repository.py  # DiscoveryRepository (scrape_queue CRUD)
  exceptions.py        # Exception hierarchy
  http_client.py       # HLTVClient (nodriver + tenacity + rate limiter)
  rate_limiter.py      # Adaptive rate limiter
  repository.py        # MatchRepository (matches/maps/player_stats CRUD)
  storage.py           # HtmlStorage (gzip HTML save/load)
```

### Phase 5 New Files
```
src/scraper/
  match_parser.py      # NEW: parse_match_overview() pure function + dataclasses
migrations/
  003_vetoes_rosters.sql  # NEW: vetoes + match_players tables
tests/
  test_match_parser.py    # NEW: parser unit tests against real HTML samples
```

### Pattern 1: Pure Parser Function (from Phase 4)
**What:** A stateless function that takes raw HTML string and returns structured dataclasses. No side effects, no database access, no HTTP calls.
**When to use:** All HTML parsing in this project.
**Example:**
```python
# Source: src/scraper/discovery.py (existing pattern)
def parse_results_page(html: str) -> list[DiscoveredMatch]:
    soup = BeautifulSoup(html, "lxml")
    entries = soup.select(".result-con[data-zonedgrouping-entry-unix]")
    results = []
    for entry in entries:
        # ... extract fields ...
        results.append(DiscoveredMatch(...))
    return results
```

For Phase 5, the parser will return a structured result object containing match metadata, map data, veto steps, and roster entries -- all from a single HTML page.

### Pattern 2: Repository UPSERT with Module-Level SQL (from Phase 2/4)
**What:** SQL constants defined at module level, repository class takes `sqlite3.Connection`, write methods use `with self.conn:` for auto-commit.
**When to use:** All database writes.
**Example:**
```python
# Source: src/scraper/repository.py (existing pattern)
UPSERT_MATCH = """
    INSERT INTO matches (...) VALUES (...)
    ON CONFLICT(match_id) DO UPDATE SET ...
"""

class MatchRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_match(self, data: dict) -> None:
        with self.conn:
            self.conn.execute(UPSERT_MATCH, data)
```

### Pattern 3: Test Against Real HTML Samples (from Phase 4)
**What:** Unit tests load gzipped HTML from `data/recon/`, parse it, and assert on extracted fields.
**When to use:** All parser tests.
**Example:**
```python
# Source: tests/test_results_parser.py (existing pattern)
RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"

def load_sample(filename: str) -> str:
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample HTML not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")
```

### Pattern 4: Async Orchestrator (from Phase 4)
**What:** An async function that coordinates client/storage/repo/config without type hints on parameters (to avoid circular imports).
**When to use:** The top-level "run" function that drives fetching + parsing + persistence.
**Example:**
```python
# Source: src/scraper/discovery.py (existing pattern)
async def run_discovery(client, repo, storage, config) -> dict:
    # 1. Get work items from repo
    # 2. Fetch pages via client
    # 3. Archive via storage
    # 4. Parse
    # 5. Persist via repo
    return stats
```

### Anti-Patterns to Avoid
- **Coupling parser to database:** The parser must be a pure function. Database writes happen in the orchestrator, not in the parser.
- **Fetching inside the parser:** The parser takes HTML string input only. Fetching is the orchestrator's responsibility.
- **Ignoring edge cases in tests:** Every test must cover at least one forfeit case and one normal case. The recon samples provide both.
- **Using CSS pseudo-classes for veto box selection:** `:last-of-type` is unreliable. Use index-based selection (`soup.select('.veto-box')[1]`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML parsing | String manipulation / regex on HTML | BeautifulSoup + lxml | HTML is messy; BS4 handles malformed HTML, encoding issues, etc. |
| Database migrations | Manual CREATE TABLE in code | SQL files in `migrations/` dir | Existing `Database.apply_migrations()` handles versioning automatically |
| Rate limiting | Custom sleep logic | Existing `RateLimiter` via `HLTVClient` | Already tuned for HLTV's Cloudflare protection |
| HTML compression | Custom storage | Existing `HtmlStorage.save()` | Already handles gzip, directory creation, path building |
| UPSERT semantics | Manual SELECT-then-INSERT | SQLite `ON CONFLICT DO UPDATE SET` | Atomic, idempotent, handles re-scraping gracefully |
| Retry logic | Manual retry loops | Existing `HLTVClient.fetch()` with tenacity | Already configured for Cloudflare challenge retry |

**Key insight:** Phase 5 is primarily a parser + orchestrator. All infrastructure (fetch, store, persist, retry, rate limit) already exists from Phases 1-4.

## Common Pitfalls

### Pitfall 1: Forfeit Match Handling
**What goes wrong:** Parser crashes or produces garbage when encountering a forfeit match (mapname "Default", missing `.won`/`.lost` divs).
**Why it happens:** Forfeit pages have fundamentally different DOM structure -- missing score elements, no stats links, different countdown text.
**How to avoid:** Check for forfeit conditions FIRST, before trying to extract scores/stats links. Store partial data (teams, event, date, forfeit flag) and skip sub-page URL collection.
**Warning signs:** `None` values where integers are expected; `IndexError` on missing elements.

**Verified forfeit signals (from real HTML samples):**
- `.mapholder .mapname` text == "Default" (most reliable, handles both full and partial forfeits)
- `.team1-gradient .won` and `.team1-gradient .lost` both absent (full forfeit only)
- `.countdown` text == "Match deleted" (full forfeit only)

### Pitfall 2: Two Veto Boxes
**What goes wrong:** Parser extracts format text instead of veto sequence, or extracts veto lines from the wrong box.
**Why it happens:** There are always TWO `.standard-box.veto-box` elements. The first contains match format + stage info. The second contains the actual veto sequence.
**How to avoid:** Use index-based selection: `soup.select('.veto-box')[1]` for vetoes. Use `soup.select('.veto-box')[0]` (or `.padding.preformatted-text`) for format text.
**Warning signs:** Veto lines contain "Best of" text; veto sequence has 0 entries.

### Pitfall 3: Half-Score Parsing Complexity
**What goes wrong:** Half scores are parsed as text "(7:5;6:6)" instead of structured data, losing CT/T side attribution. Or overtime periods are missed.
**Why it happens:** The half-score div contains multiple `<span>` elements with class="ct" or class="t" for regulation, but overtime spans lack these classes entirely.
**How to avoid:** Iterate over span children, extract numeric values paired with their CSS class. Regulation spans have ct/t classes; overtime spans do not. Validate that sum of half scores equals total map score.
**Warning signs:** Side attribution is wrong; overtime rounds are missing from half-score totals.

### Pitfall 4: BO1 Score Representation
**What goes wrong:** Parser expects series-level `.won`/`.lost` scores for all matches, but BO1 series scores are the same as map scores (e.g., "16" and "14", not "1" and "0").
**Why it happens:** BO1 matches show the map round score in the `.team1-gradient .won`/`.lost` divs, not a "maps won" count.
**How to avoid:** Set `best_of=1` and use the `.won`/`.lost` values as-is for `team1_score`/`team2_score`. For the `maps` table, `map_number=1`, and the map-level scores come from the mapholder.
**Warning signs:** BO1 match stored with team1_score=16 when it should represent "maps won" -- actually this IS correct for BO1 since HLTV shows round scores in the team gradient for BO1s. Verified: match 2366498 shows 16/14 in `.won`/`.lost`.

**CORRECTION (verified against HTML):** For BO1 matches, the `.team1-gradient .won` div shows the round score (e.g., 16), NOT a "1" for maps won. This is different from BO3/BO5 where `.won` shows maps won (e.g., 2). The `matches.team1_score`/`team2_score` columns store "maps won by team" per the schema comments. For BO1, this should be 1 and 0 (since one team wins the single map). The actual round scores go in the `maps` table. Parser must handle this difference.

### Pitfall 5: Missing Schema for Vetoes and Rosters
**What goes wrong:** Parser extracts veto and roster data but has nowhere to store it.
**Why it happens:** The initial schema (001) has `matches`, `maps`, `player_stats`, `round_history`, `economy` -- but no `vetoes` or `match_players` tables.
**How to avoid:** Create a new migration (003) adding `vetoes` and `match_players` tables. Add corresponding UPSERT SQL and repository methods.
**Warning signs:** Data extracted by parser but silently discarded.

### Pitfall 6: Unplayed Maps in Sweeps
**What goes wrong:** Parser tries to extract stats links or half scores from unplayed maps (map 3 in a 2-0 BO3 sweep).
**Why it happens:** Unplayed map holders have `.optional` class, score text "-", and no stats link.
**How to avoid:** Check for `.optional` class or score text == "-" before extracting map details. Store unplayed maps with null scores and null mapstatsid to preserve map pool context (per CONTEXT.md decision).
**Warning signs:** ValueError when parsing "-" as integer; null mapstatsid errors.

### Pitfall 7: Scrape Queue Status Progression
**What goes wrong:** Matches are fetched and parsed but the scrape_queue status stays 'pending', causing re-processing on next run.
**Why it happens:** No method exists on DiscoveryRepository to update status from 'pending' to 'scraped' or 'failed'.
**How to avoid:** Add `update_status(match_id, status)` method to DiscoveryRepository. Call it after successful parse ('scraped') or on unrecoverable error ('failed').
**Warning signs:** Same matches re-processed every run; scrape_queue count_pending never decreases.

## Code Examples

### Example 1: Match Metadata Extraction
```python
# Verified against 9 real HTML samples
import re
from bs4 import BeautifulSoup

def _extract_match_metadata(soup: BeautifulSoup) -> dict:
    """Extract match-level metadata from the overview page."""
    # Team names
    team1_name = soup.select_one('.team1-gradient .teamName').text.strip()
    team2_name = soup.select_one('.team2-gradient .teamName').text.strip()

    # Team IDs from href: /team/{id}/{slug}
    t1_href = soup.select_one('.team1-gradient a[href*="/team/"]')['href']
    t2_href = soup.select_one('.team2-gradient a[href*="/team/"]')['href']
    team1_id = int(re.search(r'/team/(\d+)/', t1_href).group(1))
    team2_id = int(re.search(r'/team/(\d+)/', t2_href).group(1))

    # Series scores -- may be absent on full forfeit
    won_el = soup.select_one('.team1-gradient .won')
    lost_el = soup.select_one('.team1-gradient .lost')
    if won_el:
        team1_score = int(won_el.text.strip())
    elif lost_el:
        team1_score = int(lost_el.text.strip())
    else:
        team1_score = None  # Full forfeit

    won_el = soup.select_one('.team2-gradient .won')
    lost_el = soup.select_one('.team2-gradient .lost')
    if won_el:
        team2_score = int(won_el.text.strip())
    elif lost_el:
        team2_score = int(lost_el.text.strip())
    else:
        team2_score = None  # Full forfeit

    # Date (unix milliseconds)
    date_el = soup.select_one('.timeAndEvent .date[data-unix]')
    date_unix_ms = int(date_el['data-unix'])

    # Event
    event_a = soup.select_one('.timeAndEvent .event a[href*="/events/"]')
    event_name = event_a.text.strip()
    event_id = int(re.search(r'/events/(\d+)/', event_a['href']).group(1))

    # Format: "Best of N (LAN|Online)"
    fmt_el = soup.select_one('.padding.preformatted-text')
    fmt_text = fmt_el.text.strip()
    fmt_match = re.search(r'Best of (\d+) \((LAN|Online)\)', fmt_text)
    best_of = int(fmt_match.group(1)) if fmt_match else 1
    is_lan = 1 if (fmt_match and fmt_match.group(2) == 'LAN') else 0

    return {
        'team1_name': team1_name, 'team2_name': team2_name,
        'team1_id': team1_id, 'team2_id': team2_id,
        'team1_score': team1_score, 'team2_score': team2_score,
        'date_unix_ms': date_unix_ms,
        'event_name': event_name, 'event_id': event_id,
        'best_of': best_of, 'is_lan': is_lan,
    }
```

### Example 2: Map Holder Extraction
```python
# Verified against 9 real HTML samples
def _extract_maps(soup: BeautifulSoup, match_id: int) -> list[dict]:
    """Extract per-map data from map holders."""
    maps = []
    for i, mh in enumerate(soup.select('.mapholder'), start=1):
        map_name = mh.select_one('.mapname').text.strip()
        is_unplayed = mh.select_one('.optional') is not None
        is_forfeit_map = (map_name == 'Default')

        # Scores
        score_left = mh.select_one('.results-left .results-team-score')
        score_right = mh.select_one('.results-right .results-team-score')

        if is_unplayed:
            team1_rounds = None
            team2_rounds = None
        else:
            team1_rounds = int(score_left.text.strip()) if score_left else None
            team2_rounds = int(score_right.text.strip()) if score_right else None

        # MapStatsID (only on played, non-forfeit maps)
        stats_link = mh.select_one('a.results-stats[href]')
        mapstatsid = None
        if stats_link:
            m = re.search(r'/mapstatsid/(\d+)/', stats_link['href'])
            if m:
                mapstatsid = int(m.group(1))

        # Half scores (CT/T breakdown) -- only for played, non-forfeit maps
        team1_ct = None
        team1_t = None
        team2_ct = None
        team2_t = None
        if not is_unplayed and not is_forfeit_map:
            hs_el = mh.select_one('.results-center-half-score')
            if hs_el:
                # Parse spans with ct/t classes for regulation halves
                # (overtime spans lack ct/t classes -- handled separately)
                pass  # Detailed parsing in implementation

        maps.append({
            'match_id': match_id,
            'map_number': i,
            'mapstatsid': mapstatsid,
            'map_name': map_name,
            'team1_rounds': team1_rounds,
            'team2_rounds': team2_rounds,
            'team1_ct_rounds': team1_ct,
            'team1_t_rounds': team1_t,
            'team2_ct_rounds': team2_ct,
            'team2_t_rounds': team2_t,
            'is_unplayed': is_unplayed,
            'is_forfeit_map': is_forfeit_map,
        })
    return maps
```

### Example 3: Veto Sequence Extraction
```python
# Verified against 9 real HTML samples
def _extract_vetoes(soup: BeautifulSoup) -> list[dict] | None:
    """Extract veto sequence from second veto box."""
    veto_boxes = soup.select('.veto-box')
    if len(veto_boxes) < 2:
        return None

    veto_div = veto_boxes[1]
    lines = veto_div.select('.padding > div')
    if not lines:
        return None

    vetoes = []
    for line in lines:
        text = line.text.strip()
        # Pattern: "1. G2 removed Nuke" or "3. G2 picked Mirage" or "7. Anubis was left over"
        m_remove = re.match(r'(\d+)\. (.+) removed (.+)', text)
        m_pick = re.match(r'(\d+)\. (.+) picked (.+)', text)
        m_left = re.match(r'(\d+)\. (.+) was left over', text)

        if m_remove:
            vetoes.append({
                'step': int(m_remove.group(1)),
                'team': m_remove.group(2),
                'action': 'removed',
                'map_name': m_remove.group(3),
            })
        elif m_pick:
            vetoes.append({
                'step': int(m_pick.group(1)),
                'team': m_pick.group(2),
                'action': 'picked',
                'map_name': m_pick.group(3),
            })
        elif m_left:
            vetoes.append({
                'step': int(m_left.group(1)),
                'team': None,  # No team for "left over"
                'action': 'left_over',
                'map_name': m_left.group(2),
            })

    return vetoes if vetoes else None
```

### Example 4: Player Roster Extraction
```python
# Verified against 9 real HTML samples
def _extract_rosters(soup: BeautifulSoup) -> list[dict]:
    """Extract player rosters from lineup blocks."""
    players = []
    lineups = soup.select('.lineups .lineup.standard-box')

    for team_num, lineup in enumerate(lineups, start=1):
        # Team info from lineup header
        team_a = lineup.select_one('.box-headline a.text-ellipsis')
        team_id_href = team_a['href'] if team_a else None
        team_id = None
        if team_id_href:
            m = re.search(r'/team/(\d+)/', team_id_href)
            if m:
                team_id = int(m.group(1))

        # Players with data-player-id
        player_els = lineup.select('[data-player-id]')
        for p_el in player_els:
            player_id = int(p_el['data-player-id'])
            name_el = p_el.select_one('.text-ellipsis')
            player_name = name_el.text.strip() if name_el else None

            players.append({
                'player_id': player_id,
                'player_name': player_name,
                'team_id': team_id,
                'team_num': team_num,  # 1 or 2
            })

    return players
```

### Example 5: Half-Score Parsing
```python
# Verified against match-2384993 (overtime) and match-2389951 (normal)
def _parse_half_scores(hs_el) -> dict:
    """Parse half-score spans into structured CT/T round breakdowns.

    Returns dict with keys: team1_ct, team1_t, team2_ct, team2_t,
    plus ot_team1 and ot_team2 for overtime totals.
    """
    spans = hs_el.select('span')

    # Extract numeric values with their side class
    scored_values = []
    for s in spans:
        text = s.text.strip()
        if text and text not in ('(', ')', ';', ':', ''):
            try:
                val = int(text)
                classes = s.get('class', [])
                side = None
                if 'ct' in classes:
                    side = 'ct'
                elif 't' in classes:
                    side = 't'
                scored_values.append((val, side))
            except ValueError:
                continue

    # Regulation: first 4 values have ct/t classes
    # team1_half1, team2_half1, team1_half2, team2_half2
    # Overtime: remaining values lack ct/t classes
    result = {
        'team1_ct': None, 'team1_t': None,
        'team2_ct': None, 'team2_t': None,
        'ot_team1': 0, 'ot_team2': 0,
    }

    if len(scored_values) >= 4:
        # Half 1: positions 0,1 (team1_half1_side, team2_half1_side)
        # Half 2: positions 2,3 (team1_half2_side, team2_half2_side)
        h1_t1_val, h1_t1_side = scored_values[0]
        h1_t2_val, h1_t2_side = scored_values[1]
        h2_t1_val, h2_t1_side = scored_values[2]
        h2_t2_val, h2_t2_side = scored_values[3]

        if h1_t1_side == 'ct':
            result['team1_ct'] = h1_t1_val
            result['team1_t'] = h2_t1_val
            result['team2_t'] = h1_t2_val
            result['team2_ct'] = h2_t2_val
        elif h1_t1_side == 't':
            result['team1_t'] = h1_t1_val
            result['team1_ct'] = h2_t1_val
            result['team2_ct'] = h1_t2_val
            result['team2_t'] = h2_t2_val

        # Overtime values (pairs without side classes, index 4+)
        ot_values = scored_values[4:]
        for j in range(0, len(ot_values), 2):
            if j + 1 < len(ot_values):
                result['ot_team1'] += ot_values[j][0]
                result['ot_team2'] += ot_values[j + 1][0]

    return result
```

## Schema Additions Required

The current database schema (migrations 001 + 002) does not have tables for vetoes or match-level rosters. Phase 5 needs a new migration.

### Missing Table: vetoes
**Purpose:** Store the ordered veto sequence for each match (7 steps per match for all formats).
```sql
CREATE TABLE IF NOT EXISTS vetoes (
    match_id    INTEGER NOT NULL REFERENCES matches(match_id),
    step_number INTEGER NOT NULL,       -- 1-7
    team_name   TEXT,                   -- Team performing action (NULL for "left over")
    action      TEXT NOT NULL,          -- "removed", "picked", "left_over"
    map_name    TEXT NOT NULL,          -- Map being acted upon
    scraped_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    source_url  TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, step_number)
);
```

### Missing Table: match_players
**Purpose:** Store the 10-player roster per match (separate from per-map `player_stats` which is populated in Phase 6).
```sql
CREATE TABLE IF NOT EXISTS match_players (
    match_id    INTEGER NOT NULL REFERENCES matches(match_id),
    player_id   INTEGER NOT NULL,       -- HLTV player ID
    player_name TEXT,                   -- Nickname at time of match
    team_id     INTEGER,               -- Which team (team1 or team2)
    scraped_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    source_url  TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, player_id)
);
```

**Confidence:** HIGH -- verified that current schema has no place for this data.

### DiscoveryRepository Additions Needed
**Purpose:** Pull pending matches from queue and update status after processing.
```python
# Methods needed on DiscoveryRepository:
def get_pending_matches(self, limit: int) -> list[dict]:
    """Return pending queue entries for processing."""
    rows = self.conn.execute(
        "SELECT * FROM scrape_queue WHERE status = 'pending' "
        "ORDER BY match_id LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]

def update_status(self, match_id: int, status: str) -> None:
    """Update queue entry status to 'scraped' or 'failed'."""
    with self.conn:
        self.conn.execute(
            "UPDATE scrape_queue SET status = ? WHERE match_id = ?",
            (status, match_id),
        )
```

## Data Flow: Phase 4 Output to Phase 5 Input

### What Phase 4 Produces
- `scrape_queue` table with `match_id`, `url` (relative), `is_forfeit`, `status='pending'`
- Results page HTML archived under `data/raw/results/`

### What Phase 5 Consumes
- `scrape_queue` entries with `status='pending'` -- provides match_id and URL
- `is_forfeit` flag from discovery -- informs whether to expect forfeit-specific handling

### What Phase 5 Produces
- `matches` table rows (match metadata: teams, scores, event, format, LAN/online, date)
- `maps` table rows (per-map: map name, scores, mapstatsid, half breakdowns)
- `vetoes` table rows (7 veto steps per match with team attribution)
- `match_players` table rows (10 players per match with team assignment)
- Raw HTML archived as `data/raw/matches/{match_id}/overview.html.gz`
- `scrape_queue.status` updated to 'scraped' or 'failed'

### What Phase 6 Consumes
- `maps.mapstatsid` values -- URLs for per-map stats pages
- `matches.match_id` -- parent match reference
- `match_players` -- roster for cross-referencing player IDs

## Parser Return Type Design

The parser should return a single structured result object containing all extracted data:

```python
@dataclass
class VetoStep:
    step_number: int
    team_name: str | None   # None for "left over"
    action: str             # "removed", "picked", "left_over"
    map_name: str

@dataclass
class MapResult:
    map_number: int         # 1-based
    map_name: str
    mapstatsid: int | None  # None for forfeit/unplayed maps
    team1_rounds: int | None
    team2_rounds: int | None
    team1_ct_rounds: int | None
    team1_t_rounds: int | None
    team2_ct_rounds: int | None
    team2_t_rounds: int | None
    is_unplayed: bool
    is_forfeit_map: bool

@dataclass
class PlayerEntry:
    player_id: int
    player_name: str
    team_id: int
    team_num: int           # 1 or 2

@dataclass
class MatchOverview:
    match_id: int
    team1_name: str
    team2_name: str
    team1_id: int
    team2_id: int
    team1_score: int | None   # None on full forfeit
    team2_score: int | None
    best_of: int              # 1, 3, or 5
    is_lan: int               # 0 or 1
    date_unix_ms: int
    event_id: int
    event_name: str
    maps: list[MapResult]
    vetoes: list[VetoStep] | None   # None if unparseable
    players: list[PlayerEntry]
    is_forfeit: bool          # Full match forfeit
```

## Orchestrator Design

### Fetch-Parse-Store Flow
Per CONTEXT.md: "Fetch-first batching: fetch N overview pages and store raw HTML, then parse the batch."

```
1. Get batch of pending match_ids from scrape_queue (N at a time)
2. For each match in batch:
   a. Build URL: config.base_url + queue_entry.url
   b. Fetch via client.fetch(url)
   c. Save raw HTML via storage.save(html, match_id, "overview")
3. After all fetches succeed, parse the batch:
   a. For each saved HTML:
      - Load from storage
      - Parse via parse_match_overview(html, match_id)
      - Convert to DB dicts
      - Upsert via repository (match + maps + vetoes + players)
      - Update scrape_queue status to 'scraped'
4. On fetch failure mid-batch: discard partial batch (per CONTEXT.md)
```

### Batch Size Considerations
- Default rate limit: 3-8 seconds between requests
- Each overview page is a single fetch
- Reasonable batch size: 10-20 matches per batch
- Batch too large = risk of Cloudflare block mid-batch with all work discarded
- Batch too small = excessive overhead from queue queries

**Recommendation:** Default batch_size=10, configurable via ScraperConfig.

### Error Handling Strategy
| Error Type | Action | Queue Status |
|-----------|--------|--------------|
| Cloudflare challenge (retried, still fails) | Abort entire batch | Keep 'pending' |
| Page not found (404) | Skip match, continue batch | Set 'failed' |
| Parse error (unexpected HTML structure) | Log error, skip match | Set 'failed' |
| "Match deleted" page | Store partial data, mark as deleted | Set 'scraped' (with forfeit data) |
| Database error | Abort batch, raise | Keep 'pending' |

## BO1 Score Handling

**Verified finding (HIGH confidence):** BO1 matches show MAP-LEVEL round scores in `.team1-gradient .won`/`.lost` (e.g., 16 and 14), not series-level "maps won" counts.

For BO3/BO5, `.won`/`.lost` show series-level scores (e.g., 2 and 1).

**Recommended handling:**
- For the `matches` table: `team1_score` and `team2_score` should store "maps won" for consistency. For BO1: winner gets 1, loser gets 0.
- For the `maps` table: `team1_rounds` and `team2_rounds` store the actual round scores from the mapholder.
- The `.won`/`.lost` values from team gradients can be stored directly for BO3/BO5 but need translation for BO1.

**Alternative (simpler):** Store the raw `.won`/`.lost` values as-is. For BO1 this means team1_score=16, team2_score=14. This preserves the original data. The `best_of` column distinguishes the semantics. This approach avoids a special case in the parser.

**Recommendation for planner:** Decide in PLAN.md which approach to use. Both are valid.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| curl_cffi for fetching | nodriver (real Chrome) | Phase 1 (deviation) | All fetching uses nodriver; no change for Phase 5 |
| Separate entity tables | Inline IDs + names | Phase 2 (decision) | Team/player names stored at time of match |
| Manual retry logic | tenacity decorators | Phase 1 | HLTVClient.fetch() handles all retry logic |

**Deprecated/outdated:**
- Nothing deprecated since Phase 4 was just completed.

## Selector Verification Matrix

All selectors verified against 9 real HTML samples (HIGH confidence):

| Selector | Sample Coverage | Status |
|----------|----------------|--------|
| `.team1-gradient .teamName` | 9/9 | Verified |
| `.team2-gradient .teamName` | 9/9 | Verified |
| `.team1-gradient a[href*="/team/"]` | 9/9 | Verified |
| `.team1-gradient .won` / `.lost` | 7/9 (absent on forfeit 2380434, present on partial forfeit 2384993) | Verified |
| `.timeAndEvent .date[data-unix]` | 9/9 | Verified |
| `.timeAndEvent .event a[href*="/events/"]` | 9/9 | Verified |
| `.padding.preformatted-text` | 9/9 | Verified |
| `.mapholder` | 9/9 (1 for BO1, 3 for BO3, 5 for BO5) | Verified |
| `.mapholder .mapname` | 9/9 | Verified |
| `.mapholder a.results-stats[href]` | 7/9 (absent on forfeit/unplayed maps) | Verified |
| `.results-center-half-score` span classes | 9/9 | Verified |
| `.veto-box` (2 per page) | 9/9 | Verified |
| `[data-player-id]` | 9/9 (10 per match, including forfeits) | Verified |
| `.lineups .teamRanking a` | 7/9 (0 elements on 2366498 both unranked) | Verified |

## Open Questions

### 1. BO1 team1_score/team2_score semantics
- **What we know:** BO1 `.won`/`.lost` show round scores (16/14), BO3/BO5 show maps won (2/1)
- **What's unclear:** Should `matches.team1_score` always mean "maps won" (requiring BO1 translation to 1/0) or store raw values?
- **Recommendation:** Planner decides. Both approaches are defensible. Storing raw values is simpler. Storing "maps won" is more consistent.

### 2. Overtime half-score storage
- **What we know:** The `maps` table has `team1_ct_rounds` and `team1_t_rounds` columns, which only cover regulation. OT rounds are extra.
- **What's unclear:** Where do overtime half-score breakdowns go?
- **Recommendation:** Sum regulation + OT into the existing columns (total CT rounds, total T rounds). The per-round detail comes from Phase 6's round_history table. Or, store only regulation in the ct/t columns and let total rounds (team1_rounds, team2_rounds) capture the full score including OT. The latter is simpler and consistent -- the ct/t columns represent regulation-only sides. Phase 6 provides the detailed per-round breakdown.

### 3. Match-level vs map-level player data
- **What we know:** Match overview has a roster (10 players per match). player_stats table is keyed (match_id, map_number, player_id) -- per-map data from Phase 6.
- **What's unclear:** Whether match_players table is needed, or if Phase 6 will always populate player_stats for all players.
- **Recommendation:** Create match_players table. It captures the roster even for forfeit matches (which have no per-map stats). It also provides the definitive team assignment before map-specific data is available.

## Sources

### Primary (HIGH confidence)
- `.planning/phases/03-page-reconnaissance/recon/match-overview.md` -- 678-line selector map verified against 9 HTML samples
- `.planning/phases/03-page-reconnaissance/recon/cross-page-summary.md` -- canonical field source mapping
- `.planning/phases/03-page-reconnaissance/recon/edge-cases.md` -- 532-line edge case reference
- `data/recon/match-2389951-overview.html.gz` -- Vitality vs G2, BO3 tier-1 LAN (verified live)
- `data/recon/match-2380434-overview.html.gz` -- Full forfeit match (verified live)
- `data/recon/match-2384993-overview.html.gz` -- BO5 partial forfeit + overtime (verified live)
- `data/recon/match-2366498-overview.html.gz` -- BO1 overtime, unranked teams (verified live)
- `src/scraper/repository.py` -- existing MatchRepository pattern (read for architecture)
- `src/scraper/discovery.py` -- existing parser pattern (read for architecture)
- `migrations/001_initial_schema.sql` -- existing DB schema (read for gap analysis)

### Secondary (MEDIUM confidence)
- None needed -- all findings verified against primary sources.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all tools already in project, no new dependencies
- Architecture: HIGH -- follows exact patterns established in Phases 1-4
- Selectors: HIGH -- verified against 9 real HTML samples via BeautifulSoup
- Schema gaps: HIGH -- verified by reading current migration files
- Pitfalls: HIGH -- derived from real HTML structure analysis
- BO1 score semantics: MEDIUM -- verified the DOM values, but storage policy is a design choice

**Research date:** 2026-02-15
**Valid until:** Indefinite (HLTV page structure is the only external dependency; selector maps were just verified)
