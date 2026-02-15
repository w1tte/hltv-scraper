# Consolidated Edge Case Reference

**Synthesized from:** results-listing.md, match-overview.md, map-stats.md, map-performance.md, map-economy.md
**Date:** 2026-02-15
**Purpose:** Single reference for parser developers covering all known edge cases across all page types

---

## Section 1: BO1 vs BO3 vs BO5 Structural Differences

### Map Holder Counts

| Format | `.mapholder` count | Played maps | Unplayed maps | Veto steps |
|--------|:-:|:-:|:-:|:-:|
| BO1 | 1 | 1 | 0 | 7 (6 bans, 1 left over) |
| BO3 (2-0 sweep) | 3 | 2 | 1 | 7 (2 bans, 2 picks, 2 bans, 1 left over) |
| BO3 (2-1 full) | 3 | 3 | 0 | 7 |
| BO5 (3-0) | 5 | 3 | 2 | 7 (2 bans, 4 picks, 1 left over) |
| BO5 (3-1) | 5 | 4 | 1 | 7 |
| BO5 (3-2 full) | 5 | 5 | 0 | 7 |

### Veto Structure by Format

**BO1 (7 steps, all bans):**
```
1. {team} removed {map}    -- ban
2. {team} removed {map}    -- ban
3. {team} removed {map}    -- ban
4. {team} removed {map}    -- ban
5. {team} removed {map}    -- ban
6. {team} removed {map}    -- ban
7. {map} was left over      -- decider
```

**BO3 (7 steps, 2 picks):**
```
1. {team} removed {map}    -- ban
2. {team} removed {map}    -- ban
3. {team} picked {map}     -- pick (map 1 or 2)
4. {team} picked {map}     -- pick (map 1 or 2)
5. {team} removed {map}    -- ban
6. {team} removed {map}    -- ban
7. {map} was left over      -- decider (map 3)
```

**BO5 (7 steps, 4 picks):**
```
1. {team} removed {map}    -- ban
2. {team} removed {map}    -- ban
3. {team} picked {map}     -- pick
4. {team} picked {map}     -- pick
5. {team} picked {map}     -- pick
6. {team} picked {map}     -- pick
7. {map} was left over      -- decider (map 5)
```

### Unplayed Maps

Unplayed maps (e.g., map 3 in a 2-0 BO3 sweep) have distinct DOM structure:

| Attribute | Played Map | Unplayed Map |
|-----------|-----------|-------------|
| Inner div class | `.played` | `.optional` |
| Results div class | `.results.played` | `.results.optional` |
| Score text | Numeric (e.g., "13") | "-" (dash) |
| Score div class | `.won` or `.lost` | `.tie` |
| Stats link | Present (`a.results-stats[href]`) | **Absent** |
| Half scores | Populated spans | **Empty** element |

**Parser handling:** Check for `.optional` class or score text == "-" to skip unplayed maps.

### Results Listing Format Encoding

The `.map-text` field on results listing encodes format differently:

| Value | Meaning |
|-------|---------|
| `bo3` | Best-of-3 series |
| `bo5` | Best-of-5 series |
| `nuke`, `ovp`, `mrg`, etc. | BO1 on specific map |
| `def` | Forfeit/default win |

**Parser logic:** If `bo3`/`bo5` -> series. If `def` -> forfeit. Otherwise -> BO1 map abbreviation.

### Performance/Economy Page Map Tabs

| Format | Performance page tabs | Economy page tabs |
|--------|----------------------|-------------------|
| BO1 | 0 tabs (`.stats-match-maps` empty) | 0 tabs |
| BO3 | 3-4 tabs (series overview + per-map) | Same |
| BO5 | Expected 5-6 tabs | Same |

**Parser impact:** Performance and economy pages are fetched per-mapstatsid, so tab navigation is not needed. The map tabs are informational only.

---

## Section 2: Overtime Matches

### Detection

