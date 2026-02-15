# Map Economy Page Selector Map

**Page type:** Map economy sub-page
**URL pattern:** `/stats/matches/economy/mapstatsid/{id}/{slug}`
**Samples analyzed:** 12 economy HTML files spanning 2023-2026
**Analysis date:** 2026-02-15
**Status:** Economy tab is marked "Beta" on HLTV

## 1. Page Structure Overview

The economy page lives within the `div.stats-section.stats-match.stats-match-economy` container inside `div.contentCol`. It is labeled "Beta" in the tab menu.

**High-level DOM tree:**

```
div.contentCol
  div.stats-section.stats-match.stats-match-economy
    div.stats-match-menu.standard-box        -- tab nav (Overview/Performance/Economy/Heatmaps)
    div.section-spacer
    div.stats-match-maps                     -- map selector (BO3/BO5 map tabs)
    div.standard-headline                    -- "Round start equipment value"
    div.standard-box                         -- FusionCharts line chart
      worker-ignore.graph[data-fusionchart-config]
    div.section-spacer
    div.standard-headline                    -- "Round breakdown by round start equipment value"
    div.columns                              -- Two-column team economy stats
      div.col.standard-box.stats-rows        -- Team 1 buy type breakdown
      div.col.standard-box.stats-rows        -- Team 2 buy type breakdown
    div.section-spacer
    div.standard-headline                    -- "First half round history"
    table.standard-box.equipment-categories  -- First half equipment icons per round
    div.section-spacer
    div.standard-headline                    -- "Second half round history"
    table.standard-box.equipment-categories  -- Second half equipment icons per round
```

**Key observation:** All data is present in the static HTML. No JavaScript-loaded content is required for extraction. The page contains three distinct data representations:
1. A FusionCharts multi-series line chart (JSON config in `data-fusionchart-config` attribute)
2. Team buy type breakdown summary (HTML divs)
3. Per-round equipment category icon tables (HTML tables with SVG icons)

## 2. Data Source Analysis

### Primary source: FusionCharts JSON config (RECOMMENDED)

**Location:** `worker-ignore.graph[data-fusionchart-config]`

The FusionCharts configuration is embedded as a JSON string in the `data-fusionchart-config` attribute of a `<worker-ignore class="graph">` element. This is the richest single data source on the page.

**Evidence:** Found in all 12 samples, all eras (2023-2026). No JavaScript execution needed -- the JSON is directly in the HTML attribute.

**Data available in FusionCharts JSON:**
- Per-round equipment values for both teams (integer dollar amounts as strings)
- Team names (via `dataset[].seriesname`)
- Round win/loss indicator per round (via `anchorImageUrl` presence/absence)
- Side indicator per round (CT vs T, via `ctRoundWon.png` or `tRoundWon.png` anchor images)
- Buy type thresholds (via `trendlines`: Semi-eco $5000, Semi-buy $10000, Full buy $20000)
- Round count (via `categories[0].category[]` labels)

### Secondary source: Equipment category tables (SUPPLEMENTARY)

**Location:** `table.standard-box.equipment-categories` (two tables: first half, second half)

These HTML tables provide per-round buy type classification via SVG icon filenames. They encode:
- Equipment value (in `title` attribute: `"Equipment value: 4200"`)
- Buy type classification (via SVG filename: Pistol/ForcePistol/Forcebuy/RifleArmor)
- Side (CT/T prefix in SVG filename)
- Round outcome (Win/Loss suffix in SVG filename)
- Team identity (first `<td class="team">` cell with team logo `<img>`)
- Visual win/loss (`.lost` CSS class on the `<img>` element)

### Tertiary source: Team economy stats summary (SUPPLEMENTARY)

**Location:** `div.col.standard-box.stats-rows > div.stats-row.team-economy-stat`

Aggregate buy type breakdown per team. Less useful than the per-round data but provides:
- Round counts and win rates per buy type category
- Specific round numbers in the `title` attribute

## 3. Per-Round Equipment Values

### Extraction approach: Parse FusionCharts JSON

