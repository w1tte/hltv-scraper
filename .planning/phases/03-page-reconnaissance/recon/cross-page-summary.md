# Cross-Page Data Overlap Map

**Synthesized from:** results-listing.md, match-overview.md, map-stats.md, map-performance.md, map-economy.md
**Date:** 2026-02-15
**Purpose:** Single reference for Phase 4-7 parser developers showing which page to extract each field from

---

## Section 1: Field Inventory (Master Table)

### Match-Level Fields

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| match_id | x | x (from URL) | | | | **Results Listing** | Discovered first during crawl; drives all subsequent fetches |
| match_date | x | x | x | | | **Match Overview** | Unix ms with `data-unix` attr; results listing timestamp is completion time |
| team1_name | x | x | x | x | x | **Match Overview** | Authoritative; `.team1-gradient .teamName` |
| team2_name | x | x | x | x | x | **Match Overview** | Authoritative; `.team2-gradient .teamName` |
| team1_id | | x | x | | | **Match Overview** | Extracted from `/team/{id}/` href |
| team2_id | | x | x | | | **Match Overview** | Extracted from `/team/{id}/` href |
| team1_score (series) | x | x | | | | **Match Overview** | `.team1-gradient .won`/`.lost`; results listing also reliable |
| team2_score (series) | x | x | | | | **Match Overview** | Same; missing on forfeits |
| winner | x | x | | | | **Match Overview** | `.won` class on team gradient |
| match_format | x (partial) | x | | | | **Match Overview** | "Best of N" from `.padding.preformatted-text`; results listing has `bo3`/`bo5`/map-name |
| lan_or_online | | x | | | | **Match Overview** | Exclusive; parsed from format text |
| event_name | x | x | x | x | | **Match Overview** | Most complete; includes event link |
| event_id | | x | x | | | **Match Overview** | Parsed from `/events/{id}/` href |
| star_rating | x | | | | | **Results Listing** | Exclusive to results listing |
| match_context | | x | | | | **Match Overview** | Exclusive; stage/round info |
| team1_ranking | | x | | | | **Match Overview** | Exclusive; `.lineups .teamRanking` |
| team2_ranking | | x | | | | **Match Overview** | Exclusive; `.lineups .teamRanking` |

### Roster/Player-Level Fields

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| player_id | | x | x | x | | **Match Overview** | `data-player-id` attr; cleanest extraction |
| player_name | | x | x | x | | **Match Overview** | `.text-ellipsis` inside `[data-player-id]` |
| player_nationality | | x | x | x | | **Match Overview** | `img.flag[title]` on lineup rows |
| player_full_name | | x | | x | | **Match Overview** | `.player-image img[alt]` format: "First 'Nick' Last" |

### Veto Fields

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| veto_sequence | | x | | | | **Match Overview** | Exclusive; second `.veto-box` |
| map_picks | | x (from veto) | | | | **Match Overview** | Derived from veto text "picked" lines |

### Per-Map Fields

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| map_name | | x | x | x (BO3/BO5 tabs) | x (BO3/BO5 tabs) | **Match Overview** | `.mapholder .mapname`; needed to link maps to mapstatsids |
| mapstatsid | | x | | | | **Match Overview** | Exclusive; parsed from `.results-stats` href |
| map_score (per team) | | x | x | x (BO3/BO5 tabs) | | **Map Stats** | More precise (`.team-left .bold` / `.team-right .bold`) |
| map_winner | | x | x | | | **Map Stats** | `.bold.won` class |
| half_scores | | x | x | | | **Map Stats** | Richer data with ct-color/t-color spans |
| team_starting_side | | x (partial) | x | x (from anchor) | x (from anchor/SVG) | **Map Stats** | First half span class indicates starting side |

### Per-Player Scoreboard Fields (per map)

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| kills | | | x | | | **Map Stats** | `.st-kills.traditional-data` -- count value |
| headshots | | | x | | | **Map Stats** | Parsed from "14(9)" format |
| assists | | | x | | | **Map Stats** | `.st-assists` |
| flash_assists | | | x | | | **Map Stats** | Parsed from "2(0)" format |
| deaths | | | x | | | **Map Stats** | `.st-deaths.traditional-data` |
| traded_deaths | | | x | | | **Map Stats** | Parsed from "15(2)" format |
| adr | | | x | x | | **Map Stats** | Scoreboard has per-player ADR as count-based value |
| kast | | | x | x | | **Map Stats** | Scoreboard has "66.7%" string; performance has same |
| rating | | | x | x | | **Map Stats** | Scoreboard has direct float; performance has FusionChart |
| round_swing | | | x (3.0 only) | x (3.0 only) | | **Map Stats** | `.st-roundSwing` on scoreboard |
| opening_kills_deaths | | | x | | | **Map Stats** | Exclusive; `.st-opkd` "2 : 5" format |
| multi_kills | | | x | | | **Map Stats** | Exclusive; `.st-mks` count |
| clutch_wins | | | x | | | **Map Stats** | Exclusive; `.st-clutches` count |