An overtime match is detected when the total rounds played exceeds regulation:
- **MR12 format (current):** Regulation = 24 rounds. OT if total > 24.
- **MR15 format (pre-2024):** Regulation = 30 rounds. OT if total > 30.

Detection can be done at multiple points:
1. **Match overview:** Sum of half scores > 12 per half (MR12) or > 15 (MR15)
2. **Map stats:** Total `.round-history-outcome` count (excluding `emptyHistory`) > 24/30
3. **Map stats breakdown:** Third `()` group present in `.match-info-row .right`
4. **Economy:** FusionCharts round label count > 24/30

### Match Overview: Half Scores with OT

**Regulation only (no OT):**
```html
<div class="results-center-half-score">
  <span> (</span>
  <span class="ct">7</span><span>:</span><span class="t">5</span>
  <span>; </span>
  <span class="t">6</span><span>:</span><span class="ct">6</span>
  <span></span><span>)</span>
</div>
```

**With overtime:**
```html
<div class="results-center-half-score">
  <!-- Regulation halves (ct/t classes present) -->
  <span> (</span>
  <span class="ct">3</span><span>:</span><span class="t">9</span>
  <span>; </span>
  <span class="t">9</span><span>:</span><span class="ct">3</span>
  <span></span><span>)</span>
  <!-- OT period (NO ct/t classes) -->
  <span> (</span>
  <span>7</span><span>:</span><span>5</span>
  <span>)</span>
</div>
```

**Key difference:** Overtime spans lack `class="ct"` and `class="t"`. Parse all parenthesized groups and check for ct/t classes. Groups without classes are overtime periods.

### Map Stats: Round History DOM Structure

Three distinct patterns based on overtime length:

**Pattern 1: No overtime (10 of 12 samples)**
- 1 `.round-history-con` container
- 21-24 `.round-history-outcome` images per team row
- Headlines: "Round history", "Performance - rating X.X", "Players"

**Pattern 2: Single OT (16-14, 30 rounds total -- sample 162345)**
- 1 `.round-history-con` container (all 30 rounds in one container)
- 30 `.round-history-outcome` images per team row
- OT rounds appended inline after regulation rounds, no extra separators
- Breakdown row does NOT show OT breakdown -- only the two regulation halves
- Headlines: "Round history", "Performance - rating 2.0", "Players"

**Pattern 3: Extended OT (19-17, 36 rounds -- sample 206389)**
- 2 `.round-history-con` containers
  - Container 1 ("Round history"): 24 regulation outcomes
  - Container 2 ("Overtime"): 12 OT outcomes with 4 bar separators (3-round OT halves)
- Breakdown row shows `( 7 : 5 )` OT total (plain text, no ct/t spans)
- Headlines: "Round history", **"Overtime"**, "Performance - rating 3.0", "Players"

**Parser handling recommendation:**
```python
containers = soup.select('.round-history-con')
if len(containers) == 1:
    # All rounds (regulation + any OT) in single container
    outcomes = containers[0].select('img.round-history-outcome')
elif len(containers) == 2:
    # Container 0 = regulation, Container 1 = overtime
    reg_outcomes = containers[0].select('img.round-history-outcome')
    ot_outcomes = containers[1].select('img.round-history-outcome')
```

### Map Stats: Breakdown Row OT

The first `.match-info-row .right` div contains the score breakdown:
- Regulation: two `()` groups with `.ct-color`/`.t-color` spans
- OT (extended): additional plain-text `( N : M )` group with NO color spans
- OT (single): **No additional group** -- OT rounds visible only in round history

### Economy: OT Data Availability

| Match Era | OT Rounds in Economy Data? | Details |
|-----------|:-:|---|
| MR15 (pre-2024) | **Yes** | FusionCharts shows all 30 round labels; equipment tables have 15+15 cells |
| MR12 (2024+) | **No** | FusionCharts shows only 24 labels (regulation); OT rounds completely absent |

