# Match Overview Page Selector Map

**Page URL pattern:** `/matches/{match_id}/{slug}`
**Analyzed:** 2026-02-15
**Samples tested:** 9 match overview pages (see verification matrix below)
**Method:** Programmatic BeautifulSoup `.select()` verification against all samples

## Verification Matrix

| Match ID | Format | Edge Case | All Selectors Verified |
|----------|--------|-----------|----------------------|
| 2366498 | BO1 | Overtime (16-14 Nuke) | Yes |
| 2367432 | BO3 | Standard (2-0 sweep, unplayed map 3) | Yes |
| 2371321 | BO1 | Tier-3 online | Yes |
| 2371389 | BO3 | Standard (2-1 full series) | Yes |
| 2373741 | BO1 | Standard online | Yes |
| 2377467 | BO1 | National-team LAN event | Yes |
| 2380434 | BO1 | **Forfeit** (match deleted, no stats) | Yes |
| 2384993 | BO5 | **BO5 + overtime + partial forfeit** (map 3 = Default) | Yes |
| 2389951 | BO3 | **Tier-1 LAN** (Vitality vs G2, PGL Major) | Yes |

---

## Section 1: Match Metadata

### Selector Table

| Field | CSS Selector | Data Type | Required | Extract | Example Value | Notes |
|-------|-------------|-----------|----------|---------|---------------|-------|
| team1_name | `.team1-gradient .teamName` | string | always | **extract** | "Vitality" | Text content of element |
| team2_name | `.team2-gradient .teamName` | string | always | **extract** | "G2" | Text content of element |
| team1_id | `.team1-gradient a[href*='/team/']` | int | always | **extract** | 9565 | Parse from href `/team/{id}/{slug}` |
| team2_id | `.team2-gradient a[href*='/team/']` | int | always | **extract** | 5995 | Parse from href `/team/{id}/{slug}` |
| team1_score | `.team1-gradient .won` or `.team1-gradient .lost` | int | usually | **extract** | 2 | Text content; class indicates winner. Missing on forfeits. |
| team2_score | `.team2-gradient .won` or `.team2-gradient .lost` | int | usually | **extract** | 1 | Text content; class indicates winner. Missing on forfeits. |
| winner | `.team1-gradient .won` or `.team2-gradient .won` | enum | usually | **extract** | team1/team2/none | Whichever team's gradient has a `.won` child. Missing on forfeits. |
| match_date | `.timeAndEvent .date[data-unix]` | unix_ms | always | **extract** | 1771080000000 | `data-unix` attribute; divide by 1000 for epoch seconds |
| event_name | `.timeAndEvent .event a` | string | always | **extract** | "PGL Cluj-Napoca 2026" | Text content |
| event_id | `.timeAndEvent .event a[href*='/events/']` | int | always | **extract** | 8047 | Parse from href `/events/{id}/{slug}` |
| match_format | `.padding.preformatted-text` | enum | always | **extract** | "Best of 3" | First line of text; parse "Best of N" where N = 1, 3, or 5 |
| lan_or_online | `.padding.preformatted-text` | enum | always | **extract** | "LAN" | Parse "(LAN)" or "(Online)" from first line |
| match_context | `.padding.preformatted-text` | string | always | **extract** | "Swiss round 1" | Lines after "Best of N (LAN/Online)" -- stage/round info |
| match_status | `.countdown` | string | always | skip | "Match over" | Values: "Match over", "Match deleted" (forfeit). Not needed for scraping. |
| team1_ranking | `.lineups .lineup:first-child .teamRanking a` | string | sometimes | **extract** | "World rank: #1" | Text content; parse `#N` for rank number. Inside `.lineups`, NOT inside `.team{1,2}-gradient`. Missing for unranked teams (match 2366498: n00rg unranked). |
| team2_ranking | `.lineups .lineup:last-child .teamRanking a` | string | sometimes | **extract** | "World rank: #9" | Same as team1_ranking but for second lineup block |
| forfeit_note | `.padding.preformatted-text` | string | sometimes | **extract** | "adalYamigos forfeit the match..." | Lines starting with `**` in the preformatted-text. Present only on forfeit matches. |

### Parsing Notes