**Selector:** `worker-ignore.graph[data-fusionchart-config]` (exactly 1 per page)

```python
import json
from bs4 import BeautifulSoup

fc_el = soup.select_one('worker-ignore.graph[data-fusionchart-config]')
config = json.loads(fc_el['data-fusionchart-config'])
ds = config['dataSource']

# Round labels (1-indexed round numbers)
round_labels = [cat['label'] for cat in ds['categories'][0]['category']]

# Per-team per-round data
for dataset in ds['dataset']:
    team_name = dataset['seriesname']       # e.g., "Vitality"
    team_color = dataset['color']           # e.g., "#aeaeae" (team1) or "#525252" (team2)
    for i, point in enumerate(dataset['data']):
        round_num = int(round_labels[i])
        equip_value = int(point['value'])   # e.g., 4200
        anchor = point.get('anchorImageUrl', None)
        # anchor indicates round outcome:
        #   None / absent        -> round LOST
        #   "ctRoundWon.png"     -> round WON while on CT side
        #   "tRoundWon.png"      -> round WON while on T side
```

**Data types:**
- `value`: String representation of integer (e.g., `"4200"`). Parse with `int()`.
- `anchorImageUrl`: Optional. Present only on rounds won by this team.
- `anchorImageScale`: Always `15` when anchor present. Ignore.
- `anchorBgAlpha`: Always `100`. Ignore.

**Round outcome encoding:**
- `anchorImageUrl` **present** with `ctRoundWon.png` -> Team won this round while playing CT
- `anchorImageUrl` **present** with `tRoundWon.png` -> Team won this round while playing T
- `anchorImageUrl` **absent** -> Team LOST this round (no icon rendered on chart)

This means for each round, exactly one team has an anchor image (the winner), and the other has none (the loser). The image filename also tells you which side that team was playing.

### Cross-verification with equipment table

**Selector:** `table.standard-box.equipment-categories td.equipment-category-td`

Each `<td>` has:
- `title` attribute: `"Equipment value: NNNNN"` -- parse with regex `r'Equipment value: (\d+)'`
- Child `<img class="equipment-category">` with `src` attribute containing buy type SVG
- Child `<img>` may have additional class `.lost` indicating round loss

The equipment table values match the FusionCharts JSON values exactly (verified across all 12 samples).

**Extraction status: extract** -- Parse from FusionCharts JSON (primary). Equipment tables provide redundant data for cross-verification if needed.

## 4. Buy Type Classifications

### From FusionCharts trendlines (thresholds)

The chart JSON contains trendlines that define the buy type thresholds:

```json
"trendlines": [{
  "line": [
    {"startvalue": "5000", "displayValue": "Semi-eco", "color": "c07846"},
    {"startvalue": "10000", "displayValue": "Semi-buy", "color": "fab200"},
    {"startvalue": "20000", "displayValue": "Full buy", "color": "a2c734"}
  ]
}]
```

**HLTV buy type classification:**

| Buy Type | Equipment Value Range | Trendline Label |
|----------|----------------------|-----------------|
| Full eco | $0 - $4,999 | (below Semi-eco line) |
| Semi-eco | $5,000 - $9,999 | Semi-eco |
| Semi-buy | $10,000 - $19,999 | Semi-buy |
| Full buy | $20,000+ | Full buy |

These thresholds are consistent across all 12 samples and all eras.

### From equipment category SVG icons (per-round classification)

The equipment tables encode buy type via SVG icon filenames. There are **15 unique SVG files** used:

**CT-side icons:**

| SVG Filename | Buy Type | Outcome |
|-------------|----------|---------|
| `ctPistolWin.svg` | Pistol (eco) | Won |
| `ctPistolLoss.svg` | Pistol (eco) | Lost |
| `ctForcePistolWin.svg` | Force-pistol (semi-eco) | Won |
| `ctForcePistolLoss.svg` | Force-pistol (semi-eco) | Lost |
| `ctForcebuyWin.svg` | Force buy (semi-buy) | Won |
| `ctForcebuyLoss.svg` | Force buy (semi-buy) | Lost |
| `ctRifleArmorWin.svg` | Rifle+Armor (full buy) | Won |
| `ctRifleArmorLoss.svg` | Rifle+Armor (full buy) | Lost |

