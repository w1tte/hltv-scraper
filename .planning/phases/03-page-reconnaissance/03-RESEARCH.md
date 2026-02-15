# Phase 3: Page Reconnaissance - Research

**Researched:** 2026-02-15
**Domain:** HLTV HTML page structure analysis, CSS selector mapping, edge case documentation
**Confidence:** MEDIUM (selector details are from reference projects; live page inspection needed for verification)

## Summary

Phase 3 is a documentation-only phase: no production code is written. The output is a set of selector maps and structural analysis documents that downstream parser phases (4-7) will consume directly. The work involves fetching sample HTML pages using the existing `HLTVClient`, inspecting them to extract CSS selectors, documenting field-by-field extraction paths, and cataloguing structural variations across match formats and rating versions.

The research focused on: (1) known HLTV CSS class names from the mature gigobyte/HLTV Node.js scraper, (2) HLTV Rating 3.0 vs 2.0/2.1 differences with specific field changes, (3) structural variations for BO1/BO3/BO5, overtime, and forfeit matches, (4) best practices for building durable CSS selector maps, and (5) how to use the existing nodriver-based `HLTVClient` for page inspection.

**Primary recommendation:** Use the existing `HLTVClient` to fetch 5-6 sample matches, save HTML with `HtmlStorage`, then analyze saved HTML locally with BeautifulSoup (lxml parser) to produce selector maps. The gigobyte/HLTV project's selectors provide a strong starting reference but must be verified against current live pages, especially post-Rating 3.0.

## Standard Stack

### Core (for this documentation phase only)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| beautifulsoup4 | 4.14.x | Parse saved HTML files for selector discovery | Industry standard for HTML parsing; `.select()` with CSS selectors |
| lxml | latest | HTML parser backend for BeautifulSoup | 10x faster parsing than default html.parser |

### Already Available (from Phase 1-2)

| Library | Purpose | How Used in Phase 3 |
|---------|---------|---------------------|
| nodriver | Fetch sample pages through Cloudflare | `HLTVClient.fetch()` to get live HTML |
| gzip (stdlib) | Decompress saved HTML | `HtmlStorage.load()` reads .html.gz files |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BeautifulSoup | parsel (Scrapy) | Parsel has better CSS selector support, but BS4 is more widely known and adequate for inspection |
| BeautifulSoup | nodriver DOM methods | nodriver's `tab.select()` works but requires live browser; BS4 works offline on saved HTML |
| Manual inspection | Browser DevTools | DevTools are interactive but not scriptable; BS4 allows systematic extraction |

**Installation:**
```bash
pip install beautifulsoup4 lxml
```

**Note:** These are development/analysis dependencies only. They may or may not be needed in production parsers (that decision is for Phases 5-7). For Phase 3 they are tools for the human/agent doing the analysis.

## Architecture Patterns

### Phase 3 Output Structure

```
.planning/phases/03-page-reconnaissance/
  03-CONTEXT.md                    # Already exists
  03-RESEARCH.md                   # This file
  03-01-PLAN.md ... 03-07-PLAN.md  # Plan files
  recon/                           # Documentation outputs
    results-listing.md             # Selector map for /results pages
    match-overview.md              # Selector map for /matches/{id}/{slug}
    map-stats.md                   # Selector map for /stats/matches/mapstatsid/{id}/{slug}
    map-performance.md             # Selector map for performance sub-page
    map-economy.md                 # Selector map for economy sub-page
    cross-page-summary.md          # Data overlap map across all page types
    edge-cases.md                  # BO1/BO3/BO5, overtime, forfeits, rating versions
```

### Pattern 1: Sample-First Analysis

**What:** Fetch and save representative HTML samples before any analysis begins. All selector discovery works against saved HTML, never against live pages.

**When to use:** Always -- this is the core workflow for the entire phase.

**Why:** (1) Avoids repeated live fetches that risk Cloudflare blocks, (2) creates a reproducible artifact for verification, (3) allows offline analysis without network dependency.

**Workflow:**
```
1. HLTVClient.fetch(url) -> raw HTML string
2. Save to data/recon/{descriptive-name}.html.gz (temporary, not committed)
3. Load with gzip.decompress() -> feed to BeautifulSoup
4. Inspect DOM tree, document selectors in markdown
5. Delete sample HTML after analysis (per CONTEXT.md: not committed to repo)
```