**Team ID extraction regex:** `/team/(\d+)/` applied to the `href` attribute.

**Event ID extraction regex:** `/events/(\d+)/` applied to the `href` attribute.

**Format parsing:** The `.padding.preformatted-text` element contains multi-line text:
```
Best of 3 (LAN)
* Swiss round 1
```
- Line 1: `Best of {N} ({LAN|Online})` -- regex: `Best of (\d+) \((LAN|Online)\)`
- Line 2+: Prefixed with `*` -- stage/context info
- Lines with `**`: Forfeit/walkover notes (only on forfeit matches)
- Lines with `***`: Additional context (e.g., team withdrawal)

**Winner detection:** Exactly one of `.team1-gradient .won` or `.team2-gradient .won` exists on normal matches. The `.lost` class appears on the losing team. On forfeit matches (2380434), NEITHER `.won` NOR `.lost` exists -- both score divs are absent entirely.

**Ranking location:** Rankings are inside `.lineups .box-headline .teamRanking a`, NOT inside `.team{1,2}-gradient`. The `.teamRanking a` selector on the page root returns both rankings in document order (team1 first, team2 second). One team may be "Unranked" (missing `.teamRanking a` element), as seen in match 2366498 (both teams unranked) and 2377467 (Tunisia unranked, only kONO has ranking).

### Annotated HTML: Team Container

```html
<!-- .team1-gradient contains team name, link, and score -->
<div class="team1-gradient">
  <a href="/team/9565/vitality">
    <div class="teamName">Vitality</div>
  </a>
  <!-- .won class = this team won the match -->
  <!-- .lost class = this team lost the match -->
  <!-- On forfeit matches, this div is ABSENT entirely -->
  <div class="won">2</div>
</div>

<div class="team2-gradient">
  <a href="/team/5995/g2">
    <div class="teamName">G2</div>
  </a>
  <div class="lost">1</div>
</div>
```

### Annotated HTML: Rankings (inside .lineups, not team-gradient)

```html
<div class="lineups" id="lineups">
  <span class="headline">Lineups</span>
  <div class="">
    <div class="lineup standard-box">
      <div class="box-headline flex-align-center">
        <div class="flex-align-center">
          <img class="logo" src="..." title="Vitality"/>
          <a class="text-ellipsis" href="/team/9565/vitality">Vitality</a>
        </div>
        <div class="teamRanking">
          <a class="a-reset" href="/ranking/teams/2026/february/9/9565">
            <span>World rank: </span>#1
          </a>
        </div>
      </div>
      <div class="players">
        <!-- player rows (see Section 4) -->
      </div>
    </div>
  </div>
</div>
```

---

## Section 2: Map Holders and Scores

### Selector Table

| Field | CSS Selector | Data Type | Required | Extract | Example Value | Notes |
|-------|-------------|-----------|----------|---------|---------------|-------|
| map_holders | `.mapholder` | container[] | always | **extract** | - | One per map in series. BO1=1, BO3=3, BO5=5. |
| map_name | `.mapholder .mapname` | string | always | **extract** | "Mirage" | Text content. "Default" = forfeit map. |
| map_played | `.mapholder .played` | boolean | always | **extract** | true | If `.played` div exists inside mapholder = played. If `.optional` exists = unplayed. |
| team1_map_score | `.mapholder .results-left .results-team-score` | int | played maps | **extract** | 13 | Text content. "-" for unplayed maps. team1 is ALWAYS left. |
| team2_map_score | `.mapholder .results-right .results-team-score` | int | played maps | **extract** | 11 | Text content. "-" for unplayed maps. team2 is ALWAYS right. |
| half_scores | `.mapholder .results-center-half-score` | structured | played maps | **extract** | "(7:5;6:6)" | Contains `<span>` children with ct/t classes. See parsing notes. |
| map_stats_link | `.mapholder a.results-stats[href]` | string | played, non-forfeit | **extract** | "/stats/matches/mapstatsid/219128/..." | Extract mapstatsid with regex. Absent for forfeit maps and unplayed maps. |
| mapstatsid | (parsed from map_stats_link) | int | played, non-forfeit | **extract** | 219128 | Regex: `/mapstatsid/(\d+)/` |
| map_winner | `.mapholder .results-left .won` or `.results-right .won` | enum | played maps | **extract** | left/right | `.won` class on the score div indicates winner |
| map_pick | (not in DOM) | - | - | skip | - | No pick indicator found in any sample. Map picks are only in veto text. |