**T-side icons:**

| SVG Filename | Buy Type | Outcome |
|-------------|----------|---------|
| `tPistolWin.svg` | Pistol (eco) | Won |
| `tPistolLoss.svg` | Pistol (eco) | Lost |
| `tForcebuyWin.svg` | Force buy (semi-buy) | Won |
| `tForcebuyLoss.svg` | Force buy (semi-buy) | Lost |
| `tForcePistolLoss.svg` | Force-pistol (semi-eco) | Lost |
| `tRifleArmorWin.svg` | Rifle+Armor (full buy) | Won |
| `tRifleArmorLoss.svg` | Rifle+Armor (full buy) | Lost |

**Note:** T-side has no `tForcePistolWin.svg` observed in the 12 samples. It may exist but was not encountered. T-side force-pistol rounds that were won may be classified differently.

**SVG filename parsing pattern:**
```
/img/static/equipmentcategories/{side}{buyType}{outcome}.svg
```
Where:
- `side` = `ct` | `t`
- `buyType` = `Pistol` | `ForcePistol` | `Forcebuy` | `RifleArmor`
- `outcome` = `Win` | `Loss`

**Mapping SVG buy types to HLTV thresholds:**

| SVG Buy Type | HLTV Category | Value Range |
|-------------|---------------|-------------|
| Pistol | Full eco | $0 - $4,999 |
| ForcePistol | Semi-eco | $5,000 - $9,999 |
| Forcebuy | Semi-buy | $10,000 - $19,999 |
| RifleArmor | Full buy | $20,000+ |

### From team economy stats (aggregate per team)

**Selector:** `div.stats-row.team-economy-stat`

Each stat row contains:
```html
<div class="stats-row team-economy-stat" title="Rounds: 4,13,21">
  <span><span>Total full eco rounds [0-5k] </span></span>
  <span title="Played">3<span title="Won"> (1)</span></span>
</div>
```

**Parsing:**
- Label: `div > span > span` text (e.g., "Total full eco rounds [0-5k]")
- Count played: `div > span[title="Played"]` direct text (e.g., "3")
- Count won: `div > span[title="Played"] > span[title="Won"]` text (e.g., "(1)")
- Round numbers: `div[@title]` attribute (e.g., "Rounds: 4,13,21")

**Four categories per team (always in this order):**
1. Total full eco rounds [0-5k]
2. Total semi-eco rounds [5-10k]
3. Total semi-buy rounds [10-20k]
4. Total full buy rounds [20k+]

**Two containers** (one per team) in `div.columns > div.col.standard-box.stats-rows`:
- Container 0: First team (team1 from URL/page position)
- Container 1: Second team

Team identity is in the first `div.stats-row` child (non-economy-stat), which contains:
- `span.label-and-text > img.label.flag` -- team region flag
- Text content -- team name
- `img.team-logo` -- team logo

**Extraction status: extract** -- Buy type can be derived from equipment values alone using the thresholds. The SVG icons and aggregate stats provide redundant confirmation.

## 5. Round Outcomes

Round win/loss is embedded in the FusionCharts data via the `anchorImageUrl` field:

- **Winner:** Has `anchorImageUrl` = `https://www.hltv.org/img/static/economy/ctRoundWon.png` or `tRoundWon.png`
- **Loser:** No `anchorImageUrl` field (or field absent)

In the equipment tables, round outcome is encoded via:
- SVG filename suffix: `Win` or `Loss`
- CSS class on `<img>`: `.lost` class present = round lost, absent = round won

**Note:** Round outcomes on the economy page are identical to those on the map stats/performance pages (round history section). If economy parsing is implemented, round outcomes can be cross-verified. However, the economy page does NOT show the specific outcome type (bomb planted/defused, elimination, time run out) -- only win/loss.

