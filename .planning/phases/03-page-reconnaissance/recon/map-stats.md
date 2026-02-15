# Map Stats Page Selector Map

**Page type:** `/stats/matches/mapstatsid/{id}/{slug}`
**Samples analyzed:** 12 (mapstatsid 162345, 164779, 164780, 173424, 174112, 174116, 179210, 188093, 206389, 206393, 219128, 219151)
**Verified:** All selectors tested programmatically via `soup.select()` against all 12 samples
**Analysis date:** 2026-02-15

## Rating Version Note

11 of 12 samples use **Rating 3.0**. One sample (162345, Sep 2023 match) uses **Rating 2.0**. The difference affects the scoreboard:
- Rating 2.0: no `st-roundSwing` column, eco-adjusted data contains `"null"` / `"-"` values
- Rating 3.0: has `st-roundSwing` column, eco-adjusted data contains real values

Detection: check `th.st-rating` text content ("Rating2.0" vs "Rating3.0") or presence of `th.st-roundSwing`.

---

## Section 1: Match/Map Metadata

Located inside `.match-info-box` (1 per page, consistent across all 12 samples).

### Team Names and Scores

| Field | CSS Selector | Data Type | Required | Example Value | Extraction | Notes |
|-------|-------------|-----------|----------|---------------|------------|-------|
| team_left_name | `.team-left a` | string | always | "9 Pandas" | **extract** | Text content of anchor tag |
| team_left_id | `.team-left a[href]` | int | always | 11883 | **extract** | Parse from href `/stats/teams/{id}/{slug}` |
| team_left_score | `.team-left .bold` | int | always | "8" | **extract** | Total rounds won; has class `.won` or `.lost` |
| team_left_won | `.team-left .bold.won` | boolean | always | presence check | **extract** | If `.won` class present, this team won the map |
| team_right_name | `.team-right a` | string | always | "FORZE" | **extract** | Same structure as team-left |
| team_right_id | `.team-right a[href]` | int | always | 8135 | **extract** | Parse from href `/stats/teams/{id}/{slug}` |
| team_right_score | `.team-right .bold` | int | always | "13" | **extract** | Has `.won` or `.lost` class |
| team_right_won | `.team-right .bold.won` | boolean | always | presence check | **extract** | If `.won` class present, this team won |
| team_left_logo | `.team-left img.team-logo` | string | always | CDN URL | skip | Logo image URL |
| team_right_logo | `.team-right img.team-logo` | string | always | CDN URL | skip | Has `.day-only` and `.night-only` variants |

**Team container HTML snippet:**
```html
<div class="team-left">
  <img alt="9 Pandas" class="team-logo" src="https://img-cdn.hltv.org/..." title="9 Pandas"/>
  <a class="block text-ellipsis" href="/stats/teams/11883/9-pandas">
    9 Pandas
  </a>
  <div class="bold lost">
    8
  </div>
</div>
```

**NOTE:** `.teamName` selector (used on match overview pages) does NOT exist on map stats pages. Team names are extracted via `.team-left a` / `.team-right a` instead.

### Event and Date

| Field | CSS Selector | Data Type | Required | Example Value | Extraction | Notes |
|-------|-------------|-----------|----------|---------------|------------|-------|
| event_name | `.match-info-box > a[href*="event"]` | string | always | "CCT East Europe Series 3" | **extract** | First `<a>` child with event href |
| event_id | `.match-info-box > a[href*="event"]` | int | always | 7451 | **extract** | Parse from href `/stats?event={id}` |
| match_date | `.match-info-box [data-unix]` | unix_ms | always | "1697895000000" | **extract** | `data-unix` attribute, divide by 1000 for epoch seconds |

### Map Name

| Field | CSS Selector | Data Type | Required | Example Value | Extraction | Notes |
|-------|-------------|-----------|----------|---------------|------------|-------|
| map_name | text node in `.match-info-box` | string | always | "Nuke" | **extract** | Bare text node after `.small-text` div. No class/tag -- it's a raw text child of `.match-info-box`. Use `NavigableString` iteration. |

The map name is NOT inside any tag. It appears as a bare text node between the `.small-text` div and the `.team-left` div. Extraction approach:
```python
for child in match_info_box.children:
    if isinstance(child, NavigableString) and child.strip():
        map_name = child.strip()
        break
```