### Team Left/Right Mapping

**Confirmed across all 9 samples:** Team 1 (`.team1-gradient`) is ALWAYS the left team (`.results-left`), and team 2 (`.team2-gradient`) is ALWAYS the right team (`.results-right`). This is consistent regardless of who picked the map or who won.

### Played vs. Unplayed Maps

Maps have two possible internal structures:

| State | Inner class | `.results` class | Score value | Stats link |
|-------|------------|-------------------|-------------|-----------|
| **Played** | `.played` | `results played` | Numeric (e.g., "13") | Present |
| **Unplayed** | `.optional` | `results optional` | "-" (dash) | Absent |
| **Forfeit** | `.played` | `results played` | Numeric ("0"/"1") | **Absent** |

Note: Forfeit maps (map name "Default") use the `.played` class but have NO stats link.

### Half-Score Structure

The `.results-center-half-score` element contains structured `<span>` elements with side indicators:

**Standard regulation (24 rounds):**
```html
<!-- Format: (CT1:T1;T2:CT2) where sides flip at halftime -->
<div class="results-center-half-score">
  <span> (</span>
  <span class="ct">7</span>    <!-- team1 first-half rounds (as CT) -->
  <span class="">:</span>
  <span class="t">5</span>     <!-- team2 first-half rounds (as T) -->
  <span>; </span>
  <span class="t">6</span>     <!-- team1 second-half rounds (as T) -->
  <span class="">:</span>
  <span class="ct">6</span>    <!-- team2 second-half rounds (as CT) -->
  <span></span>
  <span>)</span>
</div>
```

**With overtime (Mirage 19-17, match 2384993):**
```html
<div class="results-center-half-score">
  <!-- Regulation half -->
  <span> (</span>
  <span class="ct">3</span><span class="">:</span><span class="t">9</span>
  <span>; </span>
  <span class="t">9</span><span class="">:</span><span class="ct">3</span>
  <span></span><span>)</span>
  <!-- Overtime (no ct/t class -- sides not indicated) -->
  <span> (</span>
  <span>7</span><span class="">:</span><span>5</span>
  <span>)</span>
</div>
```

**Forfeit map (Default):**
```html
<div class="results-center-half-score"></div>
<!-- Empty element -- no half scores for forfeit maps -->
```

### Half-Score Parsing Strategy

1. Collect all `<span>` children of `.results-center-half-score`
2. The spans with `class="ct"` or `class="t"` indicate the side for that half
3. **Regulation half 1:** The first pair of scored spans tells team1's first-half side
   - If team1's first span has `class="ct"`, team1 started CT
   - If team1's first span has `class="t"`, team1 started T
4. **Regulation half 2:** Sides flip (CT becomes T, T becomes CT)
5. **Overtime halves:** Spans have NO `class="ct"` or `class="t"` -- just raw numbers in parenthesized groups. Each OT period has its own `(X:Y)` group.
6. **Validation:** Sum of all half scores per team should equal the total map score

### Map Holder Count by Format

| Format | `.mapholder` count | Played maps | Unplayed maps |
|--------|-------------------|-------------|---------------|
| BO1 | 1 | 1 | 0 |
| BO3 (2-0) | 3 | 2 | 1 (map 3) |
| BO3 (2-1) | 3 | 3 | 0 |
| BO5 (3-0 with forfeit) | 5 | 3 (including forfeit) | 2 |
| BO1 forfeit | 1 | 1 | 0 |

### MapStatsID Extraction

**Selector:** `.mapholder a.results-stats[href]` (one per played, non-forfeit map)

**Regex:** `/stats/matches/mapstatsid/(\d+)/`

**Note:** The broader selector `[href*='mapstatsid']` sometimes returns duplicates (the same link appears in another section of the page). Use `.mapholder a.results-stats[href]` for exact count.

### Annotated HTML: Played Map Holder