**Extraction status: extract** -- Available from FusionCharts JSON anchor images. Redundant with map stats page round history (which has more detail).

## 6. Side/Team Attribution

### Team identification

**In FusionCharts JSON:**
- `dataset[0].seriesname` = team1 name (always color `#aeaeae`, solid line `dashed: 0`)
- `dataset[1].seriesname` = team2 name (always color `#525252`, dashed line `dashed: 1`)

**In equipment tables:**
- Row 0: team1 (first `<td class="team">` contains `<img>` with team logo and name in `alt`/`title`)
- Row 1: team2

**Team ordering is consistent** between FusionCharts datasets and table rows across all 12 samples.

### Side determination (CT/T per half)

The side each team plays in each half is determined from the per-round anchor images or SVG filenames:

**From FusionCharts:**
- Rounds 1-12 (first half): If team1 wins with `ctRoundWon.png`, team1 started CT
- Rounds 13-24 (second half): Teams switch sides

**From equipment tables:**
- Table 0 (first half) SVGs: prefix `ct` or `t` indicates which side that team is playing
- Table 1 (second half) SVGs: sides are swapped

**Determining starting side:** Look at the first round's SVG prefix for team1:
- If first-half table row0 cell1 SVG starts with `ct` -> team1 started CT-side
- If first-half table row0 cell1 SVG starts with `t` -> team1 started T-side

**Verified across all samples:** The SVG prefix and FusionCharts anchor image consistently indicate the side. In MR12 format: rounds 1-12 are first half, rounds 13-24 are second half.

**Extraction status: extract** -- Side can be derived from SVG filenames or anchor image URLs.

## 7. Overtime Handling

### Critical finding: Economy page MAY omit OT rounds

**MR15 era (2023, economy-162345, score 16-14):**
- FusionCharts shows **30 round labels** (all rounds including OT)
- Equipment tables: Table 0 has **15 rounds per row**, Table 1 has **15 rounds per row** (15+15 = 30)
- Headline structure: "First half round history" + "Second half round history" (no separate OT section)
- OT rounds (25-30) are appended to the second half table
- Team economy stats reference rounds up to 30
- **Conclusion: Full OT economy data present**

**MR12 era (2025, economy-206389, score 19-17 = 36 rounds):**
- FusionCharts shows **24 round labels** (regulation only, rounds 1-24)
- Equipment tables: Table 0 has **12 rounds per row**, Table 1 has **12 rounds per row** (12+12 = 24)
- Headline structure: Same two headlines, no OT section
- Team economy stats only reference rounds up to 24
- OT rounds (25-36) are **completely absent**
- **Conclusion: OT economy data MISSING for MR12 matches**

**Implication for parser:** When the score indicates OT occurred (sum > 24 for MR12, sum > 30 for MR15), the parser should:
1. Check whether the FusionCharts data actually contains all expected rounds
2. If round count matches regulation only, mark OT economy data as unavailable
3. Still extract the regulation round economy data

**Round count validation formula:**
```python
chart_rounds = len(config['dataSource']['categories'][0]['category'])
# Regulation is 24 for MR12, 30 for MR15
# If chart_rounds < total_rounds, OT economy data is missing
```

**Extraction status: extract (regulation) / infeasible (OT for MR12 matches)** -- OT economy data is not available on the static page for MR12 matches. No known way to obtain it.

## 8. Historical Availability

### Economy data exists for ALL sampled eras

| Era | Sample | Economy Data? | Structure Identical? |
|-----|--------|---------------|---------------------|
| 2023 (Sep) | economy-162345 | Yes - full data | MR15 format (15 rounds/half) |
| 2023 (Oct) | economy-164779 | Yes - full data | MR15 format (12+9 rounds) |
| 2024 (Apr) | economy-173424 | Yes - full data | MR12 format |
| 2024 (Jul) | economy-179210 | Yes - full data | MR12 format |
| 2024 (Nov) | economy-188093 | Yes - full data | MR12 format |
| 2025 (Aug) | economy-206389 | Yes - regulation data | MR12 format (OT rounds missing) |
| 2026 (Feb) | economy-219128 | Yes - full data | MR12 format |

