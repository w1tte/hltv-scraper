# Results Listing Page Selector Map

**Page type:** Results listing
**URL pattern:** `https://www.hltv.org/results?offset={N}` (N = 0, 100, 200, ...)
**Verified against:** 3 HTML samples (offset 0, 100, 5000)
**Date analyzed:** 2026-02-15

## Page Overview

The HLTV results listing page displays completed match results in reverse chronological order, 100 entries per page. Results are grouped by date. The first page (offset=0) includes a "big results" featured section at the top that duplicates entries from the regular listing.

### Key structural facts

- Each page returns exactly **100 regular results** (in `.results-all` with `data-zonedgrouping-entry-unix` attributes)
- The first page (offset=0) additionally contains a **big-results** featured section with 8 promoted entries that are **duplicates** of entries in the regular list
- Total results count: **115,045** at time of fetch (available from pagination text)
- Results are grouped into `.results-sublist` containers by date, each with a `.standard-headline` showing the date

---

## Field-by-Field Selector Table

### Container-Level Selectors

| Field | CSS Selector | Data Type | Required | Example Value | Extraction | Notes |
|-------|-------------|-----------|----------|---------------|------------|-------|
| Results holder | `.results-all` | container | always | - | skip | Wraps all regular results; 2 on page 1 (big-results + regular), 1 on other pages |
| Date group | `.results-sublist` | container | always | - | skip | Groups results by date |
| Date headline | `.results-sublist > .standard-headline` | string | usually | `"Results for February 14th 2026"` | **extract** | Absent on the big-results sublist (page 1 only) |
| Featured section | `.big-results` | container | page 1 only | - | **skip** | Only on offset=0; entries are duplicates of regular results |
| Match entry | `.result-con` | container | always | - | **extract** | One per match result |
| Pagination | `.pagination-component` | container | always | - | **extract** | 2 per page (top + bottom); use `.pagination-top` |

### Per-Match-Entry Fields (inside each `.result-con`)

| Field | CSS Selector | Data Type | Required | Example Value | Extraction | Notes |
|-------|-------------|-----------|----------|---------------|------------|-------|
| Match URL | `a.a-reset[href]` | string | always | `/matches/2389953/furia-vs-b8-pgl-cluj-napoca-2026` | **extract** | `href` attribute; parse match_id with regex `/matches/(\d+)/` |
| Match timestamp | `[data-zonedgrouping-entry-unix]` | unix_ms | regular only | `1771112947000` | **extract** | `data-zonedgrouping-entry-unix` attribute on the `.result-con` div itself. **Absent** on big-results entries. Divide by 1000 for epoch seconds. |
| Team 1 name | `.team1 .team` | string | always | `"FURIA"` | **extract** | Text content. The `.team` div may have additional class `team-won` if team 1 won. |
| Team 2 name | `.team2 .team` | string | always | `"B8"` | **extract** | Text content. The `.team` div may have additional class `team-won` if team 2 won. |
| Winner indicator | `.team-won` | presence | always | class on `.team` div | **extract** | Exactly one `.team-won` exists per entry. Located inside `.team1` or `.team2`. |
| Team 1 score | `.result-score .score-won` or `.score-lost` | int | always | `2` | **extract** | First `<span>` in `.result-score` belongs to team 1. It has class `score-won` if team 1 won, `score-lost` otherwise. |
| Team 2 score | `.result-score .score-won` or `.score-lost` | int | always | `0` | **extract** | Second `<span>` in `.result-score` belongs to team 2. |
| Map/format | `.map-text` | string | always | `"bo3"`, `"nuke"`, `"def"` | **extract** | Values: `bo3`, `bo5` for series; abbreviated map name for BO1 (e.g., `nuke`, `ovp`, `mrg`); `def` for forfeit/default win |
| Star rating | `.stars i` | int (count) | sometimes | 0-5 | **extract** | Count `<i>` elements inside `.stars`. When 0 stars, the `.stars` div and `.map-and-stars` wrapper are **absent entirely**. |
| Event name | `.event-name` | string | always | `"PGL Cluj-Napoca 2026"` | **extract** | Text content of `<span class="event-name">` |
| Team 1 logo | `.team1 img.team-logo` | string | always | `https://img-cdn.hltv.org/teamlogo/...` | skip | `src` attribute. Some teams have 2 logos: `.day-only` and `.night-only` variants. |
| Team 2 logo | `.team2 img.team-logo` | string | always | `https://img-cdn.hltv.org/teamlogo/...` | skip | Same day/night variant behavior. |
| Event logo | `.event-logo` | string | always | `https://img-cdn.hltv.org/eventlogo/...` | skip | `src` attribute. Also has day/night variants for some events. |