```html
<div class="mapholder">
  <div class="played">
    <div class="map-name-holder">
      <img alt="Mirage" class="minimap" src="/img/static/maps/mirage.png" title="Mirage"/>
      <div class="mapname">Mirage</div>
    </div>
  </div>
  <div class="results played">
    <div class="results-left won">
      <div class="results-teamlogo-container">
        <img alt="Vitality" class="logo team1Logo" src="..."/>
      </div>
      <div class="results-team-score">13</div>
    </div>
    <div class="results-center">
      <div class="results-center-stats">
        <a class="results-stats" href="/stats/matches/mapstatsid/219128/vitality-vs-g2">STATS</a>
      </div>
      <div class="results-center-half-score">
        <span> (</span>
        <span class="ct">7</span><span class="">:</span><span class="t">5</span>
        <span>; </span>
        <span class="t">6</span><span class="">:</span><span class="ct">6</span>
        <span></span><span>)</span>
      </div>
    </div>
    <div class="results-right lost">
      <div class="results-teamlogo-container">
        <img alt="G2" class="logo team2Logo" src="..."/>
      </div>
      <div class="results-team-score">11</div>
    </div>
  </div>
</div>
```

### Annotated HTML: Unplayed Map Holder (BO3 sweep, map 3)

```html
<div class="mapholder">
  <div class="optional">
    <div class="map-name-holder">
      <img alt="Ancient" class="minimap" src="/img/static/maps/ancient.png" title="Ancient"/>
      <div class="mapname">Ancient</div>
    </div>
  </div>
  <div class="results optional">
    <div class="results-left tie">
      <!-- Score shows "-" -->
      <div class="results-team-score">-</div>
    </div>
    <div class="results-center">
      <div class="results-center-stats"></div>
      <div class="results-center-half-score"></div>
    </div>
    <div class="results-right tie">
      <div class="results-team-score">-</div>
    </div>
  </div>
</div>
```

### Annotated HTML: Forfeit Map Holder

```html
<div class="mapholder">
  <div class="played">
    <div class="map-name-holder">
      <img alt="Default" class="minimap" src="/img/static/maps/default.png" title="Default"/>
      <div class="mapname">Default</div>
    </div>
  </div>
  <div class="results played">
    <div class="results-left lost">
      <div class="results-team-score">0</div>
    </div>
    <div class="results-center">
      <div class="results-center-stats"></div>      <!-- EMPTY: no stats link -->
      <div class="results-center-half-score"></div>  <!-- EMPTY: no half scores -->
    </div>
    <div class="results-right won">
      <div class="results-team-score">1</div>
    </div>
  </div>
</div>
```

---

## Section 3: Veto Sequence

### Structure Overview

There are always **two** `.standard-box.veto-box` elements on the page:

| Element | Content | Selector for content |
|---------|---------|---------------------|
| **First `.veto-box`** | Match format, stage, and forfeit notes | `.veto-box .padding.preformatted-text` |
| **Second `.veto-box`** | Actual veto lines | `.veto-box:nth-of-type(2) .padding > div` |

**Important:** The first `.veto-box` is the SAME element that provides match format and LAN/Online info (Section 1). The second `.veto-box` contains the veto sequence.

### Selector Table

| Field | CSS Selector | Data Type | Required | Extract | Example Value | Notes |
|-------|-------------|-----------|----------|---------|---------------|-------|
| veto_container | `.veto-box:last-of-type .padding` | container | always | **extract** | - | Second `.veto-box` on the page |
| veto_lines | `.veto-box:last-of-type .padding > div` | string[] | always | **extract** | "1. G2 removed Nuke" | Direct `<div>` children, each containing one veto step |

**Note on selector:** Using `.veto-box:last-of-type` to target the second veto box. Alternatively, collect all `.veto-box` elements and index `[1]`. In practice, using index-based selection (`soup.select('.veto-box')[1]`) is more reliable than `:last-of-type` pseudo-class which depends on sibling structure.

### Veto Line Parsing

Each veto line follows one of three patterns:

| Pattern | Regex | Example |
|---------|-------|---------|
| **Remove/ban** | `(\d+)\. (.+) removed (.+)` | "1. G2 removed Nuke" |
| **Pick** | `(\d+)\. (.+) picked (.+)` | "3. G2 picked Mirage" |
| **Left over** | `(\d+)\. (.+) was left over` | "7. Anubis was left over" |