Verified: all 12 samples produce correct map names (Nuke, Anubis, Mirage, Inferno, Overpass).

### Half Score Breakdown

Located in the first `.match-info-row` element. Always 4 `.match-info-row` elements per page.

| Field | CSS Selector | Data Type | Required | Example Value | Extraction | Notes |
|-------|-------------|-----------|----------|---------------|------------|-------|
| breakdown_row | `.match-info-row:first-child .right` | complex | always | see below | **extract** | Contains score breakdown with colored spans |
| team_left_total | `.match-info-row:first-child .right > span:first-child` | int | always | "8" | **extract** | Has `.won` or `.lost` class |
| half1_left_rounds | `.match-info-row:first-child .right span.ct-color:first-of-type` or `span.t-color:first-of-type` | int | always | varies | **extract** | First half; ct-color or t-color depends on starting side |
| half1_right_rounds | second span in first `()` group | int | always | varies | **extract** | Opponent's first half |
| half2_left_rounds | first span in second `()` group | int | always | varies | **extract** | Second half |
| half2_right_rounds | second span in second `()` group | int | always | varies | **extract** | Second half opponent |
| ot_breakdown | third `()` group (if present) | string | sometimes | "( 7 : 5 )" | **extract** | Only present on OT maps; plain text, NO ct/t-color spans |

**Breakdown row HTML -- regular match (164779, 8-13):**
```html
<div class="right">
  <span class="lost">8</span> : <span class="won">13</span>
  (<span class="ct-color">2</span> : <span class="t-color">10</span>)
  (<span class="t-color">6</span> : <span class="ct-color">3</span>)
</div>
```

**Breakdown row HTML -- overtime match (206389, 19-17):**
```html
<div class="right">
  <span class="won">19</span> : <span class="lost">17</span>
  (<span class="ct-color">3</span> : <span class="t-color">9</span>)
  (<span class="t-color">9</span> : <span class="ct-color">3</span>)
  ( 7 : 5 )
</div>
```

**Half score interpretation:**
- Half 1 is in the first `()` group. The `ct-color` span = CT-side rounds, `t-color` span = T-side rounds.
- Half 2 is in the second `()` group. Sides swap (the team that was T in half 1 is now CT in half 2).
- The first `ct-color`/`t-color` span in half 1 belongs to team-left; the second to team-right.
- **Overtime breakdown** (third group, if present): plain text `( N : M )` with NO color spans. These are the total OT rounds per team (left : right), not broken down by CT/T.

**Single OT (162345, 16-14):** no OT breakdown group in the match-info-row. Overtime rounds are embedded in the round history only. The breakdown shows only the two regulation halves.

### Other Match Info Rows

| Row | Label (`.bold` child) | Right Value (`.right` child) | Example | Extraction |
|-----|----------------------|------------------------------|---------|------------|
| 1 | Breakdown | Score + half breakdown | "8 : 13 (2:10) (6:3)" | **extract** (see above) |
| 2 | Team rating {version} | "{float} : {float}" | "0.83 : 1.35" | **extract** -- team avg rating per team |
| 3 | First kills | "{int} : {int}" | "9 : 12" | **extract** -- opening kill count per team |
| 4 | Clutches won | "{int} : {int}" | "3 : 2" | **extract** -- clutch round wins per team |

All 4 rows present consistently across all 12 samples.

The rating label in row 2 indicates the rating version: "Team rating 2.0" or "Team rating 3.0". This matches the scoreboard rating version.

---

## Section 2: Per-Player Scoreboard

### Table Structure

There are **6** `.stats-table` elements per page (consistent across all 12 samples):

| Table | Class | Content | Visible |
|-------|-------|---------|---------|
| 1 | `.stats-table.totalstats` | Team-left total stats | Yes |
| 2 | `.stats-table.ctstats.hidden` | Team-left CT-side stats | No (hidden) |
| 3 | `.stats-table.tstats.hidden` | Team-left T-side stats | No (hidden) |
| 4 | `.stats-table.totalstats` | Team-right total stats | Yes |
| 5 | `.stats-table.ctstats.hidden` | Team-right CT-side stats | No (hidden) |
| 6 | `.stats-table.tstats.hidden` | Team-right T-side stats | No (hidden) |