### Pattern 2: Selector Map Format

**What:** Each page type gets a markdown document with a consistent field-by-field table.

**Format per field:**
```markdown
| Field | CSS Selector | Data Type | Required | Example Value | Notes |
|-------|-------------|-----------|----------|---------------|-------|
| team1_name | .team1-gradient .teamName | string | always | "FaZe" | Text content |
| team1_id | .team1-gradient a[href] | int | always | 6667 | Parse from href="/team/6667/faze" |
| match_date | .timeAndEvent .date[data-unix] | unix_ms | always | 1707346800000 | data-unix attribute, divide by 1000 |
```

**Include for ALL fields:**
- CSS selector path (primary)
- Fallback selector if applicable
- Data type (string, int, float, unix_ms, boolean, enum)
- Optionality: always / sometimes / never (with conditions)
- Example value from a real page
- Notes on parsing (regex needed, attribute vs text, format variations)
- Whether we extract this field (yes/skip/future)

### Pattern 3: Annotated HTML Snippets

**What:** Include actual HTML fragments showing the DOM structure around key data points.

**Example:**
```html
<!-- Match overview: team container -->
<div class="team1-gradient">
  <a href="/team/6667/faze">
    <div class="teamName">FaZe</div>
  </a>
  <div class="teamRanking">
    <a href="/ranking/teams/...">#3</a>
  </div>
</div>
```

This makes selector paths concrete and helps parser developers understand DOM context.

### Anti-Patterns to Avoid

- **Testing selectors only against one sample:** HLTV's HTML varies across eras and match types. Test every selector against multiple samples.
- **Relying on positional selectors (nth-child):** These break when HLTV adds/removes elements. Prefer class-based selectors.
- **Ignoring data attributes:** HLTV uses `data-unix`, `data-fusionchart-config`, `data-player-id`, `data-highlight-embed` -- these are more stable than text parsing.
- **Documenting only fields we plan to extract:** CONTEXT.md explicitly requires documenting ALL visible fields, marking which are extracted vs skipped.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML parsing | Custom regex on raw HTML | BeautifulSoup with lxml | HTML is not regular; regex breaks on edge cases |
| Sample page fetching | New fetch logic | Existing `HLTVClient` | Already handles Cloudflare, rate limiting, retries |
| Sample page storage | New file saving | `HtmlStorage` (for match pages) or simple gzip write (for results pages) | Phase 2 already built this |
| CSS selector testing | Manual browser inspection only | Programmatic BS4 `.select()` verification | Scriptable, reproducible, catches selector errors |

**Key insight:** This phase produces documentation, not code. The temptation to start writing parsers must be resisted -- the goal is to build the knowledge base that makes parser writing fast and correct in Phases 4-7.

## Common Pitfalls

### Pitfall 1: Fetching Too Many Pages and Getting Blocked

**What goes wrong:** Enthusiastic sample collection triggers Cloudflare escalation.
**Why it happens:** Fetching 30+ pages in one session without sufficient pacing.
**How to avoid:** Fetch samples in small batches (5-8 per session). Use the existing rate limiter (3-8s between requests). Plan for 2-3 collection sessions, not one big run.
**Warning signs:** Cloudflare challenge count increasing in `client.stats`, response sizes shrinking, "Just a moment" in page titles.

### Pitfall 2: Selector Map Based on Single Era

**What goes wrong:** Selectors work for 2025 pages but fail on 2023-2024 pages.
**Why it happens:** HLTV has updated their CSS classes and page structure over time. Rating 3.0 (August 2025) changed scoreboard fields.
**How to avoid:** Sample from 3 distinct eras: late 2023, mid 2024, recent 2025-2026. Document any selector differences by era.
**Warning signs:** A selector returns results on some samples but not others.

### Pitfall 3: Confusing Rating Versions

**What goes wrong:** Parser assumes all pages have the same stat columns.
**Why it happens:** Rating 2.0/2.1 pages have different fields than Rating 3.0 pages (August 2025+). Rating 3.0 was retroactively applied to historical data in October 2025.
**How to avoid:** Document explicit detection logic for rating version. Check for presence of eco-adjusted toggles/fields (eK-eD, eADR, eKAST) as a Rating 3.0 indicator.
**Warning signs:** Missing "Impact" column (removed in 3.0), presence of "Round Swing" column (added in 3.0).