### Pagination Fields

| Field | CSS Selector | Data Type | Required | Example Value | Extraction | Notes |
|-------|-------------|-----------|----------|---------------|------------|-------|
| Pagination text | `.pagination-data` | string | always | `"1 - 100 of 115045"` | **extract** | Parse with regex `(\d+) - (\d+) of (\d+)` to get start, end, total |
| Next page link | `.pagination-next[href]` | string | when exists | `/results?offset=100` | **extract** | `href` attribute. Has class `inactive` (no href) on last page. |
| Prev page link | `.pagination-prev[href]` | string | when exists | `/results?offset=4900` | future | `href` attribute. Has class `inactive` (no href) on first page. |

---

## Annotated HTML Snippets

### Regular Match Entry (BO3, with stars, team 1 won)

```html
<!-- .result-con is the outermost per-match container -->
<!-- data-zonedgrouping-entry-unix: millisecond Unix timestamp of match completion -->
<div class="result-con" data-zonedgrouping-entry-unix="1771112947000">
  <a class="a-reset" href="/matches/2390387/lag-vs-overknight-prizepicks-na-revival-series-12">
    <div class="result">
      <table><tbody><tr>

        <!-- TEAM 1 (left side) -->
        <td class="team-cell">
          <div class="line-align team1">
            <!-- .team-won class indicates this team won -->
            <div class="team team-won">LAG</div>
            <!-- Some teams have day-only + night-only logo pairs -->
            <img class="team-logo day-only" src="https://img-cdn.hltv.org/teamlogo/..." alt="LAG"/>
            <img class="team-logo night-only" src="https://img-cdn.hltv.org/teamlogo/...?invert=true..." alt="LAG"/>
          </div>
        </td>

        <!-- SCORE -->
        <td class="result-score">
          <!-- .score-won = winner's score, .score-lost = loser's score -->
          <!-- Position determines team: first span = team 1, second span = team 2 -->
          <span class="score-won">2</span> - <span class="score-lost">0</span>
        </td>

        <!-- TEAM 2 (right side) -->
        <td class="team-cell">
          <div class="line-align team2">
            <img class="team-logo" src="https://img-cdn.hltv.org/teamlogo/..." alt="OverKnight"/>
            <!-- No .team-won class = this team lost -->
            <div class="team">OverKnight</div>
          </div>
        </td>

        <!-- EVENT -->
        <td class="event">
          <img class="event-logo" src="https://img-cdn.hltv.org/eventlogo/..." alt="PrizePicks NA Revival Series 12"/>
          <span class="event-name">PrizePicks NA Revival Series 12</span>
        </td>

        <!-- STARS + MAP/FORMAT -->
        <td class="star-cell">
          <!-- When 0 stars: .map-and-stars wrapper is absent, .map-text sits directly in .star-cell -->
          <div class="map-text">bo3</div>
        </td>

      </tr></tbody></table>
    </div>
  </a>
</div>
```

### Match Entry with Stars (2 stars)

```html
<!-- Star cell structure when stars > 0 -->
<td class="star-cell">
  <div class="map-and-stars">
    <div class="stars">
      <i class="fa fa-star star"></i>
      <i class="fa fa-star star"></i>
    </div>
    <!-- Note: .map-text gets additional class "map" when inside .map-and-stars -->
    <div class="map map-text">bo3</div>
  </div>
</td>
```

### BO1 Entry (map name instead of format)

```html
<!-- For BO1 matches, .map-text shows abbreviated map name instead of "bo1" -->
<td class="star-cell">
  <div class="map-text">nuke</div>
</td>
<!-- Observed BO1 map abbreviations: nuke, ovp (Overpass), mrg (Mirage) -->
```

### Forfeit/Default Entry