**Team attribution:** The first `.stats-table.totalstats` is always team-left. The second is always team-right. Confirmed by checking the `th.st-teamname` header (contains team name) and cross-referencing with `.team-left a` text.

**Row count:** 5 rows per table (tbody tr) across all 12 samples. Always 5 players per team.

### Table Columns (Rating 3.0 -- 11 of 12 samples)

Each table has these columns, tested via `th` classes:

| Column | Header Class | Header Text | Data Class | Data Type | Example | Extraction | Notes |
|--------|-------------|-------------|------------|-----------|---------|------------|-------|
| Team name | `st-teamname text-ellipsis` | team name | - | string | "9 Pandas" | **extract** | Only in header row |
| Opening K-D | `st-opkd gtSmartphone-only traditional-data` | "Op.K-D" | `st-opkd gtSmartphone-only traditional-data` | string | "2 : 5" | **extract** | Format: "{int} : {int}" |
| Eco Opening K-D | `st-opkd gtSmartphone-only eco-adjusted-data hidden` | "Op.eK-eD" | same | string | "2 : 5" | future | Hidden eco-adjusted variant |
| Multi-kills | `st-mks gtSmartphone-only` | "MKs" | `st-mks gtSmartphone-only` | int | "4" | **extract** | Multi-kill rounds count |
| KAST | `st-kast gtSmartphone-only traditional-data` | "KAST" | same | string | "66.7%" | **extract** | Percentage with % suffix |
| eKAST | `st-kast gtSmartphone-only eco-adjusted-data hidden` | "eKAST" | same | string | "64.0%" | future | Hidden eco-adjusted variant |
| Clutches | `st-clutches gtSmartphone-only` | "1vsX" | `st-clutches gtSmartphone-only` | int | "2" | **extract** | Clutch wins total |
| Kills (hs) | `st-kills traditional-data` | "K(hs)" | `st-kills traditional-data` | string | "14(9)" | **extract** | Format: "{kills}({headshots})" -- headshots in `<span class="gtSmartphone-only">` |
| Eco Kills | `st-kills eco-adjusted-data hidden` | "eK(hs)" | same | string | "14(9)" | future | Hidden eco-adjusted variant |
| Assists (flash) | `st-assists` | "A(f)" | `st-assists` | string | "2(0)" | **extract** | Format: "{assists}({flash_assists})" -- flash assists in `<span>` with tooltip |
| Deaths (traded) | `st-deaths traditional-data` | "D(t)" | `st-deaths traditional-data` | string | "15(2)" | **extract** | Format: "{deaths}({traded_deaths})" -- traded in `<span>` |
| Eco Deaths | `st-deaths eco-adjusted-data hidden` | "eD(t)" | same | string | "15(2)" | future | Hidden eco-adjusted variant |
| ADR | `st-adr traditional-data` | "ADR" | `st-adr traditional-data` | float | "69.2" | **extract** | Average damage per round |
| eADR | `st-adr eco-adjusted-data hidden` | "eADR" | same | float | "70.4" | future | Hidden eco-adjusted variant |
| KAST (mobile) | `st-kast smartphone-only traditional-data` | "KAST" | same | string | "66.7%" | skip | Duplicate for mobile layout |
| eKAST (mobile) | `st-kast smartphone-only eco-adjusted-data hidden` | "eKAST" | same | string | "64.0%" | skip | Duplicate for mobile layout |
| Round Swing | `st-roundSwing` | "Swing" | `st-roundSwing` | string | "+2.90%" | **extract** | Has `.won`/`.lost`/no subclass; Rating 3.0 only |
| Rating | `st-rating` | "Rating3.0" | `st-rating` | float | "1.14" | **extract** | Has `.ratingPositive`/`.ratingNeutral`/`.ratingNegative` subclass |

**Rating description:** `.ratingDesc` element exists inside each `<td class="st-rating">` cell. Text is "3.0" or "2.0". Appears 6 times per sample (one per table).

### Table Columns (Rating 2.0 -- sample 162345 only)