### Per-Player Rate/Rating Fields (per map)

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| kpr | | | | x | | **Performance** | Exclusive; FusionChart `displayValue` |
| dpr | | | | x | | **Performance** | Exclusive; FusionChart `displayValue` |
| mk_rating (3.0 only) | | | | x | | **Performance** | Exclusive; FusionChart `displayValue` |
| impact (2.0 only) | | | | x | | **Performance** | Exclusive; FusionChart `displayValue` |

### Team-Level Aggregate Fields (per map)

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| team_rating | | | x | | | **Map Stats** | Exclusive; `.match-info-row` row 2 |
| first_kills_total | | | x | | | **Map Stats** | Exclusive; `.match-info-row` row 3 |
| clutches_won_total | | | x | | | **Map Stats** | Exclusive; `.match-info-row` row 4 |
| team_kills | | | | x | | **Performance** | `.overview-table` row "Kills" |
| team_deaths | | | | x | | **Performance** | `.overview-table` row "Deaths" |
| team_assists | | | | x | | **Performance** | `.overview-table` row "Assists" |

### Kill Matrix Fields (per map)

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| kill_matrix_all | | | | x | | **Performance** | Exclusive; `#ALL-content` table |
| kill_matrix_first_kills | | | | x | | **Performance** | Exclusive; `#FIRST_KILL-content` table |
| kill_matrix_awp | | | | x | | **Performance** | Exclusive; `#AWP-content` table |

### Round History Fields (per map)

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| round_outcome_type | | | x | | | **Map Stats** | Exclusive detailed types: ct_win, t_win, bomb_exploded, bomb_defused, stopwatch |
| round_outcome_simple | | | x | | x | **Map Stats** | Win/loss only; economy has anchor images |
| round_score_progression | | | x | | | **Map Stats** | `title` attr on winning outcome images |

### Economy Fields (per map, per round)

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| equipment_value | | | | | x | **Economy** | Exclusive; FusionCharts JSON `dataset[t].data[i].value` |
| buy_type | | | | | x | **Economy** | Exclusive; derived from value thresholds or SVG filenames |
| buy_type_granular | | | | | x | **Economy** | Exclusive; SVG filenames (Pistol/ForcePistol/Forcebuy/RifleArmor) |
| round_side (CT/T) | | | x (from history) | | x | **Economy** | Anchor image URL prefix or SVG prefix |
| buy_type_aggregate | | | | | x | **Economy** | Exclusive; `.team-economy-stat` summary rows |

### Eco-Adjusted Fields (per map)

| Field | Results Listing | Match Overview | Map Stats | Performance | Economy | Canonical Source | Reason |
|-------|:-:|:-:|:-:|:-:|:-:|---|---|
| eco_kills | | | x (hidden) | | | **Map Stats** | `.eco-adjusted-data.hidden` columns; Rating 3.0 only |
| eco_deaths | | | x (hidden) | | | **Map Stats** | Same; "null" on Rating 2.0 |
| eco_adr | | | x (hidden) | | | **Map Stats** | Same |
| eco_kast | | | x (hidden) | | | **Map Stats** | Same |

---

## Section 2: Overlapping Fields Detail

### Team Names (5 page types)

| Page Type | Selector | Format | Notes |
|-----------|----------|--------|-------|
| Results Listing | `.team1 .team` / `.team2 .team` | Plain text | Short form |
| Match Overview | `.team1-gradient .teamName` / `.team2-gradient .teamName` | Plain text | Authoritative |
| Map Stats | `.team-left a` / `.team-right a` | Text content of anchor | Uses `/stats/teams/` href |
| Performance | `.players-team-header .label-and-text` | Text after flag image | No team ID link |
| Economy | FusionCharts `dataset[t].seriesname` | JSON string | Also in equipment table `img[alt]` |