### Pitfall 4: Missing Forfeit/Walkover Edge Cases

**What goes wrong:** Parser crashes on forfeit matches because expected elements are absent.
**Why it happens:** Forfeit matches have no map stats, no round history, no player stats -- most of the page is empty.
**How to avoid:** Fetch at least one confirmed forfeit/walkover match and document exactly which elements are present vs. missing.
**Warning signs:** Very short page HTML, missing `.stats-table` or `.round-history-team-row` elements.

### Pitfall 5: Overtime Round History Not Fitting Standard Layout

**What goes wrong:** Round history parser assumes 24 rounds (12 per half in MR12).
**Why it happens:** CS2 overtime adds 6 rounds per OT period (3 per side). The round history bar (`.round-history-bar`) separates regulation halves but OT periods may have different separators.
**How to avoid:** Fetch at least one overtime match and document how extra rounds appear in the round history DOM. Note the M80 vs fnatic octuple overtime (71 rounds) as an extreme case.
**Warning signs:** Round counts > 24 in `.round-history-outcome` elements.

### Pitfall 6: HtmlStorage Doesn't Support Results Pages

**What goes wrong:** Trying to save results listing pages with `HtmlStorage.save()` fails.
**Why it happens:** Phase 2 decision: `HtmlStorage` supports only 4 match-page types (`overview`, `map_stats`, `map_performance`, `map_economy`). Results pages were deferred to Phase 4.
**How to avoid:** Save results page samples with a simple gzip write to `data/recon/` directory, not through `HtmlStorage`. This is temporary analysis data anyway.
**Warning signs:** `ValueError: Unknown page_type 'results_listing'`.

## HLTV Page Types: Known Selectors Reference