Same columns as Rating 3.0 **except:**
- No `st-roundSwing` column (absent entirely)
- `st-deaths eco-adjusted-data hidden` header text is "eD" (not "eD(t)")
- Eco-adjusted data cells contain `"null"` or `"-"` instead of real values
- `st-rating` header text is "Rating2.0" instead of "Rating3.0"
- `.ratingDesc` text is "2.0"

### Player Name and ID

| Field | CSS Selector | Data Type | Example | Extraction | Notes |
|-------|-------------|-----------|---------|------------|-------|
| player_name | `tbody tr td.st-player a.text-ellipsis` | string | "glowiing" | **extract** | Text content |
| player_id | `tbody tr td.st-player a[href]` | int | 17508 | **extract** | Parse from href `/stats/players/{id}/{slug}` |
| player_country | `tbody tr td.st-player img.flag` | string | "Russia" | **extract** | `title` attribute on flag image |

**Player cell HTML snippet:**
```html
<td class="st-player">
  <div class="flag-align">
    <img alt="Russia" class="flag" src="/img/static/flags/30x20/RU.gif" title="Russia"/>
    <a class="text-ellipsis" href="/stats/players/17508/glowiing">
      glowiing
    </a>
  </div>
</td>
```

### Kills/Deaths/Assists Sub-value Parsing

The kills, deaths, and assists cells contain a main number and a parenthesized sub-value:

```html
<!-- Kills: 14 total, 9 headshots -->
<td class="st-kills traditional-data">
  14
  <span class="gtSmartphone-only">(9)</span>
</td>

<!-- Assists: 2 total, 0 flash assists -->
<td class="st-assists">
  2
  <span class="gtSmartphone-only" title="Flash assists, a teammate killed an opponent while blinded, or pushed out of position by a flash by this player.">
    (0)
  </span>
</td>

<!-- Deaths: 15 total, 2 traded -->
<td class="st-deaths traditional-data">
  15
  <span class="gtSmartphone-only">(2)</span>
</td>
```

**Parsing approach:** Use `td.get_text(strip=True)` to get full string like `"14(9)"`, then parse with regex `(\d+)\((\d+)\)`.

### CT-Side and T-Side Tables

The hidden `.ctstats` and `.tstats` tables have the **same column structure** as `.totalstats`. They contain per-side stats for the same players. These tables become visible when the user toggles the side filter (JS-driven, hidden by default).

**Extraction recommendation:** For Phase 6, extract from `.totalstats` tables only. CT/T side breakdowns can be derived from round-level data or extracted as a future enhancement from `.ctstats`/`.tstats`.

### Eco-Adjusted Data

Every traditional-data column has an eco-adjusted counterpart with class `eco-adjusted-data hidden`. These are hidden by default and toggled via JavaScript. The eco-adjusted values ARE present in the initial HTML (no AJAX needed).

- Rating 3.0 pages: eco-adjusted values are real numbers
- Rating 2.0 pages: eco-adjusted values are `"null"` or `"-"` (not available)

**Extraction recommendation:** Extract traditional data for Phase 6. Eco-adjusted data can be extracted as a future enhancement (same CSS selectors with `eco-adjusted-data` instead of `traditional-data`).

---

## Section 3: Round History

### Container Structure

| Element | CSS Selector | Count | Notes |
|---------|-------------|-------|-------|
| Regulation container | `.round-history-con` (first) | 1 per page | Always present, 24 outcomes for regular matches, 24-30 for single OT |
| Overtime container | `.round-history-con` (second, if present) | 0 or 1 | Present only when OT rounds exceed regulation container |
| Team row | `.round-history-team-row` | 2 per container | One row per team |
| Team identity | `img.round-history-team` | 1 per row | `title` attribute = team name |
| Half separator | `div.round-history-bar` | varies | Separates regulation halves and OT halves |
| Round outcome | `img.round-history-outcome` | varies | One per round |

### Overtime Handling

Three distinct patterns observed:

**Pattern 1: Regular match (no OT)** -- 10 of 12 samples
- 1 `.round-history-con` container
- 2 `.round-history-bar` separators per row (one at start, one between halves)
- 21-24 `.round-history-outcome` elements per row (total rounds played)
- Headlines: "Round history", "Performance - rating X.X", "Players"