Fields extracted per line:
- `step_number` (int): The sequential number (1-7)
- `team_name` (string): The team performing the action (for "left over", this is the map name)
- `action` (enum): "removed", "picked", or "left_over"
- `map_name` (string): The map being acted upon

### Veto Structure by Format

**BO1 (7 steps):**
```
1. {team1/team2} removed {map}   -- ban
2. {team1/team2} removed {map}   -- ban
3. {team2/team1} removed {map}   -- ban
4. {team2/team1} removed {map}   -- ban
5. {team1/team2} removed {map}   -- ban
6. {team2/team1} removed {map}   -- ban
7. {map} was left over            -- decider
```
All 6 maps are banned (3 per team), 1 remains.

**BO3 (7 steps):**
```
1. {team} removed {map}          -- ban
2. {team} removed {map}          -- ban
3. {team} picked {map}           -- pick (becomes map 1 or 2)
4. {team} picked {map}           -- pick (becomes map 1 or 2)
5. {team} removed {map}          -- ban
6. {team} removed {map}          -- ban
7. {map} was left over            -- decider (becomes map 3)
```
2 bans, 2 picks, 2 bans, 1 left over.

**BO5 (7 steps):**
```
1. {team} removed {map}          -- ban
2. {team} removed {map}          -- ban
3. {team} picked {map}           -- pick
4. {team} picked {map}           -- pick
5. {team} picked {map}           -- pick
6. {team} picked {map}           -- pick
7. {map} was left over            -- decider (becomes map 5)
```
2 bans, 4 picks, 1 left over.

**Forfeit matches:** Veto box is still present and complete. Match 2380434 (full forfeit) has a normal BO1 veto sequence -- the veto happened before the forfeit.

### Annotated HTML: Veto Box (BO3 example, Vitality vs G2)

```html
<!-- First .veto-box: format and stage info -->
<div class="standard-box veto-box">
  <div class="padding preformatted-text">Best of 3 (LAN)
* Swiss round 1</div>
</div>

<!-- Second .veto-box: actual veto sequence -->
<div class="standard-box veto-box">
  <div class="padding">
    <div>1. G2 removed Nuke</div>
    <div>2. Vitality removed Ancient</div>
    <div>3. G2 picked Mirage</div>
    <div>4. Vitality picked Inferno</div>
    <div>5. Vitality removed Dust2</div>
    <div>6. G2 removed Overpass</div>
    <div>7. Anubis was left over</div>
  </div>
</div>
```

### Annotated HTML: Veto Box (BO5 example, Getting Info vs BOSS)

```html
<div class="standard-box veto-box">
  <div class="padding">
    <div>1. BOSS removed Nuke</div>
    <div>2. Getting Info removed Inferno</div>
    <div>3. BOSS picked Mirage</div>
    <div>4. Getting Info picked Overpass</div>
    <div>5. BOSS picked Dust2</div>
    <div>6. Getting Info picked Ancient</div>
    <div>7. Train was left over</div>
  </div>
</div>
```

### Annotated HTML: Veto Box (BO1 example, n00rg vs FALKE)

```html
<div class="standard-box veto-box">
  <div class="padding">
    <div>1. n00rg removed Inferno</div>
    <div>2. n00rg removed Mirage</div>
    <div>3. FALKE removed Ancient</div>
    <div>4. FALKE removed Anubis</div>
    <div>5. FALKE removed Vertigo</div>
    <div>6. n00rg removed Overpass</div>
    <div>7. Nuke was left over</div>
  </div>
</div>
```

---

## Section 4: Player Rosters

### Selector Table