**Recommendation:** Extract from **Match Overview** (`.team1-gradient .teamName`). This is the authoritative source with team ID links available in the same container. All other pages should cross-reference against the overview team names.

### Player Names and IDs (3 page types)

| Page Type | Name Selector | ID Source | ID Pattern |
|-----------|---------------|-----------|------------|
| Match Overview | `.players [data-player-id] .text-ellipsis` | `data-player-id` attribute | Direct integer |
| Map Stats | `td.st-player a.text-ellipsis` | `a[href]` | `/stats/players/{id}/{slug}` |
| Performance | `.headline .player-nick` | `.headline a[href]` | `/player/{id}/{slug}` |

**Differences:**
- Match overview: `data-player-id` attribute (cleanest), player href uses `/player/{id}/`
- Map stats: Player href uses `/stats/players/{id}/` (different path prefix)
- Performance: Player cards use `/player/{id}/`; kill matrix uses `/stats/players/{id}/`

**Recommendation:** Extract roster from **Match Overview** (`data-player-id` attribute). Use map stats and performance player IDs to cross-reference/link per-map data back to the roster.

### Map Score (3 page types)

| Page Type | Selector | Format | Notes |
|-----------|----------|--------|-------|
| Match Overview | `.mapholder .results-team-score` | Integer text | Left = team1, right = team2; "-" for unplayed |
| Map Stats | `.team-left .bold` / `.team-right .bold` | Integer text | Has `.won`/`.lost` class |
| Performance | `.stats-match-map .stats-match-map-result-score` | "13 - 11" string | Only on BO3/BO5 map tabs |

**Recommendation:** Extract from **Map Stats** (`.team-left .bold` / `.team-right .bold`). Includes `.won`/`.lost` class for direct winner identification. Match overview is the fallback (and the source for unplayed/forfeit maps).

### Rating Value (2 page types)

| Page Type | Selector | Format | Notes |
|-----------|----------|--------|-------|
| Map Stats | `td.st-rating` | Float text (e.g., "1.14") | In scoreboard table; has `.ratingPositive`/`.ratingNegative` subclass |
| Performance | FusionChart JSON `data[label="Rating 3.0"].displayValue` | Float string | Same value, different extraction method |

**Recommendation:** Extract from **Map Stats** (`td.st-rating`). The scoreboard already has all other per-player stats; extracting rating from the same table is simpler. Performance page rating is redundant.

### ADR (2 page types)

| Page Type | Selector | Format | Notes |
|-----------|----------|--------|-------|
| Map Stats | `td.st-adr.traditional-data` | Float text (e.g., "69.2") | Per-player in scoreboard |
| Performance | FusionChart JSON `data[label="ADR"].displayValue` | Float string (e.g., "102.6") | Per-player in chart bars |

**Recommendation:** Extract from **Map Stats** (`td.st-adr`). Same reasoning as rating -- keep scoreboard extraction unified.

### KAST (2 page types)

| Page Type | Selector | Format | Notes |
|-----------|----------|--------|-------|
| Map Stats | `td.st-kast.traditional-data` | Percentage string (e.g., "66.7%") | Per-player in scoreboard |
| Performance | FusionChart JSON `data[label="KAST"].displayValue` | Percentage string (e.g., "66.7%") | Per-player in chart bars |

**Recommendation:** Extract from **Map Stats**. Same reasoning.

### Round Swing (2 page types, Rating 3.0 only)

| Page Type | Selector | Format | Notes |
|-----------|----------|--------|-------|
| Map Stats | `td.st-roundSwing` | Signed percentage (e.g., "+2.90%") | Absent on Rating 2.0 pages |
| Performance | FusionChart JSON `data[label="Swing"].displayValue` | Signed percentage (e.g., "+12.23%") | Absent on Rating 2.0 pages |

**Recommendation:** Extract from **Map Stats** (`td.st-roundSwing`). Consistent with other scoreboard fields.

### Round Outcomes (2 page types)

| Page Type | Selector | Format | Notes |
|-----------|----------|--------|-------|
| Map Stats | `img.round-history-outcome[src]` | SVG filename encodes type | 6 outcome types: ct_win, t_win, bomb_exploded, bomb_defused, stopwatch, emptyHistory |
| Economy | FusionCharts `anchorImageUrl` | PNG filename | Only win/loss (ctRoundWon/tRoundWon or absent) |