**Pattern 2: Single OT (162345, Nuke 16-14, 30 rounds)**
- 1 `.round-history-con` container (ALL 30 rounds in one container)
- 2 `.round-history-bar` separators per row (same as regular)
- 30 `.round-history-outcome` elements per row
- OT rounds are simply appended after regulation rounds, no additional separators
- Headlines: "Round history", "Performance - rating 2.0", "Players"
- Breakdown row does NOT show an OT section -- just the two regulation halves

**Pattern 3: Extended OT (206389, Mirage 19-17, 36 rounds = regulation + 2 OT periods)**
- 2 `.round-history-con` containers
  - Container 1 ("Round history" headline): 24 regulation outcomes, 2 bar separators per row
  - Container 2 ("Overtime" headline): 12 OT outcomes, 4 bar separators per row (separating each 3-round OT half)
- Headlines: "Round history", **"Overtime"**, "Performance - rating 3.0", "Players"
- Breakdown row shows `( 7 : 5 )` OT total as plain text (no ct/t color spans)

**Detection strategy:**
1. Count `.round-history-con` containers: 1 = regular or single OT; 2 = extended OT
2. Check for "Overtime" `.standard-headline`: present = extended OT has separate container
3. Count outcomes in first container: > 24 = single OT with rounds inline

### Round Outcome Types

Each round outcome is an `<img>` element. The outcome type is determined by the `src` attribute:

| Image Source | Meaning | Side |
|-------------|---------|------|
| `/img/static/scoreboard/ct_win.svg` | CT team eliminated all T players | CT win |
| `/img/static/scoreboard/t_win.svg` | T team eliminated all CT players | T win |
| `/img/static/scoreboard/bomb_exploded.svg` | Bomb detonated | T win |
| `/img/static/scoreboard/bomb_defused.svg` | Bomb defused | CT win |
| `/img/static/scoreboard/stopwatch.svg` | Time ran out (no plant) | CT win |
| `/img/static/scoreboard/emptyHistory.svg` | This team lost this round | Loss indicator |

**Interpretation:** In each team row, non-empty outcomes (anything except `emptyHistory.svg`) represent rounds that team won. The `emptyHistory.svg` entries represent rounds the team lost. The `title` attribute on winning outcomes shows the score at that point (e.g., "1-7", "8-13"). Loss outcomes have empty `title`.

**Round history team row HTML snippet (164779, first few rounds):**
```html
<div class="round-history-team-row">
  <img class="round-history-team" title="9 Pandas" src="..."/>
  <div class="round-history-bar"></div>
  <img class="round-history-outcome" src="/img/static/scoreboard/emptyHistory.svg" title=""/>
  <img class="round-history-outcome" src="/img/static/scoreboard/emptyHistory.svg" title=""/>
  <!-- ... more losses ... -->
  <img class="round-history-outcome" src="/img/static/scoreboard/ct_win.svg" title="1-7"/>
  <!-- ... -->
  <img class="round-history-outcome" src="/img/static/scoreboard/bomb_defused.svg" title="2-10"/>
  <div class="round-history-bar"></div>  <!-- half separator -->
  <img class="round-history-outcome" src="/img/static/scoreboard/bomb_exploded.svg" title="3-10"/>
  <img class="round-history-outcome" src="/img/static/scoreboard/t_win.svg" title="4-10"/>
  <!-- ... -->
</div>
```

### CT/T Side Round Extraction

From the breakdown row (`.match-info-row:first-child .right`):

- `span.ct-color` values = rounds won on CT side
- `span.t-color` values = rounds won on T side
- First `()` group = first half, Second `()` group = second half

**For team-left:**
- First half: first span in first `()` group is team-left's rounds on their starting side
- Second half: first span in second `()` group is team-left's rounds after side swap

**Determining starting side:**
- In the first `()` group, the first span's class tells team-left's starting side
- If first span is `.ct-color`, team-left started as CT
- If first span is `.t-color`, team-left started as T

**Example (164779, 8-13):**
```
(ct:2 : t:10) (t:6 : ct:3)
```
Team-left (9 Pandas) first half: 2 CT-side rounds. Team-right (FORZE) first half: 10 T-side rounds.
Team-left second half: 6 T-side rounds. Team-right second half: 3 CT-side rounds.
Team-left started CT. Team-right started T.