```html
<!-- Forfeit entries have map-text "def" and a normal 1-0 score -->
<div class="result-con" data-zonedgrouping-entry-unix="1771105556000">
  <a class="a-reset" href="/matches/2390356/los-kogutos-vs-1win-esl-challenger-league-season-51-europe-cup-1">
    <div class="result">
      <table><tbody><tr>
        <td class="team-cell">
          <div class="line-align team1">
            <div class="team team-won">los kogutos</div>
            <img class="team-logo" src="..." alt="los kogutos"/>
          </div>
        </td>
        <td class="result-score">
          <span class="score-won">1</span> - <span class="score-lost">0</span>
        </td>
        <td class="team-cell">
          <div class="line-align team2">
            <img class="team-logo" src="..." alt="1win"/>
            <div class="team">1win</div>
          </div>
        </td>
        <td class="event">
          <img class="event-logo day-only" src="..." alt="..."/>
          <img class="event-logo night-only" src="..." alt="..."/>
          <span class="event-name">ESL Challenger League Season 51 Europe Cup 1</span>
        </td>
        <td class="star-cell">
          <!-- "def" indicates forfeit/default win -->
          <div class="map-text">def</div>
        </td>
      </tr></tbody></table>
    </div>
  </a>
</div>
```

### Date Group Container

```html
<!-- Results are grouped by date inside .results-sublist containers -->
<div class="results-sublist">
  <div class="standard-headline">Results for February 14th 2026</div>
  <!-- N .result-con entries follow, all from this date -->
  <div class="result-con" data-zonedgrouping-entry-unix="...">...</div>
  <div class="result-con" data-zonedgrouping-entry-unix="...">...</div>
  <!-- ... -->
</div>
```

### Pagination Component

```html
<!-- Two pagination components per page: .pagination-top and .pagination-bottom -->
<div class="pagination-component pagination-top">
  <!-- Text shows range and total count -->
  <span class="pagination-data">1 - 100 of 115045</span>
  <!-- .inactive class + no href on first page prev / last page next -->
  <a class="pagination-prev inactive">
    <i class="fa fa-chevron-left pagination-left"></i>
  </a>
  <a class="pagination-next" href="/results?offset=100">
    <i class="fa fa-chevron-right pagination-right"></i>
  </a>
</div>
```

---

## Pagination Mechanics

### URL Scheme

- **Base URL:** `https://www.hltv.org/results`
- **Offset parameter:** `?offset=N` where N increments by 100
- **First page:** `?offset=0` (or just `/results`)
- **Page size:** 100 regular entries per page (plus up to 8 featured entries on page 1)

### Determining Total Pages

The `.pagination-data` text contains the total count:
```
"1 - 100 of 115045"  ->  total = 115045
```
Parse with regex: `(\d+)\s*-\s*(\d+)\s+of\s+(\d+)`

Total pages = `ceil(total / 100)`

### Stop Conditions

Three complementary stop conditions (use any):

1. **Next button inactive:** `.pagination-next` has class `inactive` and no `href` attribute
2. **Pagination text:** When `end >= total` in the pagination data text
3. **Empty results:** If `.result-con` count is 0, no more results exist

### Page 1 Special Behavior

- Contains **two** `.results-all` sections:
  - First: wraps `.big-results` (8 featured entries without timestamps)
  - Second: wraps 100 regular entries (with timestamps)
- Big-results entries are **exact duplicates** of entries in the regular listing
- **Parser should skip `.big-results`** and only process the second `.results-all` to avoid double-counting

### Observed Values

| Sample | Offset | Regular entries | Big-results entries | Date groups | Total reported |
|--------|--------|-----------------|---------------------|-------------|----------------|
| offset-0 | 0 | 100 | 8 | 3 | 115,045 |
| offset-100 | 100 | 100 | 0 | 3 | 115,045 |
| offset-5000 | 5000 | 100 | 0 | 6 | 115,045 |

---

## Structural Observations

### Big-Results Featured Section (Page 1 Only)

The `.big-results` section is a promoted/featured area that appears only on the first page (offset=0). Key differences:

| Aspect | Big-results entries | Regular entries |
|--------|-------------------|-----------------|
| Container | Inside `.big-results` | Inside `.results-all` (second one) |
| Timestamp | **No** `data-zonedgrouping-entry-unix` | **Has** `data-zonedgrouping-entry-unix` |
| Date headline | No `.standard-headline` | Grouped under date headlines |
| Content | Same HTML structure otherwise | Same HTML structure |
| Duplication | Duplicated in regular results | Authoritative listing |