**Recommendation:** Extract from **Map Stats** (`img.round-history-outcome`). Provides granular outcome type (bomb planted, defused, elimination, timeout). Economy page only shows win/loss.

### Starting Side (3 page types)

| Page Type | Selector | Format | Notes |
|-----------|----------|--------|-------|
| Match Overview | `.results-center-half-score span.ct`/`.t` | CT/T class on half-score spans | First half spans indicate starting side |
| Map Stats | `.match-info-row .right span.ct-color`/`.t-color` | CT/T color class | First span in first () group |
| Economy | FusionCharts `anchorImageUrl` / SVG prefix | ct/t prefix | Determined from first round's anchor/SVG |

**Recommendation:** Extract from **Map Stats** (`.match-info-row .right` breakdown). The ct-color/t-color spans are explicit and verified across all samples.

---

## Section 3: Exclusive Fields

### Results Listing Exclusives

| Field | Critical? | Notes |
|-------|-----------|-------|
| star_rating | Optional | Match importance indicator (0-5 stars); not essential for stats |
| match_timestamp (completion) | Optional | `data-zonedgrouping-entry-unix` is match completion time; match overview `data-unix` is match start |

### Match Overview Exclusives

| Field | Critical? | Notes |
|-------|-----------|-------|
| team1_id, team2_id | **Critical** | Only available from team gradient hrefs |
| mapstatsid | **Critical** | Only available from `.results-stats` hrefs; drives all map sub-page fetches |
| veto_sequence | Important | Only in second `.veto-box` |
| team_rankings | Important | `.lineups .teamRanking`; may be missing for unranked teams |
| lan_or_online | Important | From format text |
| match_context | Optional | Stage/round info |
| player_full_name | Optional | "First 'Nick' Last" from photo alt text |
| forfeit_note | Important | Lines starting with `**` in format text |

### Map Stats Exclusives

| Field | Critical? | Notes |
|-------|-----------|-------|
| opening_kills_deaths | **Critical** | `.st-opkd` -- Op.K-D per player |
| multi_kills | **Critical** | `.st-mks` -- MK count per player |
| clutch_wins | **Critical** | `.st-clutches` -- 1vsX count per player |
| round_outcome_type | **Critical** | Detailed outcome (bomb_exploded, defused, elimination, timeout) |
| round_score_progression | Important | Score at each round from `title` attr |
| team_rating_avg | Important | Team average rating from `.match-info-row` row 2 |
| first_kills_total | Important | Team total from `.match-info-row` row 3 |
| clutches_won_total | Important | Team total from `.match-info-row` row 4 |
| ct_side_stats | Optional | Hidden `.ctstats` tables |
| t_side_stats | Optional | Hidden `.tstats` tables |
| eco_adjusted_stats | Optional | Hidden `.eco-adjusted-data` columns |

### Performance Page Exclusives

| Field | Critical? | Notes |
|-------|-----------|-------|
| kpr | **Critical** | Kills per round -- rate metric not on scoreboard |
| dpr | **Critical** | Deaths per round -- rate metric not on scoreboard |
| mk_rating (3.0) | **Critical** | Multi-kill rating (split from Impact in 3.0) |
| impact (2.0) | **Critical** | Impact rating (combined metric in 2.0) |
| kill_matrix_all | Important | 5x5 head-to-head kills |
| kill_matrix_first_kills | Important | 5x5 first-kill matchups |
| kill_matrix_awp | Important | 5x5 AWP kill matchups |
| team_kills/deaths/assists | Optional | Aggregate per team (derivable from scoreboard) |

### Economy Page Exclusives

| Field | Critical? | Notes |
|-------|-----------|-------|
| equipment_value | **Critical** | Per-round start equipment in dollars |
| buy_type | **Critical** | Derived from equipment value thresholds |
| buy_type_granular | Important | HLTV's own classification via SVG filenames |
| buy_type_aggregate | Optional | Per-team buy type summary (derivable from per-round data) |

---

## Section 4: Data Flow Diagram