**Parser handling:** Check round count in FusionCharts categories. If fewer rounds than expected from score:
```python
chart_rounds = len(config['dataSource']['categories'][0]['category'])
total_score = team1_score + team2_score
if chart_rounds < total_score:
    # OT economy data unavailable -- mark as missing, extract regulation only
```

---

## Section 3: Forfeit / Walkover Matches

### Types of Forfeits

1. **Full forfeit** (sample 2380434): Entire match forfeited before any map played
2. **Partial forfeit** (sample 2384993): Some maps played, then one map forfeited mid-series

### Full Forfeit Detection

A match is a full forfeit if ANY of these signals are present:

| Signal | Selector | Value | Reliability |
|--------|----------|-------|-------------|
| Countdown text | `.countdown` | "Match deleted" | High |
| Map name | `.mapholder .mapname` | "Default" | High |
| Format text | `.padding.preformatted-text` | Contains "forfeit" (case-insensitive) | High |
| Missing score divs | `.team1-gradient .won` / `.lost` | Both absent | High (full forfeit only) |
| Missing stats link | `.mapholder a.results-stats[href]` | Absent on played map | Medium (also absent on unplayed maps) |

**Recommended primary check:** `.mapholder .mapname` text == "Default"

### Full Forfeit: DOM Differences

| Element | Normal Match | Full Forfeit |
|---------|-------------|-------------|
| `.team1-gradient .won`/`.lost` | Present (one `.won`, one `.lost`) | **Both ABSENT** |
| `.countdown` text | "Match over" | "Match deleted" |
| Map holder count | 1-5 (by format) | 1 |
| `.mapname` text | Actual map name | "Default" |
| Map scores | Real scores | "0" and "1" |
| Half scores | Populated spans | **Empty** element |
| Stats link (`a.results-stats`) | Present | **ABSENT** |
| Veto box | Present with veto data | **Still present** (veto happened before forfeit) |
| Player lineups | 10 players | **Still present** (10 players) |
| Demo link | Present | **ABSENT** |
| Streams | Multiple | 1 ("No media yet") |

### Partial Forfeit Detection

In a partial forfeit (e.g., BO5 match 2384993):
- The match `.countdown` text is "Match over" (NOT "Match deleted") because the series result was decided
- The `.won`/`.lost` divs ARE present on team gradients
- One specific map has `.mapname` == "Default" with no stats link
- Format text contains forfeit note: `"** BOSS forfeit 3rd map..."` (lines starting with `**`)

### Pages Affected by Forfeits

| Page Type | Full Forfeit | Partial Forfeit |
|-----------|-------------|-----------------|
| Results Listing | `.map-text` = "def", score = "1-0" | `.map-text` = "bo3"/"bo5", normal series score |
| Match Overview | Map name "Default", no `.won`/`.lost`, no stats links | One map "Default", others normal |
| Map Stats | **Does not exist** (no mapstatsid) | Exists for played maps only |
| Performance | **Does not exist** | Exists for played maps only |
| Economy | **Does not exist** | Exists for played maps only |

### Parser Handling Recommendation

```python
# EARLY DETECTION at match overview parsing time
for mapholder in soup.select('.mapholder'):
    map_name = mapholder.select_one('.mapname').get_text(strip=True)
    stats_link = mapholder.select_one('a.results-stats[href]')

    if map_name == "Default":
        # Forfeit map: record as forfeit, skip sub-page fetching
        continue
    if stats_link is None and mapholder.select_one('.played'):
        # Played map with no stats link -- treat as forfeit
        continue
    if stats_link is None:
        # Unplayed map (sweep): skip
        continue

    # Normal played map: extract mapstatsid and queue sub-page fetches
    mapstatsid = parse_mapstatsid(stats_link['href'])
```

**Critical rule:** Always check for forfeits before attempting to fetch map stats/performance/economy sub-pages. Fetching a non-existent mapstatsid wastes requests and may trigger errors.