**Recommendation:** Skip `.big-results` entirely. Parse only the regular `.results-all` section.

### Day/Night Theme Logo Variants

Some teams and events have two logo images:
- `img.team-logo.day-only` -- shown in light theme
- `img.team-logo.night-only` -- shown in dark theme (often with `?invert=true` URL parameter)

~30% of entries have day/night logo pairs. The other ~70% have a single `img.team-logo` without theme classes.

**For extraction:** Use the first `img.team-logo` `src` (if needed at all). Logos are marked as "skip" since we don't need them.

### Map-Text Value Mapping

The `.map-text` field encodes both format and map information:

| Value | Meaning | Match Type |
|-------|---------|------------|
| `bo3` | Best of 3 | Series |
| `bo5` | Best of 5 | Series |
| `nuke` | BO1 on Nuke | Single map |
| `ovp` | BO1 on Overpass | Single map |
| `mrg` | BO1 on Mirage | Single map |
| `inf` | BO1 on Inferno | Single map (inferred) |
| `anb` | BO1 on Anubis | Single map (inferred) |
| `anc` | BO1 on Ancient | Single map (inferred) |
| `d2` | BO1 on Dust2 | Single map (inferred) |
| `vtg` | BO1 on Vertigo | Single map (inferred) |
| `trn` | BO1 on Train | Single map (inferred) |
| `def` | Forfeit/default win | No map played |

**Observed in samples:** `bo3` (276), `def` (26), `bo5` (2), `nuke` (2), `ovp` (1), `mrg` (1)

**Parsing logic:**
- If value is `bo3` or `bo5`: it's a series format
- If value is `def`: it's a forfeit
- Otherwise: it's a BO1 and the value is an abbreviated map name

### Score Structure

Scores use `.score-won` and `.score-lost` classes that indicate the *outcome* of each side, not position:
- Team 1's score is always the **first** `<span>` inside `.result-score`
- Team 2's score is always the **second** `<span>` inside `.result-score`
- The `score-won`/`score-lost` classes tell you which team won

For forfeit entries, score is always `1 - 0` (winner gets `score-won`, loser gets `score-lost`).

No tied scores were observed across all 308 entries in the 3 samples.

### Elements NOT Present on Results Listing

The following elements are **not** present on the results listing page:
- LAN/online indicator (no badge, no flag)
- Team IDs (no link to `/team/{id}/...` -- only the match link)
- Player information
- Map scores for individual maps in a series
- Veto information

These fields are only available on the match overview page.

### Non-Match Elements in Results

The results holder contains these non-match children that a parser must skip:
- `.pagination-component.pagination-bottom` -- pagination at bottom
- `span.clearfix` -- layout spacer

No ads or promotional elements were found interspersed with match results inside the `.results-holder`.

### Differences Between Samples

| Aspect | offset-0 | offset-100 | offset-5000 |
|--------|----------|------------|-------------|
| Big-results section | Present (8 entries) | Absent | Absent |
| Date groups | 3 dates | 3 dates | 6 dates |
| `.results-all` count | 2 | 1 | 1 |
| BO1 entries (map name) | 0 | 4 | 0 |
| Forfeit entries (`def`) | 14 | 11 | 1 |
| BO5 entries | 0 | 0 | 2 |
| Max star rating | 3 | 1 | 3 |
| Star distribution | 0:92, 1:2, 2:10, 3:4 | 0:97, 1:3 | 0:92, 1:3, 2:3, 3:2 |

---

## Selector Verification Results

Every selector was tested against all 3 HTML samples using `BeautifulSoup.select()`.