**Key observations:**
- Economy data is available for matches as far back as September 2023 (earliest CS2 samples)
- The DOM structure is identical across all eras
- FusionCharts JSON config format is identical across all eras
- SVG icon set is identical across all eras
- The "Beta" label on the economy tab is present across all eras
- The **only** structural difference is MR15 vs MR12 round counts per half

**The "Economy data availability for historical matches" concern from STATE.md is now RESOLVED:** Economy data exists and is parseable for early CS2 matches.

## 9. Annotated HTML/JSON Snippets

### 9.1 FusionCharts JSON (complete structure from Vitality vs G2, 2026)

```json
{
  "type": "msline",
  "renderAt": "uniqueChartId2015178223",
  "dataSource": {
    "chart": {
      "yAxisMaxValue": "40000",
      "yAxisMinValue": "0",
      "drawAnchors": 1,
      "showYAxisValues": "1",
      "numDivLines": 7,
      "type": "msline",
      "theme": "fint",
      "animation": "0"
      // ... other chart config (visual only, not data)
    },
    "categories": [{
      "category": [
        {"label": "1"},   // Round number as string
        {"label": "2"},
        // ... one entry per round
        {"label": "24"}
      ]
    }],
    "dataset": [
      {
        "seriesname": "Vitality",      // Team 1 name
        "color": "#aeaeae",            // Always #aeaeae for team 1
        "dashed": 0,                   // Solid line for team 1
        "data": [
          {
            "value": "4200",           // Equipment value in dollars
            "anchorImageUrl": "https://www.hltv.org/img/static/economy/ctRoundWon.png",
            // ^^ Present = WON this round. "ct" = playing CT side. "t" = playing T side.
            "anchorImageScale": 15,    // Always 15, ignore
            "anchorBgAlpha": 100       // Always 100, ignore
          },
          {
            "value": "22300",
            "anchorBgAlpha": 100
            // No anchorImageUrl = LOST this round
          }
          // ... one entry per round
        ]
      },
      {
        "seriesname": "G2",            // Team 2 name
        "color": "#525252",            // Always #525252 for team 2
        "dashed": 1,                   // Dashed line for team 2
        "data": [ /* same structure */ ]
      }
    ],
    "trendlines": [{
      "line": [
        {"startvalue": "5000", "displayValue": "Semi-eco", "color": "c07846"},
        {"startvalue": "10000", "displayValue": "Semi-buy", "color": "fab200"},
        {"startvalue": "20000", "displayValue": "Full buy", "color": "a2c734"}
      ]
    }]
  },
  "heightOverride": false,
  "width": "100%",
  "dataFormat": "json",
  "containerBackgroundOpacity": "0"
}
```

### 9.2 Equipment category table (first half, Vitality vs G2)

```html
<div class="standard-headline">First half round history</div>
<table class="standard-box equipment-categories">
<tbody>
  <tr class="team-categories">
    <!-- Team cell -->
    <td class="team">
      <img alt="Vitality" class="team-logo day-only" title="Vitality"
           src="https://img-cdn.hltv.org/teamlogo/..."/>
      <img alt="Vitality" class="team-logo night-only" title="Vitality"
           src="https://img-cdn.hltv.org/teamlogo/..."/>
    </td>
    <!-- Round 1: CT pistol, won -->
    <td class="equipment-category-td" title="Equipment value: 4200">
      <img class="equipment-category" src="/img/static/equipmentcategories/ctPistolWin.svg"/>
    </td>
    <!-- Round 2: CT rifle+armor, lost -->
    <td class="equipment-category-td" title="Equipment value: 22300">
      <img class="equipment-category lost" src="/img/static/equipmentcategories/ctRifleArmorLoss.svg"/>
    </td>
    <!-- Round 3: CT force-pistol (semi-eco), lost -->
    <td class="equipment-category-td" title="Equipment value: 9100">
      <img class="equipment-category lost" src="/img/static/equipmentcategories/ctForcePistolLoss.svg"/>
    </td>
    <!-- ... remaining rounds ... -->
  </tr>
  <tr class="team-categories">
    <td class="team">
      <img alt="G2" class="team-logo" title="G2" src="..."/>
    </td>
    <!-- Round 1: T pistol, lost -->
    <td class="equipment-category-td" title="Equipment value: 4200">
      <img class="equipment-category lost" src="/img/static/equipmentcategories/tPistolLoss.svg"/>
    </td>
    <!-- ... remaining rounds ... -->
  </tr>
</tbody>
</table>
```