| Field | CSS Selector | Data Type | Required | Extract | Example Value | Notes |
|-------|-------------|-----------|----------|---------|---------------|-------|
| lineups_container | `.lineups` | container | always | **extract** | - | Contains both teams' roster data |
| team_lineup_blocks | `.lineups .lineup.standard-box` | container[] | always | **extract** | - | Two blocks: first = team1, second = team2 |
| team_name_in_lineup | `.lineup .box-headline a.text-ellipsis` | string | always | **extract** | "Vitality" | Team name with link; href has team ID |
| team_ranking_in_lineup | `.lineup .box-headline .teamRanking a` | string | sometimes | **extract** | "World rank: #1" | Parse rank number from text. Missing if unranked. |
| player_containers | `.lineup .players` | container[] | always | **extract** | - | One per team; `.players[0]` = team1, `.players[1]` = team2 |
| player_id | `.players [data-player-id]` | int | always | **extract** | 11893 | `data-player-id` attribute on `.flagAlign` div |
| player_name | `.players [data-player-id] .text-ellipsis` | string | always | **extract** | "ZywOo" | The short nickname. Note: there are many `.text-ellipsis` in nested contexts. The one inside the `[data-player-id]` element is the clean nickname. |
| player_href | `.players td.player a[href*='/player/']` | string | always | **extract** | "/player/11893/zywoo" | Player profile link in the first `<tr>` (image row) |
| player_nationality | `.players [data-player-id] img.flag` | string | always | **extract** | "France" | `title` attribute on the flag `<img>` |
| player_team_ordinal | `.players [data-player-id]` | int | always | **extract** | 1 | `data-team-ordinal` attribute: `1` = team1, `2` = team2 (if present) |

### Team Attribution

Players are attributed to teams by their position in the DOM:

1. `.lineups` contains two `.lineup.standard-box` blocks
2. First block = team1 (same as `.team1-gradient`), second block = team2
3. Each `.lineup` block has a `.box-headline` with team name + ranking, and a `.players` div with the roster
4. Inside `.players`, each player's `.flagAlign` div has a `data-team-ordinal` attribute (`1` or `2`)

**Consistent across all 9 samples:** Every match has exactly 2 `.players` containers with exactly 5 `[data-player-id]` elements each (10 total players per match). This holds true even for the forfeit match (2380434).

### Roster Table Structure

Each `.players` div contains a `<table>` with two `<tr>` rows:
- **Row 1 (`.player.player-image`):** Player photos with links to profiles (`a[href*='/player/']`)
- **Row 2 (`.player`):** Player nickname, flag, and `data-player-id` attribute

**For extracting player data, Row 2 is the primary target** because it contains both the ID and the structured name/flag data.

### Annotated HTML: Player Roster

```html
<div class="players">
  <table class="table">
    <tbody>
      <!-- Row 1: Player photos (link has player ID in href) -->
      <tr>
        <td class="player player-image">
          <a href="/player/18462/mezii">
            <div>
              <img alt="William 'mezii' Merriman" class="player-photo"
                   src="..." title="William 'mezii' Merriman"/>
            </div>
          </a>
        </td>
        <!-- ... 4 more player-image cells -->
      </tr>
      <!-- Row 2: Player names with IDs and flags -->
      <tr>
        <td class="player">
          <a href="/player/18462/mezii">
            <div class="flagAlign" data-player-id="18462" data-team-ordinal="1">
              <img alt="United Kingdom" class="flag" title="United Kingdom"/>
              <div class="text-ellipsis">mezii</div>
            </div>
          </a>
        </td>
        <!-- ... 4 more player cells -->
      </tr>
    </tbody>
  </table>
</div>
```

### Player ID Extraction Strategy

Two reliable paths to player ID:
1. **Preferred:** `data-player-id` attribute on `.flagAlign` div (clean integer)
2. **Fallback:** Parse from `a[href*='/player/']` with regex `/player/(\d+)/`

Both are available on every sample, including forfeit matches.

### Player Full Name

The `<img>` in Row 1 has an `alt` attribute with the player's full name in format `"FirstName 'Nickname' LastName"` (e.g., `"Mathieu 'ZywOo' Herbaut"`). This is also available in the `title` attribute. This is a **future** extraction target -- not in the current schema but could be useful.

---

## Section 5: Other Elements

### Selector Table