| Selector | offset-0 | offset-100 | offset-5000 | Consistent | Notes |
|----------|----------|------------|-------------|------------|-------|
| `.result-con` | 108 | 100 | 100 | Yes | 108 on page 1 = 8 big + 100 regular |
| `.result-con a.a-reset` | 108 | 100 | 100 | Yes | 1:1 with entries |
| `.result-con .team1 .team` | 108 | 100 | 100 | Yes | Always present |
| `.result-con .team2 .team` | 108 | 100 | 100 | Yes | Always present |
| `.result-con .team-won` | 108 | 100 | 100 | Yes | Exactly 1 per entry |
| `.result-con img.team-logo` | 251 | 234 | 249 | Yes | >1 per entry due to day/night variants |
| `.result-con .result-score` | 108 | 100 | 100 | Yes | Always present |
| `.result-con .result-score .score-won` | 108 | 100 | 100 | Yes | Always present |
| `.result-con .result-score .score-lost` | 108 | 100 | 100 | Yes | Always present |
| `.result-con .map-text` | 108 | 100 | 100 | Yes | Always present |
| `.result-con .stars i` | 34 | 3 | 15 | Yes | Variable; 0 when no `.stars` div |
| `.result-con .event-name` | 108 | 100 | 100 | Yes | Always present |
| `.result-con .event-logo` | 149 | 143 | 125 | Yes | >1 per entry due to day/night variants |
| `.results-sublist` | 4 | 3 | 6 | Yes | 1 per date group |
| `.results-sublist .standard-headline` | 3 | 3 | 6 | Yes | Missing on big-results sublist |
| `.result-con[data-zonedgrouping-entry-unix]` | 100 | 100 | 100 | Yes | Only on regular (not big-results) entries |
| `.pagination-component` | 2 | 2 | 2 | Yes | Top + bottom |
| `.pagination-data` | 2 | 2 | 2 | Yes | |
| `.pagination-next` | 2 | 2 | 2 | Yes | |
| `.pagination-prev` | 2 | 2 | 2 | Yes | |
| `.big-results` | 1 | 0 | 0 | Yes | Only on first page |

All selectors work consistently across all 3 samples.

---

## Recommended Extraction Strategy for Phase 4

### Minimal extraction path

```python
# 1. Load page, find the correct results-all container
# Skip big-results: use the LAST .results-all on the page
results_all = soup.select('.results-all')
container = results_all[-1]  # Last one is always the regular results

# 2. Select all match entries
entries = container.select('.result-con')

# 3. For each entry, extract fields
for entry in entries:
    match_url = entry.select_one('a.a-reset')['href']
    match_id = int(re.search(r'/matches/(\d+)/', match_url).group(1))

    timestamp_ms = entry.get('data-zonedgrouping-entry-unix')  # may be None on page 1
    if timestamp_ms:
        match_date = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)

    team1_name = entry.select_one('.team1 .team').text.strip()
    team2_name = entry.select_one('.team2 .team').text.strip()

    team1_won = entry.select_one('.team1 .team-won') is not None

    scores = entry.select('.result-score span')
    team1_score = int(scores[0].text.strip())
    team2_score = int(scores[1].text.strip())

    map_text = entry.select_one('.map-text').text.strip()
    # "bo3"/"bo5" = series, "def" = forfeit, else = BO1 map name

    stars = len(entry.select('.stars i'))

    event_name = entry.select_one('.event-name').text.strip()

# 4. Pagination: check for next page
next_btn = soup.select_one('.pagination-next')
has_next = 'inactive' not in next_btn.get('class', [])
next_url = next_btn.get('href') if has_next else None
```

### Edge cases to handle

1. **Page 1 big-results duplication:** Always use the last `.results-all` container
2. **Missing timestamp on big-results:** If `data-zonedgrouping-entry-unix` is None, fall back to the date headline of the containing `.results-sublist`, or skip (entry will appear in regular results anyway)
3. **Forfeit detection:** `map-text == "def"` -- score will be 1-0
4. **BO1 map abbreviation:** When `map-text` is not `bo3`/`bo5`/`def`, it's a BO1 map abbreviation
5. **Star count of 0:** The `.stars` div is entirely absent, so `len(soup.select('.stars i'))` correctly returns 0
6. **Day/night logo variants:** If extracting logos, use the first `img.team-logo` and ignore theme classes

---

## Map Abbreviation Reference

| Abbreviation | Full Map Name |
|-------------|---------------|
| `nuke` | Nuke |
| `ovp` | Overpass |
| `mrg` | Mirage |
| `inf` | Inferno |
| `anb` | Anubis |
| `anc` | Ancient |
| `d2` | Dust2 |
| `vtg` | Vertigo |
| `trn` | Train |

Note: Only `nuke`, `ovp`, and `mrg` were directly observed in samples. The others are inferred from HLTV's naming conventions and should be verified when encountered.