**Example (162345, 16-14 OT):**
```
(t:7 : ct:8) (ct:9 : t:6)
```
Team-left (n00rg) started T-side. First half: 7 T-side rounds. Second half: 9 CT-side rounds.

---

## Section 4: Stat Leader Boxes (Most-X-Box)

Located in `.most-x-box.standard-box` elements. 6 per page (consistent across all 12 samples).

| Stat Leader | `.most-x-title` Text | Value Element | Example | Extraction |
|-------------|---------------------|---------------|---------|------------|
| Most kills | "Most kills" | `.value` / `.valueName` | "21" | skip |
| Most damage | "Most damage" | `.value` / `.valueName` | "97.8" | skip |
| Most assists | "Most assists" | `.value` / `.valueName` | "5" | skip |
| Most AWP kills | "Most AWP kills" | `.value` / `.valueName` | "9" | skip |
| Most first kills | "Most first kills" | `.value` / `.valueName` | "4" | skip |
| Best rating | "Best rating 3.0" | `.value` / `.valueName` | "1.70" | skip |

Each box contains:
- Player image (`.img`)
- Player name (`.name a[href]`) with link to `/stats/players/{id}/{slug}`
- Stat label (`.most-x-title`)
- Stat value (`.value` / `.valueName`)

**Extraction status: skip** -- These are derivable from the per-player scoreboard data. Not needed as separate extraction targets.

---

## Section 5: Performance Graph (FusionChart)

| Element | CSS Selector | Data Type | Extraction |
|---------|-------------|-----------|------------|
| Chart container | `[data-fusionchart-config]` | JSON string | skip |

The `data-fusionchart-config` attribute contains a JSON object defining a bar2D FusionChart with player rating data. This is the same data available in the scoreboard tables, rendered as a visual chart.

**Extraction status: skip** -- Redundant with scoreboard data.

---

## Section 6: Navigation and Sub-Page Links

The page has a top navigation menu for switching between sub-pages of the same mapstatsid.

| Element | CSS Selector | Example href | Extraction |
|---------|-------------|-------------|------------|
| Nav container | `.stats-top-menu .tabs` | - | skip |
| Overview (current page) | `.stats-top-menu-item.selected` | `/stats/matches/mapstatsid/{id}/{slug}` | skip |
| Performance link | `a.stats-top-menu-item[href*="performance"]` | `/stats/matches/performance/mapstatsid/{id}/{slug}` | future |
| Economy link | `a.stats-top-menu-item[href*="economy"]` | `/stats/matches/economy/mapstatsid/{id}/{slug}` | future |
| Heatmaps link | `a.stats-top-menu-item[href*="heatmap"]` | `/stats/matches/heatmap/mapstatsid/{id}/{slug}?...` | skip |

The Economy link has a `<span class="new-feature">Beta</span>` badge.

---

## Section 7: Highlighted Player

| Element | CSS Selector | Count | Extraction |
|---------|-------------|-------|------------|
| Highlighted player | `.highlighted-player` | 0 | skip |

Not found on any of the 12 samples. This element may not exist on map stats pages (possibly only on player profile pages).

---

## Section 8: Eco-Adjusted Toggle

No explicit toggle element found in the HTML. The eco-adjusted data is embedded in hidden columns with class `eco-adjusted-data hidden`. The toggle is likely implemented via JavaScript that swaps `hidden` classes between `traditional-data` and `eco-adjusted-data` elements.

Searched selectors (all returned 0 results): `.eco-adjusted`, `[class*=eco]` (only found in table cells), `.toggle`, `.switch`, `[data-toggle]`, `[class*=adjusted]`.

**Conclusion:** No separate interaction needed to access eco-adjusted data. It's already in the HTML, just hidden by CSS class.

---

## Data Attributes Summary

All `data-*` attributes found on map stats pages:

| Attribute | Elements | Purpose | Useful? |
|-----------|----------|---------|---------|
| `data-unix` | `span` in match-info-box | Match timestamp (ms) | Yes |
| `data-time-format` | `span` in match-info-box | Date display format | No |
| `data-tooltip-id` | various `a` elements | Tooltip popup reference | No |
| `data-fusionchart-config` | chart container | Chart JSON configuration | No (redundant) |

---

## Verification Summary

All selectors verified programmatically against all 12 samples using `BeautifulSoup.select()`.