---

## Section 4: Rating Version Handling

### Affected Pages

| Page Type | Rating-Version-Dependent Content? | Detection Available? |
|-----------|:-:|:-:|
| Results Listing | No | N/A |
| Match Overview | No | N/A |
| Map Stats | **Yes** -- scoreboard column differences | Yes |
| Performance | **Yes** -- FusionChart bar differences | Yes |
| Economy | No | N/A |

### Version Differences

**Map Stats Scoreboard:**

| Feature | Rating 2.0 | Rating 3.0 |
|---------|-----------|------------|
| `th.st-rating` text | "Rating2.0" | "Rating3.0" |
| `.ratingDesc` text | "2.0" | "3.0" |
| `st-roundSwing` column | **Absent** | Present (12 elements) |
| Eco-adjusted data cells | `"null"` / `"-"` | Real values |
| `st-deaths` eco header | "eD" (no traded count) | "eD(t)" |
| `.match-info-row` row 2 label | "Team rating 2.0" | "Team rating 3.0" |

**Performance Page FusionChart:**

| Feature | Rating 2.0 | Rating 3.0 |
|---------|-----------|------------|
| Bar count | 6 | 7 |
| Last bar label | "Rating 2.0" | "Rating 3.0" |
| Bar 4 (index 3) | "Impact" (combined metric) | "MK rating" (multi-kill rating) |
| Bar 5 (index 4) | "ADR" | "Swing" (Round Swing %) |
| Bar 6 (index 5) | "Rating 2.0" | "ADR" |
| Bar 7 (index 6) | N/A | "Rating 3.0" |

### Finalized Detection Strategy

**Use a single detector function across all parsers.** The recommended detection approach uses the map stats page as the primary signal, with the performance page as a secondary signal:

**Primary detection (map stats page):**
```python
def detect_rating_version_from_stats(soup):
    """Detect rating version from map stats scoreboard header.

    Returns: '2.0', '3.0', or 'unknown'
    """
    th = soup.select_one('th.st-rating')
    if th:
        text = th.get_text(strip=True)
        if 'Rating3.0' in text or '3.0' in text:
            return '3.0'
        if 'Rating2.0' in text or '2.0' in text:
            return '2.0'

    # Fallback: check for st-roundSwing presence
    if soup.select_one('th.st-roundSwing'):
        return '3.0'

    return 'unknown'
```

**Secondary detection (performance page):**
```python
def detect_rating_version_from_performance(soup):
    """Detect rating version from FusionChart bar labels.

    Returns: '2.0', '3.0', or 'unknown'
    """
    chart_el = soup.select_one('[data-fusionchart-config]')
    if not chart_el:
        return 'unknown'

    config = json.loads(chart_el['data-fusionchart-config'])
    data = config['dataSource']['data']
    labels = [d['label'] for d in data]

    if labels and labels[-1] == 'Rating 3.0':
        return '3.0'
    if labels and labels[-1] == 'Rating 2.0':
        return '2.0'

    return 'unknown'
```

**Why the map stats header is preferred:**
1. Detected from a simple CSS selector (no JSON parsing needed)
2. Available before any per-player extraction starts
3. Both the header text and column presence (`st-roundSwing`) provide redundant signals
4. The map stats page is always parsed before the performance page (per extraction order)

### Impact on Database Storage

| Column | Rating 2.0 Value | Rating 3.0 Value |
|--------|-----------------|-----------------|
| rating | Float (2.0 formula) | Float (3.0 formula) |
| rating_version | "2.0" | "3.0" |
| round_swing | **NULL** | Float (signed percentage) |
| mk_rating | **NULL** | Float |
| impact | Float | **NULL** |
| eco_adjusted_* | **NULL** (all columns) | Float (real values) |

**Parser handling:** Store `rating_version` alongside each player stat row. Columns that don't apply to the detected version should be stored as NULL.