These selectors are from the gigobyte/HLTV Node.js project (confidence: MEDIUM -- project is actively maintained but may lag behind HLTV's latest changes). **All must be verified against live pages during reconnaissance.**

### Results Listing (`/results?offset=N`)

| Element | Selector | Data | Notes |
|---------|----------|------|-------|
| Match entry | `.result-con` | Container | Each match is one entry |
| Featured matches | `.big-results .result-con` | Container | Promoted matches at top |
| Score | `.result-score` | "2 - 1" text | Split on " - " |
| Map/format | `.map-text` | "bo3" or map name | |
| Team name | `div.team` | Text | First = team1, last = team2 |
| Team logo | `img.team-logo` | `src` attribute | |
| Match date | `[data-zonedgrouping-entry-unix]` | Unix timestamp | Attribute on parent container |
| Star rating | `.stars i` | Count of `<i>` elements | 0-5 stars |
| Pagination | URL `?offset=N` | N increments by 100 | Continue while `.result-con` exists |

### Match Overview (`/matches/{match_id}/{slug}`)

| Element | Selector | Data | Notes |
|---------|----------|------|-------|
| Team 1 name | `.team1-gradient .teamName` | Text | |
| Team 2 name | `.team2-gradient .teamName` | Text | |
| Team 1 ID | `.team1-gradient a[href]` | Parse from href | `/team/{id}/{slug}` |
| Team 2 ID | `.team2-gradient a[href]` | Parse from href | |
| Winner | `.team1-gradient .won` or `.team2-gradient .won` | Presence | Class `.won` on winning team |
| Match date | `.timeAndEvent .date[data-unix]` | Unix ms | `data-unix` attribute |
| Event name | `.timeAndEvent .event a` | Text | |
| Event ID | `.timeAndEvent .event a[href]` | Parse from href | `/events/{id}/{slug}` |
| Map holder | `.mapholder` | Container | One per map in series |
| Map name | `.mapname` | Text | Inside `.mapholder` |
| Map score left | `.results-left .results-team-score` | Text | |
| Map score right | `.results-right .results-team-score` | Text | |
| Half scores | `.results-center-half-score` | "X:Y" pairs | CT/T halves |
| Map stats link | `.results-stats[href]` | `/stats/matches/mapstatsid/{id}/{slug}` | Extract mapstatsid |
| Veto box | `.veto-box` | Container | Old and new veto formats exist |
| Player containers | `div.players` | Container | Indexed by position (team) |
| Player name | `.text-ellipsis` | Text | Inside player flagAlign |
| Player ID | `[data-player-id]` | Attribute | On player element |
| Format/location | `.preformatted-text` | Text | Parse by line splits for BO format and LAN/online |
| Team ranking | `.teamRanking a` | Text | Contains "#N" |
| Streams | `.stream-box` | Container | Not needed for scraping |
| Head-to-head | `.head-to-head-listing tr` | Rows | Historical matches |

### Map Overview/Stats (`/stats/matches/mapstatsid/{id}/{slug}`)

| Element | Selector | Data | Notes |
|---------|----------|------|-------|
| Team 1 rounds | `.team-left .bold` | Text (int) | Total rounds won |
| Team 2 rounds | `.team-right .bold` | Text (int) | |
| Half results | `.match-info-row .right` | Text | |
| Match info | `.match-info-box` | Container | Metadata |
| Round history row | `.round-history-team-row` | Container | One per team |
| Round outcome | `.round-history-outcome` | Element | Per-round win/loss icon |
| Round history bar | `.round-history-bar` | Separator | Between halves |
| Stats table | `.stats-table.totalstats` | Table | First = team1, last = team2 |
| Player link | `.st-player a` | Name + href | |
| Kills | `.st-kills` | Text (int) | |
| Assists | `.st-assists` | Text (int) | |
| Deaths | `.st-deaths` | Text (int) | |
| K/D ratio | `.st-kdratio` | Text (float) | |
| K/D diff | `.st-kddiff` | Text (int) | |
| ADR | `.st-adr` | Text (float) | |
| FK diff | `.st-fkdiff` | Text (int) | First kills difference |
| Rating | `.st-rating` | Text (float) | Rating 2.0 or 3.0 depending on era |
| Rating label | `.ratingDesc` | Text | May indicate rating version |
| Stat leaders | `.most-x-box` | Container | Most kills, most damage, etc. |
| Overview table | `.overview-table tr` | Rows | Performance overview by team |
| Team 1 stats | `.team1-column` | Text | In overview table |
| Team 2 stats | `.team2-column` | Text | In overview table |
| Highlighted player | `.highlighted-player` | Container | Player performance graph |
| Performance graph | `.graph.small[data-fusionchart-config]` | JSON attribute | Chart data |

### Map Performance (`/stats/matches/performance/mapstatsid/{id}/{slug}`)

| Element | Selector | Data | Notes |
|---------|----------|------|-------|
| Stats table | `.stats-table` | Table | Player performance metrics |
| Overview table | `.overview-table` | Table | Performance overview rows |

**Known fields on performance page (confidence: MEDIUM):**
- KPR (Kills Per Round)
- DPR (Deaths Per Round)
- Impact rating (Rating 2.0/2.1) -- **removed in Rating 3.0, replaced by Round Swing**
- Opening kills / Opening deaths
- Opening kill rating
- Multi-kill rounds (2k, 3k, 4k, 5k counts)
- Clutch wins (1v1, 1v2, 1v3, etc.)
- **Rating 3.0 additions:** Round Swing, Multi-Kill Rating, eco-adjusted toggles (eK-eD, eADR, eKAST)

### Map Economy (`/stats/matches/economy/mapstatsid/{id}/{slug}`)

**Confidence: LOW** -- No reference project has detailed economy page selectors. Must be discovered from live page inspection.

**Expected fields:**
- Per-round equipment values for each team
- Buy type classifications per round (eco, force buy, full buy, pistol round)
- Round outcome alongside economy data
- Side information (CT/T) per round

## Rating Version Differences (Critical for RECON-04)

### Timeline

| Date | Event | Impact |
|------|-------|--------|
| June 2017 | Rating 2.0 launched | Added ADR, KAST, Impact, multi-kill/clutch metrics |
| Unknown | Rating 2.1 (minor update) | Incremental formula changes; no major field additions |
| August 20, 2025 | Rating 3.0 launched | Major field changes (see below) |
| October 29, 2025 | Rating 3.0 adjustments | Rebalanced weights; eco-adjusted toggle added to match pages |
| October 2025 | Retroactive application | All historical match data overwritten with 3.0 formula |

### Field Changes: 2.0/2.1 vs 3.0

| Aspect | Rating 2.0/2.1 | Rating 3.0 | Impact on Scraper |
|--------|----------------|------------|-------------------|
| Sub-ratings | Kill, Survival, KAST, Impact, Damage (5) | Kill, Survival, KAST, Multi-Kill, Damage, Round Swing (6) | Different column count in performance table |
| Impact Rating | Present (multi-kills + opening kills + clutches) | **Removed** -- split into Round Swing + Multi-Kill | Must detect absence of Impact column |
| Round Swing | Not present | **New** -- measures kill impact on round win probability | New column to extract |
| Multi-Kill Rating | Part of Impact | **Separate sub-rating** | New column to extract |
| Eco-adjusted stats | Not present | eK-eD, eADR, eKAST (toggle) | New optional columns; requires toggle interaction or data-attribute check |
| Rating column | `rating_2` (always labeled "Rating") | `rating_3` (may be labeled "Rating 3.0") | Label text or surrounding element may indicate version |

### Detection Strategy (Recommendation)

Since Rating 3.0 was retroactively applied (October 2025), **all current pages may show Rating 3.0 data regardless of match date**. However, the scraper should still detect which rating system is in use because:

1. HLTV may change this behavior in the future
2. The DB schema has separate `rating_2` and `rating_3` columns
3. Pre-August 2025 matches may show different column headers

**Proposed detection signals (to verify during reconnaissance):**
- Presence of "Round Swing" in performance table headers
- Presence of eco-adjusted toggle (eK-eD/eADR/eKAST)
- Absence of "Impact" column in traditional location
- Text content of `.ratingDesc` element
- Match date as fallback heuristic

## Edge Cases and Structural Variations

### BO1 vs BO3 vs BO5

| Feature | BO1 | BO3 | BO5 |
|---------|-----|-----|-----|
| Map holders (`.mapholder`) | 1 played | 3 visible (2-3 played) | 5 visible (3-5 played) |
| Veto steps | 6 bans, 1 remaining | 2 bans + 2 picks + 2 bans + 1 decider | 2 bans + 2 picks + remaining ordered |
| Map stats links | 1 | 2-3 | 3-5 |
| Unplayed maps | None | Show "TBD" or empty | Show "TBD" or empty |
| Typical series score | 1-0 | 2-0 or 2-1 | 3-0 to 3-2 |

### Overtime Matches

- **CS2 uses MR12:** regulation = 24 rounds (12 per half)
- **Overtime format:** 6 rounds per OT period (3 per side), team needs 4 OT round wins
- **Multiple OTs:** If 3-3 in OT, another 6-round period begins
- **Extreme case:** M80 vs fnatic played 71 rounds (octuple overtime on Anubis)
- **Round history DOM:** `.round-history-outcome` elements continue past 24; `.round-history-bar` separators may appear between OT halves
- **Half scores:** Additional half-score entries appear in `.results-center-half-score`
- **Total round count:** `team1_rounds + team2_rounds > 24` indicates overtime

### Forfeit / Walkover Matches

**Confidence: LOW** -- must be verified by fetching actual forfeit match pages.

**Expected characteristics:**
- Match overview page exists with team names, event, date
- Final score shows W/O or 0-0 or 1-0 without map stats
- No `.results-stats` links (no mapstatsid)
- No player stats, no round history, no economy data
- Veto section may be absent or show partial vetoes
- Page HTML will be shorter than typical match pages

**Sample to fetch:** The "Walkover vs FTW" match at PGL CS2 Major Copenhagen 2024 (`/matches/2368970/walkover-vs-ftw-...`) -- though this may be a team literally named "Walkover". Need to search for actual forfeit matches during Plan 03-01 sample selection.

### Showmatches / Exhibition

- Labeled as events under "Showmatch CS" on HLTV
- Examples: PGL Copenhagen 2024 Showmatch, StarLadder Budapest 2025 Showmatch
- May use mutators, non-standard rules (all 24 rounds played regardless)
- Page structure appears identical to regular matches
- Distinguishable by event name containing "Showmatch"

## Fetching Strategy for Sample Collection

### Session Planning

Given the rate limiter configuration (3-8s between requests), fetching 30-40 pages requires approximately:
- 30 pages x 6s avg delay = ~3 minutes pure wait time
- Plus page load time (~4s per page) = ~7 minutes pure overhead
- Total per session: ~10-15 minutes with some buffer

**Recommended approach:**
1. **Session 1:** Fetch results listing pages (3 offsets: 0, 100, 5000) + 5-6 match overview pages spanning eras
2. **Session 2:** Fetch map stats + performance + economy pages for the selected matches (3 pages per map x ~3-4 maps = 9-12 pages)
3. **Session 3:** Edge case matches (forfeit, overtime, BO5, showmatch) -- overview + any available stats pages

### Sample Match Selection Criteria

Choose matches covering:
- **Era diversity:** Late 2023, mid 2024, 2025, 2026
- **Format diversity:** BO1, BO3, at least one BO5
- **Tier diversity:** Major final, mid-tier LAN, online qualifier
- **Edge cases:** Overtime map, forfeit/walkover, showmatch
- **Rating version:** Pre-August 2025 (2.0/2.1) and post-August 2025 (3.0)

**Note on retroactive Rating 3.0:** Since HLTV retroactively applied Rating 3.0 to all matches (October 2025), even old matches may now show 3.0 columns. Reconnaissance must verify whether old matches still show 2.0/2.1 columns or if everything is now 3.0.

### Using HLTVClient for Sample Fetching

```python
import asyncio
import gzip
from pathlib import Path
from scraper.http_client import HLTVClient

async def fetch_samples():
    samples_dir = Path("data/recon")
    samples_dir.mkdir(parents=True, exist_ok=True)

    async with HLTVClient() as client:
        # Fetch a results page
        html = await client.fetch("https://www.hltv.org/results?offset=0")
        (samples_dir / "results-offset-0.html.gz").write_bytes(
            gzip.compress(html.encode("utf-8"))
        )

        # Fetch a match overview
        html = await client.fetch(
            "https://www.hltv.org/matches/2376513/faze-vs-natus-vincere-blast-premier-spring-final-2025"
        )
        (samples_dir / "match-2376513-overview.html.gz").write_bytes(
            gzip.compress(html.encode("utf-8"))
        )

        # ... etc for each sample
```

### Using BeautifulSoup for Offline Analysis

```python
import gzip
from bs4 import BeautifulSoup
from pathlib import Path

def analyze_page(filepath: Path):
    html = gzip.decompress(filepath.read_bytes()).decode("utf-8")
    soup = BeautifulSoup(html, "lxml")

    # Example: find all stat table rows
    for table in soup.select(".stats-table.totalstats"):
        for row in table.select("tr"):
            player = row.select_one(".st-player a")
            rating = row.select_one(".st-rating")
            if player and rating:
                print(f"{player.text.strip()}: {rating.text.strip()}")
```

## Roadmap Plan Assessment

The 7-plan breakdown from the roadmap is well-structured and should be retained:

| Plan | Scope | Assessment |
|------|-------|------------|
| 03-01 | Fetch and archive sample pages | Good -- foundational, must come first |
| 03-02 | Results listing analysis | Good -- self-contained page type |
| 03-03 | Match overview analysis | Good -- most complex page, deserves own plan |
| 03-04 | Map overview (stats) analysis | Good -- scoreboard + round history |
| 03-05 | Map performance analysis | Good -- Rating 2.0 vs 3.0 differences live here |
| 03-06 | Map economy analysis | Good -- least documented page type, needs careful exploration |
| 03-07 | Edge case + cross-page synthesis | Good -- synthesis must come last |

**Recommendation:** Keep the 7-plan breakdown. Each plan has clear scope and natural ordering (sample collection first, individual page analyses in parallel-ish order, synthesis last).

**Adjustment:** Plan 03-01 should include selecting specific match URLs based on the criteria above (era diversity, format diversity, edge cases). The plan should produce a manifest file listing which matches were fetched and why.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Rating 2.0 stats (Impact as single metric) | Rating 3.0 stats (Round Swing + Multi-Kill) | August 2025 | Performance page has different columns |
| No eco-adjustment | Eco-adjusted toggle (eK-eD, eADR, eKAST) | October 2025 | New optional data fields on scoreboard |
| MR15 round format (30 rounds) | MR12 round format (24 rounds) | September 2023 (CS2 launch) | All CS2 matches use MR12; overtime = 6 rounds per period |
| CS:GO era matches | CS2 era matches only | September 2023 | Scraper scope limited to CS2 |

**Deprecated/outdated:**
- Rating 1.0 (KPR/DPR/Impact only): replaced by 2.0 in 2017, irrelevant for CS2 era
- MR15 format: CS2 exclusively uses MR12
- curl_cffi HTTP client: replaced by nodriver in Phase 1 deviation

## Open Questions

1. **Rating 3.0 retroactive application scope**
   - What we know: HLTV retroactively applied Rating 3.0 to historical matches as of October 2025
   - What's unclear: Do old match pages now show 3.0-style columns (Round Swing instead of Impact), or do they retain the original column layout with recalculated values?
   - Recommendation: Verify by fetching a pre-August 2025 match during Plan 03-01 and comparing column headers to a post-August 2025 match

2. **Economy page detailed structure**
   - What we know: The page shows per-round equipment values and buy types
   - What's unclear: Exact CSS selectors, whether data is in a table or chart (FusionCharts?), how buy types are classified
   - Recommendation: This is the primary discovery target for Plan 03-06. No reference projects document this page well.

3. **Forfeit match HTML structure**
   - What we know: Forfeit matches exist on HLTV, likely have missing stats sections
   - What's unclear: Exactly which DOM elements are present vs absent on forfeit pages
   - Recommendation: Must fetch an actual forfeit match in Plan 03-01 to characterize

4. **Economy data availability for early CS2 matches**
   - What we know: STATE.md flags this as a concern from Phase 2 research
   - What's unclear: Whether late-2023 CS2 matches have economy data at all
   - Recommendation: Include a late-2023 match in samples and check if economy page returns meaningful data

5. **Eco-adjusted stats data location**
   - What we know: eK-eD, eADR, eKAST appear behind a toggle on match pages
   - What's unclear: Whether eco-adjusted data is in the initial HTML or loaded via JavaScript/AJAX after toggle interaction
   - Recommendation: Check initial page source for eco-adjusted values; if absent, they may require toggle interaction via nodriver

## Sources

### Primary (HIGH confidence)
- gigobyte/HLTV Node.js project (`src/endpoints/getMatch.ts`, `getMatchMapStats.ts`, `getResults.ts`) -- CSS selectors for match, stats, and results pages
- [HLTV: Introducing Rating 3.0](https://www.hltv.org/news/42485/introducing-rating-30) -- Rating 3.0 launch details, new metrics
- [HLTV: Rating 3.0 adjustments go live](https://www.hltv.org/news/43047/rating-30-adjustments-go-live) -- October 2025 adjustments, retroactive application, eco-adjusted toggle
- [HLTV: Introducing Rating 2.0](https://www.hltv.org/news/20695/introducing-rating-20) -- Rating 2.0 components (ADR, KAST, Impact)
- Existing codebase: `src/scraper/http_client.py`, `src/scraper/storage.py`, `src/scraper/config.py`

### Secondary (MEDIUM confidence)
- [CS2NEWS: HLTV tweaks Rating 3.0](https://cs2news.com/news/hltv-tweaks-rating-3.0-more-weight-on-kills-refined-round-swing-new-eco-adjusted-toggles) -- eco-adjusted toggle details
- [Dust2.in: Everything about Rating 3.0](https://www.dust2.in/news/64922/everything-you-need-to-know-about-hltvs-rating-30) -- Rating 3.0 overview
- [DMarket: MR12 in CS2](https://dmarket.com/blog/mr12-in-cs2/) -- MR12 format and overtime rules
- [CS2NEWS: StarLadder Budapest Major BO5 final](https://cs2news.com/news/starladder-budapest-major-2025-to-feature-best-of-five-final) -- BO5 format confirmation
- WebSearch: CSS selector best practices for web scraping -- durability and fallback patterns

### Tertiary (LOW confidence)
- Economy page structure -- no authoritative source found; must be discovered from live inspection
- Forfeit match DOM structure -- inferred from general knowledge; must be verified against actual pages
- HLTV showmatch page format -- inferred from event listings; structure assumed similar to regular matches

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- BeautifulSoup + lxml is well-established, nodriver already proven in Phase 1
- Known selectors reference: MEDIUM -- from gigobyte/HLTV project, actively maintained but may not reflect latest HLTV changes (especially post-Rating 3.0)
- Rating version differences: MEDIUM -- official HLTV announcements describe field changes but exact HTML impact needs verification
- Edge case documentation: LOW -- forfeit/overtime/BO5 structures are inferred, not verified from actual HTML
- Economy page structure: LOW -- no reference project documents this page type's selectors
- Architecture/workflow: HIGH -- follows naturally from Phase 1-2 patterns

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (30 days -- HLTV page structure changes infrequently, but Rating 3.0 adjustments are still settling)