```
PHASE 4: Results Listing Parser
  /results?offset=N
  |
  | Extracts per match:
  |   match_id, match_url, team1_name, team2_name,
  |   team1_score, team2_score, winner, map_text (format/map),
  |   event_name, star_rating, match_timestamp
  |
  v
PHASE 5: Match Overview Parser
  /matches/{match_id}/{slug}
  |
  | Extracts per match:
  |   team1_id, team2_id, match_date, event_id,
  |   match_format (BO1/BO3/BO5), lan_or_online,
  |   veto_sequence (7 steps),
  |   player roster (10 players: id, name, nationality),
  |   team_rankings
  |
  | Extracts per map (from map holders):
  |   map_name, mapstatsid, map_score, half_scores,
  |   map_winner, played/unplayed/forfeit status
  |
  | FORFEIT CHECK: If map_name == "Default" or no mapstatsid
  |   -> Skip sub-page fetching for that map
  |
  v (per played map, using mapstatsid)
PHASE 6: Map Stats Parser
  /stats/matches/mapstatsid/{id}/{slug}
  |
  | Extracts per map:
  |   rating_version (2.0 or 3.0),
  |   half_breakdown (CT/T starting side),
  |   team_rating, first_kills, clutches_won,
  |   round_history (outcome type per round)
  |
  | Extracts per player (5 per team, 10 total):
  |   kills, headshots, assists, flash_assists,
  |   deaths, traded_deaths, adr, kast, rating,
  |   opening_kills_deaths, multi_kills, clutch_wins,
  |   round_swing (3.0 only)
  |
  v (same mapstatsid)
PHASE 7: Map Performance + Economy Parsers
  /stats/matches/performance/mapstatsid/{id}/{slug}
  |
  | Extracts per player:
  |   kpr, dpr, mk_rating (3.0) / impact (2.0)
  |
  | Extracts per map:
  |   kill_matrix (All / First kills / AWP kills)
  |
  /stats/matches/economy/mapstatsid/{id}/{slug}
  |
  | Extracts per round per team:
  |   equipment_value, buy_type, round_side,
  |   round_outcome (win/loss)
```

---

## Section 5: Extraction Order Recommendation

### Recommended Phase Execution Order

1. **Phase 4: Results Listing** -- Produces the master list of match IDs. All subsequent phases depend on this.

2. **Phase 5: Match Overview** -- Produces team IDs, event IDs, player rosters, mapstatsids, and veto data. The mapstatsids are required to fetch any map sub-page.

3. **Phase 6: Map Stats** -- The primary per-player scoreboard data. Must be parsed before performance/economy because:
   - It has the complete per-player stat set (kills, deaths, assists, ADR, rating, etc.)
   - It has the authoritative round history with detailed outcome types
   - It detects rating version (2.0 vs 3.0) needed by performance parser
   - It provides map scores and half breakdowns more reliably than match overview

4. **Phase 7: Performance + Economy** -- These are supplementary pages that add rate metrics (KPR, DPR), kill matrices, and economy data on top of the Phase 6 scoreboard.

### Duplicate Extraction Avoidance

| Field | Extract From | Skip On |
|-------|-------------|---------|
| team_name | Match Overview | Map Stats, Performance, Economy (use for validation only) |
| player_name, player_id | Match Overview (roster) | Map Stats, Performance (use IDs for cross-reference) |
| map_score | Map Stats | Match Overview (use as fallback for forfeit maps) |
| rating | Map Stats (scoreboard) | Performance (FusionChart -- redundant) |
| adr | Map Stats (scoreboard) | Performance (FusionChart -- redundant) |
| kast | Map Stats (scoreboard) | Performance (FusionChart -- redundant) |
| round_swing | Map Stats (scoreboard) | Performance (FusionChart -- redundant) |
| round_outcome | Map Stats (round history) | Economy (FusionChart anchors -- less detail) |
| half_scores | Map Stats (breakdown row) | Match Overview (use as fallback) |
| starting_side | Map Stats (ct-color/t-color spans) | Economy (anchor/SVG -- redundant) |

### Fields That MUST Come From Specific Pages

| Field | Unique Source | Why |
|-------|--------------|-----|
| mapstatsid | Match Overview | Only page with `/stats/matches/mapstatsid/` links |
| team_id | Match Overview | Only page with `/team/{id}/` links |
| event_id | Match Overview | Most reliable `/events/{id}/` link |
| veto_sequence | Match Overview | Only page with veto data |
| equipment_value | Economy | Only page with per-round dollar amounts |
| kill_matrix | Performance | Only page with head-to-head kill tables |
| kpr, dpr | Performance | Rate metrics not on any other page |
| mk_rating, impact | Performance | Version-specific ratings exclusive to FusionChart |
| round_outcome_type | Map Stats | Only page with detailed outcome (bomb/defuse/elim/timeout) |
| opening_kills_deaths | Map Stats | Exclusive to scoreboard `.st-opkd` column |