| Selector | Expected Count | Actual | Consistent | Notes |
|----------|---------------|--------|------------|-------|
| `.team-left` | 1 | 1 | 12/12 | |
| `.team-right` | 1 | 1 | 12/12 | |
| `.team-left a` | 1 | 1 | 12/12 | |
| `.team-right a` | 1 | 1 | 12/12 | |
| `.team-left .bold` | 1 | 1 | 12/12 | Score with won/lost class |
| `.team-right .bold` | 1 | 1 | 12/12 | Score with won/lost class |
| `.match-info-box` | 1 | 1 | 12/12 | |
| `.match-info-row` | 4 | 4 | 12/12 | Breakdown, rating, first kills, clutches |
| `.stats-table` | 6 | 6 | 12/12 | 2 total + 2 CT + 2 T |
| `.stats-table.totalstats` | 2 | 2 | 12/12 | |
| `.stats-table.totalstats tbody tr` | 10 | 10 | 12/12 | 5 per team |
| `.st-player` | 30 | 30 | 12/12 | 5 per table x 6 tables |
| `.st-player a` | 30 | 30 | 12/12 | |
| `.st-kills.traditional-data` | 12 | 12 | 12/12 | 2 tables x (header excluded) |
| `.st-assists` | 12 | 12 | 12/12 | |
| `.st-deaths.traditional-data` | 12 | 12 | 12/12 | |
| `.st-adr.traditional-data` | 12 | 12 | 12/12 | |
| `.st-rating` | 12 | 12 | 12/12 | Including headers |
| `.st-roundSwing` | varies | 0 or 12 | 11/12 have 12 | Absent on 162345 (Rating 2.0) |
| `.ratingDesc` | 6 | 6 | 12/12 | "2.0" or "3.0" |
| `.round-history-con` | 1 or 2 | 1 or 2 | 12/12 | 2 only on extended OT (206389) |
| `.round-history-team-row` | 2 or 4 | 2 or 4 | 12/12 | 4 only on extended OT |
| `img.round-history-outcome` | varies | 42-72 | 12/12 | Per page total (both rows) |
| `.round-history-bar` | varies | 4-12 | 12/12 | |
| `.most-x-box` | 6 | 6 | 12/12 | |
| `.most-x-title` | 6 | 6 | 12/12 | |
| `.stats-top-menu-item` | 4 | 4 | 12/12 | Overview, Performance, Economy, Heatmaps |
| `.standard-headline` | 3 or 4 | 3 or 4 | 12/12 | 4 when "Overtime" headline present |
| `[data-unix]` | 1 | 1 | 12/12 | |
| `.eco-adjusted-data` | 216 | 216 | 12/12 | Present on all pages (hidden) |
| `.traditional-data` | 216 | 216 | 12/12 | |

---

## Quick Reference: Phase 6 Extraction Targets

Fields the map stats parser should extract:

**Metadata:**
- team_left_name, team_left_id, team_left_score, team_left_won
- team_right_name, team_right_id, team_right_score, team_right_won
- event_name, event_id, match_date (unix_ms)
- map_name
- rating_version ("2.0" or "3.0")

**Half Breakdown:**
- half1_left, half1_right (with CT/T side identification)
- half2_left, half2_right
- ot_total (if present)
- team_left_starting_side (CT or T)

**Match Info:**
- team_rating_left, team_rating_right
- first_kills_left, first_kills_right
- clutches_won_left, clutches_won_right

**Per-Player Scoreboard (10 rows: 5 per team):**
- player_name, player_id, player_country
- opening_kills_deaths (Op.K-D: parse "{int} : {int}")
- multi_kills (MKs)
- kast (parse float from "66.7%")
- clutch_wins (1vsX)
- kills, headshots (parse from "14(9)")
- assists, flash_assists (parse from "2(0)")
- deaths, traded_deaths (parse from "15(2)")
- adr (float)
- round_swing (Rating 3.0 only, parse from "+2.90%")
- rating (float)

**Round History:**
- Round-by-round outcomes for both teams
- Round outcome type (ct_win, t_win, bomb_exploded, bomb_defused, stopwatch)
- Score at each round (from title attribute on winning rounds)
- Overtime rounds (from second container if present, or inline in first container)