| Field | CSS Selector | Data Type | Required | Extract | Example Value | Notes |
|-------|-------------|-----------|----------|---------|---------------|-------|
| head_to_head | `.head-to-head-listing` | container | always | **future** | - | Historical matches between these teams. Present but empty on first encounters. |
| h2h_rows | `.head-to-head-listing tr` | rows[] | sometimes | **future** | - | 0-20 rows. Missing for teams with no history (2366498, 2377467, 2380434). |
| streams | `.streams` | container | always | skip | - | Stream links and VOD links. Not needed for stat scraping. |
| stream_boxes | `.stream-box` | container[] | always | skip | - | Individual stream entries. 1-8 per match; forfeit has 1 ("No media yet"). |
| demo_link | `a[href*='demo']` | string | usually | **future** | "Click here if your download..." | Demo download link. Missing on forfeit match. |
| highlight_embeds | `[data-highlight-embed]` | container[] | sometimes | skip | - | Highlight clip embeds. Only on some matches (2/9 samples). |
| past_matches | `.past-matches` | container | always | skip | - | Past match results section. Present on all samples. |
| match_page_wrapper | `.match-page` | container | always | skip | - | Top-level wrapper for the match page content. |
| ad_elements | `[class*='ad-']` | container[] | always | skip | - | 6-7 ad containers per page. Filter out during parsing. |
| sponsor_elements | `[class*='sponsor']` | container[] | usually | skip | - | 0-2 sponsor elements. Missing on forfeit match. |

### Elements NOT Found

| Selector | Expected? | Actual | Notes |
|----------|-----------|--------|-------|
| `.match-info-box` | Maybe | Not found on ANY sample | This selector is from the map stats page, not match overview |
| `[href*='gotv']` | Maybe | Not found on ANY sample | GOTV links not present on completed match pages |
| `.highlight-video` | Maybe | Not found | Highlights use `[data-highlight-embed]` instead |
| `.hltv-modal` | No | Not found | No modals in static HTML |
| `.pick` (map pick indicator) | Maybe | Not found | Map picks are only communicated through veto text, not visual indicators on map holders |

---

## Forfeit/Walkover Differences

### Comparison: Forfeit (2380434) vs Normal (2389951)

| Element | Forfeit | Normal | Status |
|---------|---------|--------|--------|
| Team 1 name | Present | Present | **Same** |
| Team 2 name | Present | Present | **Same** |
| Team 1/2 hrefs | Present | Present | **Same** |
| Rankings | Present (2) | Present (2) | **Same** |
| Match date | Present | Present | **Same** |
| Event name/ID | Present | Present | **Same** |
| Format text | Present (includes forfeit note) | Present | **Same** (extra lines on forfeit) |
| **Match score divs** | **MISSING** (no `.won`/`.lost`) | Present | **DIFFERENT** |
| Map holders | 1 (Default) | 3 | **Different count** |
| Map name | "Default" | Actual map names | **Different** |
| Map scores | 0-1 | Actual scores | **Different** |
| Half scores | Empty element | Populated | **MISSING content** |
| Stats links | **ABSENT** | 3 links | **MISSING** |
| Veto box | Present (full veto + forfeit note) | Present | **Same** |
| Lineups/Players | Present (10 players) | Present (10 players) | **Same** |
| Head-to-head | Present (0 rows) | Present (rows) | **Same structure** |
| Streams | 1 ("No media yet") | 8 | **Different count** |
| Demo link | **ABSENT** | Present | **MISSING** |
| Countdown | "Match deleted" | "Match over" | **Different text** |
| Sponsor elements | **ABSENT** | Present | **MISSING** |

### Forfeit Detection Checklist

A match is a forfeit/walkover if ANY of these are true:
1. `.countdown` text is "Match deleted"
2. `.mapname` text is "Default" (on any map)
3. `.padding.preformatted-text` contains "forfeit" (case-insensitive)
4. No `.won` or `.lost` divs in team gradients (full forfeit only)
5. Map stats link (`a.results-stats[href]`) is absent on a played map

### Partial Forfeit (BO5, match 2384993)

In a partial forfeit, some maps are played normally while one is forfeited:

| Map | Name | Score | Stats Link | Status |
|-----|------|-------|------------|--------|
| 1 | Mirage | 19-17 | Present | **Normal** (with overtime) |
| 2 | Overpass | 13-4 | Present | **Normal** |
| 3 | Default | 1-0 | Absent | **Forfeit** |
| 4 | Ancient | - | Absent | **Unplayed** |
| 5 | Train | - | Absent | **Unplayed** |

