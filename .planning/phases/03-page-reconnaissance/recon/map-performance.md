# Map Performance Page Selector Map

**Page URL pattern:** `/stats/matches/performance/mapstatsid/{mapstatsid}/{slug}`
**Analyzed:** 2026-02-15
**Samples verified:** 12 performance page HTML files from `data/recon/performance-*.html.gz`
**Era coverage:** September 2023 through February 2026
**Tool:** BeautifulSoup 4 with lxml parser, programmatic `.select()` verification

## Table of Contents

1. [Page Structure Overview](#page-structure-overview)
2. [Rating Version Analysis (RECON-04)](#rating-version-analysis)
3. [Section 1: Page-Level Metadata](#section-1-page-level-metadata)
4. [Section 2: Performance Overview Table](#section-2-performance-overview-table)
5. [Section 3: Kill Matrix](#section-3-kill-matrix)
6. [Section 4: Player Performance Overview](#section-4-player-performance-overview)
7. [Section 5: Eco-Adjusted Stats](#section-5-eco-adjusted-stats)
8. [Section 6: Navigation and Other Elements](#section-6-navigation-and-other-elements)
9. [Annotated HTML Snippets](#annotated-html-snippets)
10. [Cross-Sample Verification Results](#cross-sample-verification-results)
11. [Extraction Summary for Phase 7](#extraction-summary-for-phase-7)

---

## Page Structure Overview

The HLTV map performance page has three main content sections, each preceded by a `.standard-headline`:

```
.stats-section.stats-match.stats-match-performance
  +-- .stats-match-menu.standard-box          (sub-page navigation: Overview/Performance/Economy/Heatmaps)
  +-- .stats-match-maps                        (map tabs for BO3/BO5; empty for BO1)
  +-- .standard-headline "Performance overview"
  +-- .overview.standard-box                   (team comparison table: Kills, Deaths, Assists)
  +-- .standard-headline "Kill matrix"
  +-- .killmatrix-menu                         (tabs: All / First kills / AWP kills)
  +-- .killmatrix-content#ALL-content          (visible: all kills matrix)
  +-- .killmatrix-content.hidden#FIRST_KILL-content
  +-- .killmatrix-content.hidden#AWP-content
  +-- .standard-headline "Player performance overview"
  +-- .player-overview.columns                 (per-player stat cards with FusionChart bar graphs)
```

**Key structural facts (verified across all 12 samples):**
- 3 `standard-headline` elements always present
- 3 kill matrix content divs always present (All, First kills, AWP kills)
- 10 FusionChart player cards always present (5 per team)
- 2 team columns in `.player-overview`
- 1 `.overview-table` with exactly 3 data rows (Kills, Deaths, Assists)

---

## Rating Version Analysis

**THIS IS THE CRITICAL FINDING FOR RECON-04.**

### Discovery: Rating 2.0 Pages Still Exist

Contrary to the prior assumption that Rating 3.0 was retroactively applied to ALL matches, **at least one sample retains Rating 2.0 format**:

| Sample | MapStatsID | Match Date | Era | Rating Version | Bar Count |
|--------|-----------|------------|-----|----------------|-----------|
| performance-162345.html.gz | 162345 | 2023-09-08 | Early CS2 | **Rating 2.0** | **6 bars** |
| performance-164779.html.gz | 164779 | 2023-10-21 | Early CS2 | Rating 3.0 | 7 bars |
| performance-164780.html.gz | 164780 | 2023-10-21 | Early CS2 | Rating 3.0 | 7 bars |
| performance-173424.html.gz | 173424 | 2024-04-12 | Mid 2024 | Rating 3.0 | 7 bars |
| performance-174112.html.gz | 174112 | 2024-04-21 | Mid 2024 | Rating 3.0 | 7 bars |
| performance-174116.html.gz | 174116 | 2024-04-21 | Mid 2024 | Rating 3.0 | 7 bars |
| performance-179210.html.gz | 179210 | 2024-07-19 | Mid 2024 | Rating 3.0 | 7 bars |
| performance-188093.html.gz | 188093 | 2024-11-14 | Late 2024 | Rating 3.0 | 7 bars |
| performance-206389.html.gz | 206389 | 2025-08-31 | 2025 | Rating 3.0 | 7 bars |
| performance-206393.html.gz | 206393 | 2025-08-31 | 2025 | Rating 3.0 | 7 bars |
| performance-219128.html.gz | 219128 | 2026-02-14 | 2026 | Rating 3.0 | 7 bars |
| performance-219151.html.gz | 219151 | 2026-02-14 | 2026 | Rating 3.0 | 7 bars |

**Result: 11/12 samples use Rating 3.0, 1/12 uses Rating 2.0.**

The Rating 2.0 sample (162345) is from a tier-3 match (n00rg vs FALKE, RTP Arena Fall Cup 2023). It is possible the retroactive application did not reach all matches, particularly low-tier ones. The parser MUST handle both formats.

### Side-by-Side Column Comparison

**Rating 2.0 (6 bars/metrics):**
```
KPR | DPR | KAST | Impact | ADR | Rating 2.0
```

**Rating 3.0 (7 bars/metrics):**
```
KPR | DPR | KAST | MK rating | Swing | ADR | Rating 3.0
```

**Differences:**
| Metric | Rating 2.0 | Rating 3.0 |
|--------|-----------|------------|
| KPR | Present | Present (same) |
| DPR | Present | Present (same) |
| KAST | Present | Present (same) |
| Impact | **Present** (single metric combining multi-kills, openers, clutches) | **Absent** |
| MK rating | Absent | **Present** (multi-kill rating, split from Impact) |
| Swing | Absent | **Present** (Round Swing: +/- percentage) |
| ADR | Present | Present (same) |
| Overall Rating | Labeled "Rating 2.0" | Labeled "Rating 3.0" |

### Detection Strategy

The rating version is embedded in the FusionChart JSON data on each player card. Detection is reliable and unambiguous:

```python
import json

def detect_rating_version(soup):
    """Detect whether performance page uses Rating 2.0 or 3.0.

    Returns: '2.0', '3.0', or 'unknown'

    Detection is based on the FusionChart bar labels in player cards.
    Rating 2.0 has 6 bars ending with "Rating 2.0".
    Rating 3.0 has 7 bars ending with "Rating 3.0".
    """
    chart_el = soup.select_one('[data-fusionchart-config]')
    if not chart_el:
        return 'unknown'

    config = json.loads(chart_el['data-fusionchart-config'])
    data = config['dataSource']['data']
    labels = [d['label'] for d in data]

    # Primary detection: last bar label
    if labels and labels[-1] == 'Rating 3.0':
        return '3.0'
    if labels and labels[-1] == 'Rating 2.0':
        return '2.0'

    # Fallback: check for version-specific metrics
    label_set = set(labels)
    if 'MK rating' in label_set or 'Swing' in label_set:
        return '3.0'
    if 'Impact' in label_set:
        return '2.0'

    return 'unknown'
```

**Why this strategy is reliable:**
1. The FusionChart JSON is always present in the initial HTML (not JS-loaded)
2. The label text is explicit: "Rating 2.0" vs "Rating 3.0"
3. The bar count differs (6 vs 7), providing a secondary signal
4. Verified against 12 samples with 100% accuracy

**Alternative detection signals (less reliable, not recommended):**
- Bar count (6 vs 7) -- works but fragile if HLTV adds/removes metrics
- Presence of "Impact" text anywhere on page -- could match unrelated content
- Match date heuristic -- unreliable since retroactive application is inconsistent

---

## Section 1: Page-Level Metadata

### Sub-Page Navigation Menu

| Field | CSS Selector | Data Type | Required | Example Value | Extraction |
|-------|-------------|-----------|----------|---------------|------------|
| event_name | `.stats-match-menu .menu-header` | string | always | "PGL Cluj-Napoca 2026" | **extract** |
| current_tab | `.stats-match-menu .stats-top-menu-item-link.selected` | string | always | "Performance" | skip (always "Performance" on this page) |
| overview_url | `.stats-match-menu a[href*="/stats/matches/mapstatsid/"]` | url | always | "/stats/matches/mapstatsid/219128/..." | skip |
| economy_url | `.stats-match-menu a[href*="/economy/"]` | url | always | "/stats/matches/economy/mapstatsid/219128/..." | skip |
| heatmap_url | `.stats-match-menu a[href*="/heatmap/"]` | url | always | "/stats/matches/heatmap/mapstatsid/219128/..." | skip |

**Menu structure:**

```html
<div class="stats-match-menu standard-box">
  <div class="menu-header">PGL Cluj-Napoca 2026</div>
  <div class="stats-top-menu">
    <div class="tabs">
      <a class="stats-top-menu-item stats-top-menu-item-link" href="/stats/matches/mapstatsid/219128/...">Overview</a>
      <a class="stats-top-menu-item stats-top-menu-item-link selected" href="/stats/matches/performance/...">Performance</a>
      <a class="stats-top-menu-item stats-top-menu-item-link" href="/stats/matches/economy/...">Economy<span class="new-feature">Beta</span></a>
      <a class="stats-top-menu-item stats-top-menu-item-link" href="/stats/matches/heatmap/...">Heatmaps</a>
    </div>
  </div>
</div>
```

### Map Tabs (BO3/BO5 only)

| Field | CSS Selector | Data Type | Required | Example Value | Extraction |
|-------|-------------|-----------|----------|---------------|------------|
| map_score | `.stats-match-map .stats-match-map-result-score` | string | BO3/BO5 | "13 - 11" | skip (available on overview) |
| map_name_short | `.stats-match-map .dynamic-map-name-short` | string | BO3/BO5 | "mrg" | skip |
| map_name_full | `.stats-match-map .dynamic-map-name-full` | string | BO3/BO5 | "Mirage" | skip (available on overview) |
| active_map | `.stats-match-map:not(.inactive)` | boolean | BO3/BO5 | (current map) | skip |

**Behavior by format:**
- **BO1:** `.stats-match-maps` exists but is empty (no child `<a>` elements)
- **BO3:** 4 tabs (1 series overview + 3 maps); active map lacks `inactive` class
- **BO5:** Expected 6 tabs (1 series + 5 maps); not verified (no BO5 performance sample with all maps)

Tab count by sample:
- BO1 (162345, 173424, 179210, 188093): 0 tabs
- BO3 maps (164779, 164780, 174112, 174116, 206389, 206393, 219128, 219151): 3-4 tabs

---

## Section 2: Performance Overview Table

Container: `.overview.standard-box > .overview-table`

### Overview Table Rows

| Field | CSS Selector | Data Type | Required | Example Value | Extraction |
|-------|-------------|-----------|----------|---------------|------------|
| team1_kills | `.overview-table tr:nth-child(2) .team1-column` | int | always | "76" | **extract** |
| team2_kills | `.overview-table tr:nth-child(2) .team2-column` | int | always | "81" | **extract** |
| team1_deaths | `.overview-table tr:nth-child(3) .team1-column` | int | always | "81" | **extract** |
| team2_deaths | `.overview-table tr:nth-child(3) .team2-column` | int | always | "76" | **extract** |
| team1_assists | `.overview-table tr:nth-child(4) .team1-column` | int | always | "20" | **extract** |
| team2_assists | `.overview-table tr:nth-child(4) .team2-column` | int | always | "24" | **extract** |

**Preferred selector approach:** Iterate rows and match by `.name-column` text rather than `nth-child`, for resilience:

```python
for row in soup.select('.overview-table tr'):
    label = row.select_one('.name-column')
    if not label:
        continue  # header row
    name = label.get_text(strip=True)
    team1_val = row.select_one('.team1-column').get_text(strip=True)
    team2_val = row.select_one('.team2-column').get_text(strip=True)
    # name is "Kills", "Deaths", or "Assists"
```

**Row labels (consistent across all 12 samples):** Kills, Deaths, Assists

**Chart column:** Each data row has a `.chart-column` with two `<span>` elements (`.chart.chart1` and `.chart.chart2`) showing proportional width bars via `data-inline-style` attribute. These are visual only -- the numeric values in `.team1-column` and `.team2-column` are sufficient.

### Team Identity in Overview Table

The header row (first `<tr>`) contains team logos in `.team1-column` and `.team2-column`:

```html
<th class="team1-column">
  <img alt="Vitality" class="team-logo day-only" src="..." title="Vitality"/>
  <img alt="Vitality" class="team-logo night-only" src="..." title="Vitality"/>
</th>
```

Team names can be extracted from the `alt` or `title` attribute of the `img.team-logo` elements.

| Field | CSS Selector | Data Type | Required | Extraction |
|-------|-------------|-----------|----------|------------|
| team1_name (from overview) | `.overview-table th.team1-column img.team-logo` `[alt]` | string | always | skip (use player-overview header instead) |
| team2_name (from overview) | `.overview-table th.team2-column img.team-logo` `[alt]` | string | always | skip |

---

## Section 3: Kill Matrix

Container: `.killmatrix-menu` + `.killmatrix-content` (3 content divs)

### Kill Matrix Tabs

| Tab | Element ID | Selector | Hidden? |
|-----|-----------|----------|---------|
| All kills | `ALL-content` | `.killmatrix-content#ALL-content` | No (visible by default) |
| First kills | `FIRST_KILL-content` | `.killmatrix-content#FIRST_KILL-content` | Yes (class `hidden`) |
| AWP kills | `AWP-content` | `.killmatrix-content#AWP-content` | Yes (class `hidden`) |

**All three tabs are present in the initial HTML.** No JavaScript interaction needed to access hidden tabs -- they are in the DOM with class `hidden`, which can be read directly.

Menu tabs:

```html
<div class="killmatrix-menu">
  <div class="killmatrix-menu-link bold" id="ALL">All</div>
  <div class="killmatrix-menu-link" id="FIRST_KILL">First kills</div>
  <div class="killmatrix-menu-link" id="AWP">AWP kills</div>
</div>
```

### Kill Matrix Table Structure

Each `.killmatrix-content` contains one `.stats-table`:

- **Header row** (class `killmatrix-topbar`): Team 1 players as column headers
- **Data rows**: Team 2 players as row headers, with cells showing kills:deaths

**Table layout:** Team 2 players (rows) vs Team 1 players (columns).
Each cell shows `team2_kills:team1_kills` (row player kills : column player kills).

| Field | CSS Selector | Data Type | Required | Example Value | Extraction |
|-------|-------------|-----------|----------|---------------|------------|
| column_player_name | `.killmatrix-topbar td a` | string | always | "ZywOo" | **extract** |
| column_player_id | `.killmatrix-topbar td a[href]` | int | always | Parse from `/stats/players/{id}/{slug}` | **extract** |
| column_player_team | `.killmatrix-topbar td.team1` | presence | always | class `team1` on `<td>` | **extract** |
| row_player_name | `.killmatrix-content tr:not(.killmatrix-topbar) td.team2 a` | string | always | "malbsMd" | **extract** |
| row_player_id | `.killmatrix-content tr:not(.killmatrix-topbar) td.team2 a[href]` | int | always | Parse from `/stats/players/{id}/{slug}` | **extract** |
| cell_team2_kills | `td.text-center span.team2-player-score` | int | always | "6" | **extract** |
| cell_team1_kills | `td.text-center span.team1-player-score` | int | always | "4" | **extract** |

**Cell HTML structure:**

```html
<td class="text-center">
  <span class="team2-player-score">6</span>:<span class="team1-player-score">4</span>
</td>
```

The cell text renders as "6:4" meaning the row player (team 2) got 6 kills against the column player (team 1) who got 4 kills back.

**Player ID extraction pattern from kill matrix:**
- Column headers: `/stats/players/{player_id}/{slug}` (note: `/stats/players/`, not `/player/`)
- Row headers: `/stats/players/{player_id}/{slug}` (same pattern)

```python
import re
def extract_player_id_from_stats_href(href):
    """Extract player ID from /stats/players/{id}/{slug} pattern."""
    m = re.search(r'/stats/players/(\d+)/', href)
    return int(m.group(1)) if m else None
```

### Kill Matrix Dimensions

- **Always 5x5** (5 players per team)
- Column headers = team 1 players (class `team1` on `<td>`)
- Row headers = team 2 players (class `team2` on `<td>`)
- Each of the 3 kill matrix types (All, First kills, AWP) has the same players in the same order

---

## Section 4: Player Performance Overview

Container: `.player-overview.columns`

### Team Structure

Two `.col` divs, one per team:

```
.player-overview.columns
  +-- .col (team 1)
  |   +-- .players-team-header
  |   +-- .highlighted-player (player 1)
  |   |   +-- .standard-box
  |   +-- .highlighted-player (player 2)
  |   |   +-- .standard-box
  |   +-- .highlighted-player (player 3)
  |   |   +-- .standard-box
  |   +-- .highlighted-player (player 4)
  |   |   +-- .standard-box
  |   +-- .highlighted-player (player 5)
  |       +-- .standard-box
  +-- .col (team 2)
      +-- .players-team-header
      +-- .highlighted-player (player 1) ... (same structure)
```

**Note:** Despite the class name `highlighted-player`, ALL 5 players per team are wrapped in this class. There is no structural distinction between the "highlighted" (best-performing) player and others. Each player gets one `.highlighted-player > .standard-box`.

### Team Header

| Field | CSS Selector | Data Type | Required | Example Value | Extraction |
|-------|-------------|-----------|----------|---------------|------------|
| team_name | `.players-team-header .label-and-text` | string | always | "Vitality" | **extract** |
| team_flag | `.players-team-header .label-and-text img.flag` `[title]` | string | always | "Europe" | skip |
| team_logo | `.players-team-header img.team-logo` `[alt]` | string | always | "Vitality" | skip (redundant) |

**Team header HTML:**

```html
<div class="players-team-header">
  <span class="label-and-text">
    <img alt="Europe" class="label flag" src="/img/static/flags/30x20/EU.gif" title="Europe"/>
    Vitality
  </span>
  <img alt="Vitality" class="team-logo day-only" src="..." title="Vitality"/>
  <img alt="Vitality" class="team-logo night-only" src="..." title="Vitality"/>
</div>
```

**Note:** No team ID link is present in the `.players-team-header`. The team name is text content of `.label-and-text` (after the flag image). Team ID must be obtained from the match overview page or player hrefs.

### Player Card

Each player card is inside `.highlighted-player > .standard-box`:

| Field | CSS Selector (relative to `.standard-box`) | Data Type | Required | Example Value | Extraction |
|-------|---------------------------------------------|-----------|----------|---------------|------------|
| player_nick | `.headline .player-nick` | string | always | "ZywOo" | **extract** |
| player_id | `.headline a[href]` | int | always | Parse from `/player/{id}/{slug}` -> 11893 | **extract** |
| player_full_name | `.headline .gtSmartphone-only` | string | always | "Mathieu 'ZywOo' Herbaut" | skip (available from profile) |
| player_flag | `.headline img.flag` `[title]` | string | always | "France" | skip |
| player_photo_url | `.picture` `[src]` | url | always | CDN URL | skip |
| chart_data | `[data-fusionchart-config]` | JSON | always | (see below) | **extract** |

**Player ID extraction from player cards:**
```python
import re
def extract_player_id_from_player_href(href):
    """Extract player ID from /player/{id}/{slug} pattern."""
    m = re.search(r'/player/(\d+)/', href)
    return int(m.group(1)) if m else None
```

**Note on two different player link patterns:**
- Player cards use: `/player/{id}/{slug}` (e.g., `/player/11893/zywoo`)
- Kill matrix uses: `/stats/players/{id}/{slug}` (e.g., `/stats/players/11893/zywoo`)
- Both contain the same numeric player ID

### FusionChart Data (Primary Data Source)

**This is where ALL per-player performance metrics live.** The data is embedded as JSON in the `data-fusionchart-config` attribute of a `<worker-ignore>` element with class `graph small`.

Selector: `.standard-box [data-fusionchart-config]`

The JSON structure:

```json
{
  "type": "bar2D",
  "renderAt": "uniqueChartId338721280",
  "dataSource": {
    "chart": { /* rendering settings, not useful for extraction */ },
    "data": [
      {
        "label": "KPR",
        "value": "1.59",
        "color": "00707b",
        "tooltext": "Kills per round: 0.88",
        "displayValue": "0.88"
      },
      /* ... more bars ... */
    ],
    "trendlines": [
      {
        "line": [
          {
            "startvalue": "1.0",
            "endvalue": "1.0",
            "displayValue": "Avg"
          }
        ]
      }
    ]
  }
}
```

**Critical distinction between `value` and `displayValue`:**
- `value`: The normalized bar height for chart rendering (relative to yAxisMaxValue). NOT the actual stat.
- `displayValue`: The actual stat value to extract. This is what appears on screen.
- `tooltext`: Human-readable description with the stat value. Useful for verification.

### Rating 3.0 Chart Bars (7 bars)

| Bar Index | Label | displayValue Format | tooltext Pattern | Data Type | Extraction |
|-----------|-------|-------------------|-----------------|-----------|------------|
| 0 | `KPR` | "0.88" | "Kills per round: 0.88" | float | **extract** |
| 1 | `DPR` | "0.54" | "Deaths / round: 0.54" | float | **extract** |
| 2 | `KAST` | "66.7%" | "Kill, assist, survived or traded: 66.7%" | percentage string | **extract** |
| 3 | `MK rating` | "1.43" | "Multi-kill rating: 1.43" | float | **extract** |
| 4 | `Swing` | "+12.23%" | "Round Swing: +12.23%" | signed percentage string | **extract** |
| 5 | `ADR` | "102.6" | "Damage / round: 102.6" | float | **extract** |
| 6 | `Rating 3.0` | "1.85" | "" (empty) | float | **extract** |

### Rating 2.0 Chart Bars (6 bars)

| Bar Index | Label | displayValue Format | tooltext Pattern | Data Type | Extraction |
|-----------|-------|-------------------|-----------------|-----------|------------|
| 0 | `KPR` | "0.97" | "Kills per round: 0.97" | float | **extract** |
| 1 | `DPR` | "0.57" | "Deaths / round: 0.57" | float | **extract** |
| 2 | `KAST` | "90.0%" | "Kill, assist, survived or traded: 90.0%" | percentage string | **extract** |
| 3 | `Impact` | "1.33" | "Impact rating: 1.33" | float | **extract** |
| 4 | `ADR` | "98.0" | "Damage / round: 98.0" | float | **extract** |
| 5 | `Rating 2.0` | "1.54" | "" (empty) | float | **extract** |

### Extraction Pseudocode for Player Metrics

```python
import json, re

def extract_player_performance(box_element, rating_version):
    """Extract all performance metrics from a player card .standard-box element.

    Args:
        box_element: BeautifulSoup element for .standard-box
        rating_version: '2.0' or '3.0' (from detect_rating_version)

    Returns: dict with player metrics
    """
    result = {}

    # Player identity
    link = box_element.select_one('.headline a[href]')
    result['player_nick'] = box_element.select_one('.player-nick').get_text(strip=True)
    m = re.search(r'/player/(\d+)/', link['href'])
    result['player_id'] = int(m.group(1))

    # Chart data
    chart_el = box_element.select_one('[data-fusionchart-config]')
    config = json.loads(chart_el['data-fusionchart-config'])
    bars = config['dataSource']['data']

    # Map bars by label
    bar_map = {bar['label']: bar['displayValue'] for bar in bars}

    # Common metrics
    result['kpr'] = float(bar_map['KPR'])
    result['dpr'] = float(bar_map['DPR'])
    result['kast'] = float(bar_map['KAST'].rstrip('%'))  # "66.7%" -> 66.7
    result['adr'] = float(bar_map['ADR'])

    # Version-specific metrics
    if rating_version == '3.0':
        result['mk_rating'] = float(bar_map['MK rating'])
        result['round_swing'] = float(bar_map['Swing'].rstrip('%'))  # "+12.23%" -> 12.23 (note: keeps sign)
        result['rating'] = float(bar_map['Rating 3.0'])
        result['rating_version'] = '3.0'
        result['impact'] = None
    else:  # 2.0
        result['impact'] = float(bar_map['Impact'])
        result['rating'] = float(bar_map['Rating 2.0'])
        result['rating_version'] = '2.0'
        result['mk_rating'] = None
        result['round_swing'] = None

    return result
```

**Parsing notes for Swing/KAST displayValue:**
- KAST: Always ends with `%`, e.g., "66.7%" -- strip `%` and parse as float
- Swing: Always starts with `+` or `-` and ends with `%`, e.g., "+12.23%" or "-1.93%" -- strip `%` and parse as float (sign preserved by `float()`)

---

## Section 5: Eco-Adjusted Stats

**Eco-adjusted stats (eK-eD, eADR, eKAST) are NOT present on the performance page.**

Comprehensive search across all 12 performance page samples found:
- Zero occurrences of "eK-eD", "eADR", "eKAST" text
- Zero occurrences of "eco-adjusted" text
- Zero `[data-eco]` or `[data-eco-adjusted]` attributes
- No toggle elements related to eco-adjustment

**Where eco-adjusted stats live:** The map stats overview page (`/stats/matches/mapstatsid/{id}/{slug}`) contains:
- `.eco-adjusted-container` with toggle divs
- Column headers with `eK-eD`, `eADR`, `eKAST` in the `.stats-table`
- The eco-adjusted toggle and data are present in the initial HTML of the map stats page (no JS interaction needed)

**Implication for Phase 7 parser:** The performance page parser does NOT need eco-adjusted handling. Eco-adjusted stats should be extracted from the map stats overview page parser (Phase 5/6), not the performance page parser.

---

## Section 6: Navigation and Other Elements

### Sub-Page Menu (`.stats-match-menu`)

Present on all samples. Contains:
- **Event name** in `.menu-header`
- **Tab links** in `.tabs`: Overview, Performance (selected), Economy (with "Beta" badge), Heatmaps

| Field | CSS Selector | Example | Extraction |
|-------|-------------|---------|------------|
| event_name | `.stats-match-menu .menu-header` | "PGL Cluj-Napoca 2026" | **extract** (if not already from overview page) |
| economy_beta_badge | `.stats-match-menu .new-feature` | "Beta" | skip (informational) |

### Map Image in Tabs

Each map tab contains a map image:

```html
<div class="stats-match-map-holder">
  <img class="stats-match-map-img" src="/img/static/statsmatchmaps/mirage.png"/>
</div>
```

Map image filenames are lowercase map names (mirage.png, inferno.png, nuke.png, anubis.png, overpass.png). Not needed for extraction.

### Elements NOT Present on Performance Page

The following elements found on other HLTV pages are **absent** from the performance page:
- `.st-kills`, `.st-deaths`, `.st-assists`, `.st-adr`, `.st-rating` (these are on map stats overview page)
- `.round-history-team-row`, `.round-history-outcome` (map stats overview page)
- `.most-x-box` (map stats overview page)
- `.veto-box` (match overview page)
- `.stream-box` (match overview page)
- Eco-adjusted toggle (map stats overview page)

### Performance Charts (FusionCharts)

Each player card contains a FusionChart bar graph. The chart data is in the `data-fusionchart-config` JSON attribute (documented in Section 4). The actual rendered SVG chart is also present in the HTML but is not useful for data extraction.

**Chart rendering details (for reference, not extraction):**
- Chart type: `bar2D` (horizontal bars)
- `yAxisMaxValue`: Set to the maximum bar value across all players (e.g., "2.63")
- Trendline at value 1.0 labeled "Avg" (the average benchmark line)
- Color coding: varies by performance level (green `518823` for good, orange `e0a440` for average, blue `00707b` for various metrics, dark blue `0d5c9a` for overall rating)

---

## Annotated HTML Snippets

### Snippet 1: Player Card (Rating 3.0)

Source: `performance-219128.html.gz` (Vitality vs G2, 2026)

```html
<!-- Each player is wrapped in .highlighted-player > .standard-box -->
<div class="highlighted-player">
  <div class="standard-box">
    <!-- Player identity -->
    <div class="headline">
      <span>
        <img alt="France" class="flag flag" src="/img/static/flags/30x20/FR.gif" title="France"/>
        <a href="/player/11893/zywoo">
          <!-- Desktop: full name with nick highlighted -->
          <span class="gtSmartphone-only">
            Mathieu '<span class="player-nick">ZywOo</span>' Herbaut
          </span>
          <!-- Mobile: nick only -->
          <span class="smartphone-only">ZywOo</span>
        </a>
      </span>
      <span class="header-info"></span>  <!-- always empty on performance page -->
    </div>
    <!-- Photo and chart -->
    <div class="picture-and-chart">
      <div class="player-picture-holder small">
        <img alt="Mathieu 'ZywOo' Herbaut" class="picture" src="..." title="..."/>
      </div>
      <div class="facts">
        <!-- THE KEY DATA ELEMENT: FusionChart with all metrics -->
        <worker-ignore class="graph small" data-fusionchart-config='{ JSON DATA }'>
          <span class="fusioncharts-container" ...>
            <svg ...><!-- rendered chart --></svg>
          </span>
        </worker-ignore>
      </div>
    </div>
  </div>
</div>
```

### Snippet 2: Player Card FusionChart JSON (Rating 3.0)

```json
{
  "type": "bar2D",
  "dataSource": {
    "data": [
      {"label": "KPR",        "value": "1.59", "displayValue": "0.88",     "tooltext": "Kills per round: 0.88"},
      {"label": "DPR",        "value": "1.13", "displayValue": "0.54",     "tooltext": "Deaths / round: 0.54"},
      {"label": "KAST",       "value": "1.05", "displayValue": "66.7%",    "tooltext": "Kill, assist, survived or traded: 66.7%"},
      {"label": "MK rating",  "value": "1.43", "displayValue": "1.43",     "tooltext": "Multi-kill rating: 1.43"},
      {"label": "Swing",      "value": "2.63", "displayValue": "+12.23%",  "tooltext": "Round Swing: +12.23%"},
      {"label": "ADR",        "value": "1.87", "displayValue": "102.6",    "tooltext": "Damage / round: 102.6"},
      {"label": "Rating 3.0", "value": "1.85", "displayValue": "1.85",     "tooltext": ""}
    ],
    "trendlines": [{"line": [{"startvalue": "1.0", "displayValue": "Avg"}]}]
  }
}
```

### Snippet 3: Player Card FusionChart JSON (Rating 2.0)

Source: `performance-162345.html.gz` (n00rg vs FALKE, September 2023)

```json
{
  "type": "bar2D",
  "dataSource": {
    "data": [
      {"label": "KPR",        "value": "1.73", "displayValue": "0.97",  "tooltext": "Kills per round: 0.97"},
      {"label": "DPR",        "value": "1.47", "displayValue": "0.57",  "tooltext": "Deaths / round: 0.57"},
      {"label": "KAST",       "value": "1.66", "displayValue": "90.0%", "tooltext": "Kill, assist, survived or traded: 90.0%"},
      {"label": "Impact",     "value": "1.33", "displayValue": "1.33",  "tooltext": "Impact rating: 1.33"},
      {"label": "ADR",        "value": "1.52", "displayValue": "98.0",  "tooltext": "Damage / round: 98.0"},
      {"label": "Rating 2.0", "value": "1.54", "displayValue": "1.54",  "tooltext": ""}
    ],
    "trendlines": [{"line": [{"startvalue": "1.0", "displayValue": "Avg"}]}]
  }
}
```

### Snippet 4: Kill Matrix Table (All kills)

```html
<div class="killmatrix-content" id="ALL-content">
  <table class="stats-table">
    <tbody>
      <!-- Header: Team 1 players as columns -->
      <tr class="killmatrix-topbar">
        <td class="" role="columnheader"></td>  <!-- empty corner cell -->
        <td class="text-center team1" role="columnheader">
          <span class="gtSmartphone-only">
            <img alt="Israel" class="flag" src="..." title="Israel"/>
          </span>
          <a data-tooltip-id="..." href="/stats/players/16693/flamez">flameZ</a>
        </td>
        <!-- ... 4 more team1 player columns ... -->
      </tr>
      <!-- Data rows: Team 2 players as rows -->
      <tr>
        <td class="team2">
          <span class="gtSmartphone-only">
            <img alt="Guatemala" class="flag" src="..." title="Guatemala"/>
          </span>
          <a data-tooltip-id="..." href="/stats/players/11617/malbsmd">malbsMd</a>
        </td>
        <td class="text-center">
          <span class="team2-player-score">6</span>:<span class="team1-player-score">4</span>
        </td>
        <!-- ... 4 more cells (one per team1 player) ... -->
      </tr>
      <!-- ... 4 more team2 player rows ... -->
    </tbody>
  </table>
</div>
```

### Snippet 5: Overview Table

```html
<div class="overview standard-box">
  <table class="overview-table">
    <tbody>
      <tr>
        <th class="name-column"></th>
        <th class="team1-column">
          <img alt="Vitality" class="team-logo day-only" src="..." title="Vitality"/>
          <img alt="Vitality" class="team-logo night-only" src="..." title="Vitality"/>
        </th>
        <th class="chart-column"><span class="chart-middel">...</span></th>
        <th class="team2-column">
          <img alt="G2" class="team-logo" src="..." title="G2"/>
        </th>
      </tr>
      <tr>
        <td class="name-column">Kills</td>
        <td class="team1-column">76</td>
        <td class="chart-column">
          <span class="chart chart1" data-inline-style='{"width":"48.407642%"}'>...</span>
          <span class="chart chart2" data-inline-style='{"width":"51.592358%"}'>...</span>
        </td>
        <td class="team2-column">81</td>
      </tr>
      <!-- Deaths and Assists rows follow same structure -->
    </tbody>
  </table>
</div>
```

---

## Cross-Sample Verification Results

All CSS selectors were tested programmatically against all 12 performance page HTML samples using BeautifulSoup `.select()`.

| Selector | Description | 162345 | 164779 | 164780 | 173424 | 174112 | 174116 | 179210 | 188093 | 206389 | 206393 | 219128 | 219151 |
|----------|-------------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| `.stats-section.stats-match-performance` | Main section | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.standard-headline` (count=3) | Section headers | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.overview-table` | Overview table | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.overview-table tr` (count=4) | Table rows (1 header + 3 data) | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.killmatrix-content` (count=3) | Kill matrix types | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.killmatrix-menu .killmatrix-menu-link` (count=3) | Menu tabs | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `[data-fusionchart-config]` (count=10) | Player charts | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.player-overview.columns` | Player overview | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.player-overview > .col` (count=2) | Team columns | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.players-team-header` (count=2) | Team headers | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.highlighted-player` (count=10) | Player wrappers | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.standard-box` (in .player-overview, count=10) | Player cards | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.stats-match-menu .menu-header` | Event name | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |
| `.stats-match-menu a` (count=4) | Sub-page links | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK |

**Rating version by sample:**
| Sample | Last bar label | Bar count | Detected version |
|--------|---------------|-----------|-----------------|
| 162345 | "Rating 2.0" | 6 | 2.0 |
| 164779 | "Rating 3.0" | 7 | 3.0 |
| All others | "Rating 3.0" | 7 | 3.0 |

**Notable variation:**
- **Map tabs count** varies: 0 (BO1), 3 (BO3 maps 2+3 only), 4 (BO3 with series tab)
- **Page size:** 11 samples are ~6.0-6.2M chars; 1 sample (206389) is ~219K chars. The smaller page has identical structure -- the size difference is in navigation/ad chrome, not stats content.

---

## Extraction Summary for Phase 7

### Fields to Extract (by priority)

**High Priority (core performance metrics):**

| Field | Source | Selector Path | Parse Method |
|-------|--------|--------------|-------------|
| player_id | Player card | `.headline a[href]` -> regex `/player/(\d+)/` | int |
| player_nick | Player card | `.headline .player-nick` | text |
| kpr | FusionChart JSON | `data[label="KPR"].displayValue` | float |
| dpr | FusionChart JSON | `data[label="DPR"].displayValue` | float |
| kast_pct | FusionChart JSON | `data[label="KAST"].displayValue` | strip %, float |
| adr | FusionChart JSON | `data[label="ADR"].displayValue` | float |
| rating | FusionChart JSON | `data[label="Rating 3.0" or "Rating 2.0"].displayValue` | float |
| rating_version | FusionChart JSON | last bar label | "2.0" or "3.0" |
| mk_rating | FusionChart JSON (3.0 only) | `data[label="MK rating"].displayValue` | float or None |
| round_swing | FusionChart JSON (3.0 only) | `data[label="Swing"].displayValue` | strip %, float or None |
| impact | FusionChart JSON (2.0 only) | `data[label="Impact"].displayValue` | float or None |

**Medium Priority (team-level and kill matrix):**

| Field | Source | Selector Path | Parse Method |
|-------|--------|--------------|-------------|
| team_name | Team header | `.players-team-header .label-and-text` | text |
| team_kills | Overview table | `.overview-table` row "Kills" `.team{N}-column` | int |
| team_deaths | Overview table | `.overview-table` row "Deaths" `.team{N}-column` | int |
| team_assists | Overview table | `.overview-table` row "Assists" `.team{N}-column` | int |
| kill_matrix_all | Kill matrix | `#ALL-content .stats-table` cells | dict[str, dict[str, tuple[int,int]]] |
| kill_matrix_first | Kill matrix | `#FIRST_KILL-content .stats-table` cells | dict (same structure) |
| kill_matrix_awp | Kill matrix | `#AWP-content .stats-table` cells | dict (same structure) |
| event_name | Menu header | `.stats-match-menu .menu-header` | text |

**Low Priority (skip for initial implementation):**

| Field | Reason to Skip |
|-------|---------------|
| Player photos | Not useful for analysis |
| Chart colors | Visual rendering only |
| Chart `value` (bar height) | Normalized for rendering; `displayValue` has the real stat |
| Map tab images | Not useful for analysis |
| Day/night logo variants | Visual theming only |

### Data NOT Available on Performance Page

The following data often expected from performance analysis is NOT on this page:

| Data | Where to Find Instead |
|------|----------------------|
| Opening kills/deaths count | Map stats overview page (`.st-fkdiff`) |
| Multi-kill round counts (2k, 3k, 4k, 5k) | **Not found on any sub-page** -- may require player stats aggregate pages |
| Clutch stats (1v1 through 1v5) | **Not found on any sub-page** -- may require player stats aggregate pages |
| Eco-adjusted stats (eK-eD, eADR, eKAST) | Map stats overview page (`.eco-adjusted-container`) |
| Total kills/deaths/assists per player | Map stats overview page (`.st-kills`, `.st-deaths`, etc.) |
| K/D ratio, K/D diff | Map stats overview page (`.st-kdratio`, `.st-kddiff`) |
| First kills diff | Map stats overview page (`.st-fkdiff`) |

**Important for Phase 7 planning:** The performance page provides RATES (KPR, DPR, KAST%) and RATINGS (MK rating, Swing, Impact, ADR, overall Rating) via FusionChart JSON, plus KILL MATRICES (head-to-head kills). It does NOT provide per-player kill/death/assist COUNTS or opening/clutch/multi-kill COUNTS. Those are on the map stats overview page.

The plan's expected columns (opening kills, opening deaths, opening kill rating, multi-kill round counts, clutch stats) are **not present on the performance page**. Phase 7 should either:
1. Source those from the map stats overview page (Phase 5/6)
2. Accept that per-map-match multi-kill and clutch counts may not be available from standard match pages

---

## Notes for Parser Implementation

1. **JSON parsing is the primary extraction method.** Unlike other HLTV pages that use HTML tables with CSS classes, the performance page stores metrics in FusionChart JSON. Use `json.loads()` on the `data-fusionchart-config` attribute.

2. **Team assignment:** Team 1 = first `.col` in `.player-overview`; Team 2 = second `.col`. In kill matrix, column headers have class `team1`, row headers have class `team2`.

3. **Player ordering:** Players appear in the order HLTV determines (typically by rating, highest first). The same player order appears in both the player cards and kill matrix.

4. **Kill matrix values are symmetric:** If row-player kills column-player X times, the reverse appears in a different cell. The matrix is NOT symmetric in values -- each cell shows unique kill counts between the specific pair.

5. **The `value` field in FusionChart data is NOT the stat.** It is a normalized value for chart rendering. Always use `displayValue` for the actual statistic.

6. **Percentage parsing:** KAST uses "66.7%" format, Swing uses "+12.23%" or "-1.93%" format. Both need `%` stripped before `float()` conversion. Python's `float()` handles the `+`/`-` sign correctly.

7. **Empty `tooltext` on Rating bar:** The overall Rating bar (last bar) has an empty `tooltext` string. This is consistent across all samples and both rating versions.

8. **No page-specific retry logic needed:** All 12 samples loaded successfully with valid content. The smallest sample (206389, 219K chars) still contains all expected elements.