### 9.3 Team economy stats summary

```html
<div class="standard-headline">Round breakdown by round start equipment value</div>
<div class="columns">
  <div class="col standard-box stats-rows">
    <!-- Team header row (not .team-economy-stat) -->
    <div class="stats-row">
      <span class="label-and-text">
        <img alt="Europe" class="label flag" src="/img/static/flags/30x20/EU.gif"/>
        Vitality
      </span>
      <img alt="Vitality" class="team-logo day-only" title="Vitality" src="..."/>
    </div>
    <!-- Buy type breakdown rows -->
    <div class="stats-row team-economy-stat" title="Rounds: 4,13,21">
      <span><span>Total full eco rounds [0-5k] </span></span>
      <span title="Played">3<span title="Won"> (1)</span></span>
    </div>
    <div class="stats-row team-economy-stat" title="Rounds: 3">
      <span><span>Total semi-eco rounds [5-10k] </span></span>
      <span title="Played">1<span title="Won"> (0)</span></span>
    </div>
    <div class="stats-row team-economy-stat" title="Rounds: 8,14,15,16,20,23">
      <span><span>Total semi-buy rounds [10-20k] </span></span>
      <span title="Played">6<span title="Won"> (3)</span></span>
    </div>
    <div class="stats-row team-economy-stat" title="Rounds: 2,5,6,7,9,10,11,12,17,18,19,22,24">
      <span><span>Total full buy rounds [20k+] </span></span>
      <span title="Played">13<span title="Won"> (8)</span></span>
    </div>
  </div>
  <div class="col standard-box stats-rows">
    <!-- Team 2 (same structure) -->
  </div>
</div>
```

### 9.4 Complete round data for one round (Round 1, Vitality vs G2)

**From FusionCharts JSON:**
```
Team 1 (Vitality): value=4200, anchorImageUrl=ctRoundWon.png
  -> Equipment: $4,200 | Side: CT | Outcome: WON | Buy type: Full eco ($0-$5k)

Team 2 (G2): value=4200, anchorBgAlpha=100 (no anchor)
  -> Equipment: $4,200 | Side: T | Outcome: LOST | Buy type: Full eco ($0-$5k)
```

**From equipment table:**
```
Team 1 (Vitality): title="Equipment value: 4200", img.src="ctPistolWin.svg"
  -> Equipment: $4,200 | Side: CT | Type: Pistol | Outcome: Win

Team 2 (G2): title="Equipment value: 4200", img.src="tPistolLoss.svg", img.class="lost"
  -> Equipment: $4,200 | Side: T | Type: Pistol | Outcome: Loss
```

Both sources are consistent. The SVG provides a more granular buy type label (Pistol vs ForcePistol vs Forcebuy vs RifleArmor) compared to the threshold-based classification.

## 10. Extraction Feasibility Assessment

### Verdict: FULLY EXTRACTABLE from saved HTML

All economy data is embedded in the static HTML page. No JavaScript execution or live browser interaction is needed.

**Recommended extraction strategy for Phase 7:**

1. **Parse FusionCharts JSON** from `worker-ignore.graph[data-fusionchart-config]`
   - This single JSON blob contains: team names, per-round equipment values, round outcomes, and side information
   - Parse with `json.loads(element['data-fusionchart-config'])`
   - Derive buy type from equipment value using the trendline thresholds ($5K/$10K/$20K)