### Known Scope of Rating 2.0

Based on the 12-sample analysis:
- Only 1 of 12 samples uses Rating 2.0: mapstatsid 162345 (Sep 2023, tier-3 match)
- All other samples (Oct 2023 through Feb 2026) use Rating 3.0
- The retroactive Rating 3.0 application appears to have missed some older tier-3 matches
- **Parser must handle both versions** to avoid data loss on historical scrapes

---

## Section 5: Other Edge Cases

### Big-Results Featured Section (Results Listing, Page 1 Only)

The first page (`/results?offset=0`) contains a `.big-results` featured section with 8 promoted entries that are exact duplicates of entries in the regular results listing.

**Detection:** `.big-results` container exists on the page
**Impact:** Duplicate match entries if not filtered
**Parser action:** Always use the LAST `.results-all` container on the page to skip the featured section:
```python
results_all = soup.select('.results-all')
container = results_all[-1]  # Last is always regular results
```

### Missing Timestamps on Big-Results Entries

Entries inside `.big-results` lack the `data-zonedgrouping-entry-unix` attribute.

**Detection:** `entry.get('data-zonedgrouping-entry-unix')` returns None
**Impact:** Cannot determine match completion time for featured entries
**Parser action:** Skip featured entries entirely (they appear in regular results)

### Unranked Teams (Match Overview)

Some teams lack a `.teamRanking a` element in the lineups section. Both teams or just one may be unranked.

**Samples:** Match 2366498 (both teams unranked), Match 2377467 (Tunisia unranked, kONO ranked)
**Detection:** `.lineups .lineup .teamRanking a` returns fewer than 2 elements
**Parser action:** Store NULL for ranking when `.teamRanking a` is missing for a team

### Day/Night Logo Variants

~30% of team and event logos have two images: `.day-only` and `.night-only` variants (the night variant often has `?invert=true` URL parameter).

**Impact:** Multiple `img.team-logo` elements per team container
**Parser action:** If extracting logos, use the first `img.team-logo` and ignore theme classes. Logos are generally not needed for stat extraction.

### Map Name as Bare Text Node (Map Stats)

The map name on map stats pages is NOT inside any tag. It appears as a bare `NavigableString` child of `.match-info-box` between other elements.

**Detection:** No CSS selector works; must iterate children
**Parser action:**
```python
for child in match_info_box.children:
    if isinstance(child, NavigableString) and child.strip():
        map_name = child.strip()
        break
```
Verified across all 12 map stats samples.

### No Map Pick Indicator on Map Holders

Map holders on the match overview page have no visual indicator of which team picked that map. Map picks are only available from the veto text.

**Detection:** N/A (absence of feature)
**Parser action:** Cross-reference veto sequence "picked" lines with map holder map names to attribute picks:
```python
for line in veto_lines:
    match = re.match(r'\d+\. (.+) picked (.+)', line)
    if match:
        pick_team, pick_map = match.group(1), match.group(2)
```

### Two `.veto-box` Elements

The match overview page always has two `.standard-box.veto-box` elements:
1. First: contains match format and stage info (`.padding.preformatted-text`)
2. Second: contains actual veto sequence (`.padding > div` children)

**Parser action:** Use index-based selection: `soup.select('.veto-box')[1]` for the veto data. Do not use `:last-of-type` pseudo-class (depends on sibling structure).

### Performance Page Size Variation

One performance page sample (206389) is ~219K chars vs ~6.2M for others. Despite the size difference, all expected structural elements are present and correct.

**Impact:** None on extraction logic
**Parser action:** No special handling needed; extraction works identically regardless of page size

### Economy Page "Beta" Label

The economy tab on all pages (2023-2026) shows a `<span class="new-feature">Beta</span>` badge. Despite the label, the data is fully structured and extractable.

**Impact:** The "Beta" status may mean HLTV could change the page structure in the future
**Parser action:** No special handling; document as a future risk for selector changes