The `.countdown` text is "Match over" (NOT "Match deleted") because the match result was decided. The `.won`/`.lost` divs ARE present (team1 won 3-0). Forfeit note is in the preformatted-text: "** BOSS forfeit 3rd map as they are unable to play due to technical issues".

---

## Extraction Priority Summary

### Must Extract (Phase 5 parser targets)

| Priority | Field | Selector | Notes |
|----------|-------|----------|-------|
| P0 | team1_name, team2_name | `.team{1,2}-gradient .teamName` | Core identity |
| P0 | team1_id, team2_id | `.team{1,2}-gradient a[href*='/team/']` | Parse from href |
| P0 | match_date | `.timeAndEvent .date[data-unix]` | Unix milliseconds |
| P0 | event_name, event_id | `.timeAndEvent .event a` | Parse ID from href |
| P0 | match_format | `.padding.preformatted-text` | Parse "Best of N" |
| P0 | map_name, map_scores | `.mapholder .mapname`, `.results-team-score` | Per map |
| P0 | mapstatsid | `.mapholder a.results-stats[href]` | Links to detailed stats |
| P1 | team1_score, team2_score | `.team{1,2}-gradient .won` or `.lost` | Series score |
| P1 | winner | `.won` class presence | Which team won |
| P1 | half_scores | `.results-center-half-score` spans | CT/T breakdown |
| P1 | lan_or_online | `.padding.preformatted-text` | Parse "(LAN)" or "(Online)" |
| P1 | player roster | `[data-player-id]`, `.text-ellipsis` | 10 players per match |
| P2 | veto_sequence | `.veto-box:last .padding > div` | 7 veto steps |
| P2 | team_rankings | `.lineups .teamRanking a` | May be missing for unranked |
| P2 | player_nationality | `img.flag[title]` | Flag title attribute |

### Skip (present but not needed)

| Field | Selector | Reason |
|-------|----------|--------|
| Streams | `.streams`, `.stream-box` | Not relevant to match stats |
| Ads | `[class*='ad-']` | Noise |
| Sponsors | `[class*='sponsor']` | Noise |
| Match page wrapper | `.match-page` | Structural only |
| Countdown | `.countdown` | "Match over" / "Match deleted" -- could use for forfeit detection but other signals are more reliable |
| Standard boxes | `.standard-box` | Generic container class |

### Future (might extract later)

| Field | Selector | Notes |
|-------|----------|-------|
| Head-to-head history | `.head-to-head-listing tr` | Historical matchups |
| Demo links | `a[href*='demo']` | For replay analysis |
| Highlight clips | `[data-highlight-embed]` | Highlight moments |
| Player full name | `.player-image img[alt]` | "FirstName 'Nick' LastName" from alt attribute |
| Past matches | `.past-matches` | Each team's recent results |

---

## Implementation Notes for Phase 5

1. **Forfeit handling must be the first check.** Before extracting map scores, check if `mapname == "Default"` or if `.won`/`.lost` divs are missing. Handle forfeit as a special case that skips half-score and stats-link extraction.

2. **Rankings are NOT in the team gradient area.** They are inside `.lineups .box-headline .teamRanking a`. Use the lineup container's document order (first = team1, second = team2) for attribution.

3. **Half-score parsing should use span classes.** Don't try to parse the `(7:5;6:6)` text -- instead iterate over the `<span>` children and use `class="ct"` / `class="t"` to determine sides. For overtime periods, spans lack ct/t classes.

4. **Map pick attribution comes from vetoes, not map holders.** There is no visual pick indicator on map holder divs. Cross-reference the veto sequence to determine which team picked which map.

5. **Unplayed maps are identifiable by the `.optional` class** on the inner div. The score text is "-" (dash). Do not attempt to extract stats links or half scores from unplayed maps.

6. **Two `.veto-box` elements exist.** The first is format info (already used for match_format), the second is the veto sequence. Index-based selection (`[1]`) is recommended over CSS pseudo-classes.

7. **Player extraction should use `data-player-id` attribute** as primary identifier. The player href (`/player/{id}/{name}`) is a reliable fallback. Every match (including forfeits) has 10 players with `data-player-id`.

8. **Team left = team1, always.** This is consistent across all 9 samples. `.results-left` always corresponds to team1/`.team1-gradient`.