2. **Parse equipment tables** for supplementary buy type classification
   - SVG filenames provide a more granular classification (Pistol vs ForcePistol vs Forcebuy vs RifleArmor)
   - This classification is redundant with the threshold-based approach but provides HLTV's own categorization
   - Parse from `table.standard-box.equipment-categories td.equipment-category-td`

3. **Parse team economy stats** for aggregate validation
   - Cross-verify per-round data against the aggregate stats
   - Parse from `div.stats-row.team-economy-stat`

**What to extract (per round, per team):**

| Field | Source | Selector/Path | Status |
|-------|--------|---------------|--------|
| Round number | FusionCharts | `categories[0].category[i].label` | **extract** |
| Equipment value | FusionCharts | `dataset[t].data[i].value` | **extract** |
| Round outcome | FusionCharts | `dataset[t].data[i].anchorImageUrl` presence | **extract** |
| Side (CT/T) | FusionCharts | `anchorImageUrl` filename prefix | **extract** |
| Buy type (threshold) | Derived | From equipment value + trendline thresholds | **extract** |
| Buy type (granular) | Equipment table | SVG filename parsing | **extract** |
| Team name | FusionCharts | `dataset[t].seriesname` | **extract** |
| Team logo | Equipment table | `td.team > img[alt]` | **skip** |
| Region flag | Stats rows | `img.label.flag[alt]` | **skip** |
| Chart visual config | FusionCharts | `chart.*` | **skip** |

**What to skip:**
- Team logos and flags (already available from match overview page)
- Chart rendering configuration (visual-only settings)
- FusionCharts `renderAt` ID (random, meaningless)
- Chart `heightOverride`, `width`, `containerBackgroundOpacity` (visual settings)

**What is infeasible:**
- OT round economy data for MR12 matches -- not present on the page at all
- Individual player equipment breakdowns (not available -- only team totals)
- Round-end money (only round-start equipment value is shown)
- Loss bonus tracking (not visible)

## Appendix A: Equipment Table Cell Count by Sample

Demonstrates that table cell counts equal the round count for each half:

| Sample | Score | Total Rounds | Table 0 (1st Half) | Table 1 (2nd Half) | Chart Labels |
|--------|-------|-------------|--------------------|--------------------|-------------|
| economy-219128 | 13-11 | 24 | 12+1 | 12+1 | 24 |
| economy-219151 | 8-13 | 21 | 12+1 | 9+1 | 21 |
| economy-164779 | 8-13 | 21 | 12+1 | 9+1 | 21 |
| economy-174112 | 13-8 | 21 | 12+1 | 9+1 | 21 |
| economy-174116 | 6-13 | 19 | 12+1 | 7+1 | 19 |
| economy-188093 | 4-13 | 17 | 12+1 | 5+1 | 17 |
| economy-206393 | 13-4 | 17 | 12+1 | 5+1 | 17 |
| economy-162345 | 16-14 | 30 (OT) | 15+1 | 15+1 | 30 |
| economy-206389 | 19-17 | 36 (OT) | 12+1 | 12+1 | **24** (missing OT) |

Note: "+1" represents the team logo cell in each row.

## Appendix B: Anchor Image URL Reference

| Anchor Image | Meaning |
|-------------|---------|
| `https://www.hltv.org/img/static/economy/ctRoundWon.png` | This team WON the round while playing CT |
| `https://www.hltv.org/img/static/economy/tRoundWon.png` | This team WON the round while playing T |
| (absent) | This team LOST the round |

## Appendix C: FusionCharts Config Key Reference

Top-level config keys (all samples identical structure):

| Key | Value | Notes |
|-----|-------|-------|
| `type` | `"msline"` | Multi-series line chart |
| `renderAt` | `"uniqueChartId..."` | Random ID, ignore |
| `dataSource` | `{chart, categories, dataset, trendlines}` | **All data here** |
| `heightOverride` | `false` | Visual config, ignore |
| `width` | `"100%"` | Visual config, ignore |
| `dataFormat` | `"json"` | Always JSON |
| `containerBackgroundOpacity` | `"0"` | Visual config, ignore |