### Different Player ID Href Patterns

Player links use two different URL patterns across pages:

| Page | Pattern | Example |
|------|---------|---------|
| Match Overview | `/player/{id}/{slug}` | `/player/11893/zywoo` |
| Map Stats | `/stats/players/{id}/{slug}` | `/stats/players/17508/glowiing` |
| Performance (cards) | `/player/{id}/{slug}` | `/player/11893/zywoo` |
| Performance (matrix) | `/stats/players/{id}/{slug}` | `/stats/players/11893/zywoo` |

**Parser action:** Use two regex patterns for extraction:
```python
# From /player/{id}/ links
re.search(r'/player/(\d+)/', href)
# From /stats/players/{id}/ links
re.search(r'/stats/players/(\d+)/', href)
```
Both patterns yield the same numeric player ID.

### Non-Match Elements in Results Listings

The results holder contains non-match children that parsers must skip:
- `.pagination-component.pagination-bottom` (pagination)
- `span.clearfix` (layout spacer)

**Parser action:** Only iterate `.result-con` elements within the results container.

---

## Section 6: Edge Case Detection Cheatsheet

| Edge Case | Detection Method | Detection Selector/Check | Parser Action |
|-----------|-----------------|-------------------------|---------------|
| **Forfeit (full)** | `.mapname` text = "Default" | `.mapholder .mapname` text check | Skip all map sub-page fetches; record as forfeit; no mapstatsid exists |
| **Forfeit (partial)** | One map has name "Default" in a BO3/BO5 | `.mapholder .mapname` text check per map | Skip that specific map's sub-pages; parse other maps normally |
| **Forfeit (results)** | `.map-text` = "def" | `.map-text` text check | Record as forfeit; score is always 1-0 |
| **Overtime** | Total rounds > 24 (MR12) or > 30 (MR15) | Count `img.round-history-outcome` or sum half scores | Extend round iteration; check for second `.round-history-con` |
| **Extended OT** | 2 `.round-history-con` containers | `len(soup.select('.round-history-con'))` == 2 | Parse regulation from container 0, OT from container 1 |
| **Single OT** | 1 container but > 24 outcomes | Count outcomes in single container | All rounds (reg + OT) are inline in one container |
| **OT economy missing** | FusionChart round count < total score | `len(categories[0].category)` < `team1_score + team2_score` | Extract regulation economy only; mark OT economy as unavailable |
| **BO5** | 5 `.mapholder` elements | `len(soup.select('.mapholder'))` == 5 | Iterate up to 5 maps; 2+ may be unplayed |
| **BO1** | 1 `.mapholder` element | `len(soup.select('.mapholder'))` == 1 | Single map; no series score on match overview |
| **Unplayed map** | `.optional` class on inner div | `.mapholder .optional` presence | Skip; score text is "-"; no stats link |
| **Rating 2.0** | `th.st-rating` text contains "2.0" | `th.st-rating` text check | No `st-roundSwing` column; eco-adjusted data = NULL; FusionChart has 6 bars with "Impact" |
| **Rating 3.0** | `th.st-rating` text contains "3.0" | `th.st-rating` text check | Has `st-roundSwing` column; FusionChart has 7 bars with "MK rating" and "Swing" |
| **Big-results duplication** | Page 1 has `.big-results` section | `.big-results` presence check | Use last `.results-all` container only |
| **Unranked team** | Missing `.teamRanking a` in lineup block | `len(lineup.select('.teamRanking a'))` == 0 | Store ranking as NULL |
| **Map name bare text** | Not in any tag on map stats page | `NavigableString` iteration on `.match-info-box` | Iterate children, check `isinstance(child, NavigableString)` |
| **MR15 vs MR12** | Match date before ~2024 or economy half has 15 rounds | FusionChart round count per half | Regulation = 30 (MR15) or 24 (MR12); affects OT detection threshold |
