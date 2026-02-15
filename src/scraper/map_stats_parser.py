"""Map stats page parser for HLTV map detail pages.

Provides:
- parse_map_stats: pure function extracting scoreboard and round history from map stats HTML
- MapStats, PlayerStats, RoundOutcome: structured return types

All selectors verified against 12 real HTML samples in Phase 3 recon.
"""

import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger(__name__)


# Mapping from outcome image filename to (winner_side, win_type)
OUTCOME_MAP: dict[str, tuple[str, str]] = {
    "ct_win.svg": ("CT", "elimination"),
    "t_win.svg": ("T", "elimination"),
    "bomb_exploded.svg": ("T", "bomb_planted"),
    "bomb_defused.svg": ("CT", "defuse"),
    "stopwatch.svg": ("CT", "time"),
}


@dataclass
class PlayerStats:
    """Per-player scoreboard stats from a map stats page."""

    player_id: int
    player_name: str
    team_id: int
    kills: int
    deaths: int
    assists: int
    flash_assists: int
    hs_kills: int
    kd_diff: int  # kills - deaths
    adr: float
    kast: float
    opening_kills: int
    opening_deaths: int
    fk_diff: int  # opening_kills - opening_deaths
    rating: float
    rating_version: str  # "2.0" or "3.0"
    multi_kills: int
    clutch_wins: int
    traded_deaths: int
    round_swing: float | None  # Rating 3.0 only; None for 2.0


@dataclass
class RoundOutcome:
    """Outcome of a single round in a map."""

    round_number: int
    winner_team_id: int
    winner_side: str  # "CT" or "T"
    win_type: str  # "elimination", "bomb_planted", "defuse", "time"


@dataclass
class MapStats:
    """Complete parsed data from an HLTV map stats page."""

    mapstatsid: int
    team_left_id: int
    team_left_name: str
    team_right_id: int
    team_right_name: str
    team_left_score: int
    team_right_score: int
    map_name: str
    rating_version: str  # "2.0" or "3.0"
    team_left_ct_rounds: int
    team_left_t_rounds: int
    team_right_ct_rounds: int
    team_right_t_rounds: int
    team_left_starting_side: str  # "CT" or "T"
    players: list[PlayerStats]
    rounds: list[RoundOutcome]


def parse_map_stats(html: str, mapstatsid: int) -> MapStats:
    """Parse an HLTV map stats page into structured data.

    Pure function: HTML string in, MapStats out. No side effects.

    Args:
        html: Raw HTML string of a map stats page.
        mapstatsid: HLTV mapstatsid (for inclusion in result).

    Returns:
        MapStats with all extracted fields.

    Raises:
        ValueError: If required fields (team names, IDs, scores) are missing.
    """
    soup = BeautifulSoup(html, "lxml")

    rating_version = _detect_rating_version(soup)
    metadata = _extract_metadata(soup, mapstatsid)
    half_breakdown = _extract_half_breakdown(soup)
    players = _extract_scoreboard(
        soup,
        rating_version,
        metadata["team_left_id"],
        metadata["team_right_id"],
    )
    rounds = _extract_round_history(
        soup,
        metadata["team_left_id"],
        metadata["team_right_id"],
    )

    return MapStats(
        mapstatsid=mapstatsid,
        team_left_id=metadata["team_left_id"],
        team_left_name=metadata["team_left_name"],
        team_right_id=metadata["team_right_id"],
        team_right_name=metadata["team_right_name"],
        team_left_score=metadata["team_left_score"],
        team_right_score=metadata["team_right_score"],
        map_name=metadata["map_name"],
        rating_version=rating_version,
        team_left_ct_rounds=half_breakdown["team_left_ct_rounds"],
        team_left_t_rounds=half_breakdown["team_left_t_rounds"],
        team_right_ct_rounds=half_breakdown["team_right_ct_rounds"],
        team_right_t_rounds=half_breakdown["team_right_t_rounds"],
        team_left_starting_side=half_breakdown["team_left_starting_side"],
        players=players,
        rounds=rounds,
    )


def _detect_rating_version(soup: BeautifulSoup) -> str:
    """Detect whether the page uses Rating 2.0 or 3.0.

    Primary: check th.st-rating text for "2.0" or "3.0".
    Fallback: presence of th.st-roundSwing -> "3.0".
    Default: "3.0" (modern pages).
    """
    rating_th = soup.select_one("th.st-rating")
    if rating_th:
        text = rating_th.get_text(strip=True)
        if "2.0" in text:
            return "2.0"
        if "3.0" in text:
            return "3.0"

    # Fallback: presence of roundSwing column header
    if soup.select_one("th.st-roundSwing"):
        return "3.0"

    return "3.0"


def _extract_metadata(soup: BeautifulSoup, mapstatsid: int) -> dict:
    """Extract map-level metadata from the page.

    Returns dict with keys: team_left_name, team_left_id, team_right_name,
    team_right_id, team_left_score, team_right_score, map_name.
    """
    # Map name: bare NavigableString child of .match-info-box
    match_info_box = soup.select_one(".match-info-box")
    if not match_info_box:
        raise ValueError(f"Mapstats {mapstatsid}: missing .match-info-box element")

    map_name = ""
    for child in match_info_box.children:
        if isinstance(child, NavigableString) and child.strip():
            map_name = child.strip()
            break
    if not map_name:
        logger.warning("Mapstats %d: could not extract map name from .match-info-box", mapstatsid)
        map_name = "Unknown"

    # Team left
    tl_a = soup.select_one(".team-left a")
    if not tl_a:
        raise ValueError(f"Mapstats {mapstatsid}: missing .team-left a element")
    team_left_name = tl_a.get_text(strip=True)
    tl_m = re.search(r"/stats/teams/(\d+)/", tl_a.get("href", ""))
    if not tl_m:
        raise ValueError(
            f"Mapstats {mapstatsid}: could not parse team_left_id from href "
            f"({tl_a.get('href')})"
        )
    team_left_id = int(tl_m.group(1))

    # Team right
    tr_a = soup.select_one(".team-right a")
    if not tr_a:
        raise ValueError(f"Mapstats {mapstatsid}: missing .team-right a element")
    team_right_name = tr_a.get_text(strip=True)
    tr_m = re.search(r"/stats/teams/(\d+)/", tr_a.get("href", ""))
    if not tr_m:
        raise ValueError(
            f"Mapstats {mapstatsid}: could not parse team_right_id from href "
            f"({tr_a.get('href')})"
        )
    team_right_id = int(tr_m.group(1))

    # Scores
    tl_score_el = soup.select_one(".team-left .bold")
    tr_score_el = soup.select_one(".team-right .bold")
    if not tl_score_el or not tr_score_el:
        raise ValueError(
            f"Mapstats {mapstatsid}: missing score elements "
            f"(left={tl_score_el}, right={tr_score_el})"
        )
    team_left_score = int(tl_score_el.get_text(strip=True))
    team_right_score = int(tr_score_el.get_text(strip=True))

    return {
        "team_left_name": team_left_name,
        "team_left_id": team_left_id,
        "team_right_name": team_right_name,
        "team_right_id": team_right_id,
        "team_left_score": team_left_score,
        "team_right_score": team_right_score,
        "map_name": map_name,
    }


def _extract_half_breakdown(soup: BeautifulSoup) -> dict:
    """Extract CT/T half breakdown and starting side from the score breakdown row.

    Returns dict with keys: team_left_ct_rounds, team_left_t_rounds,
    team_right_ct_rounds, team_right_t_rounds, team_left_starting_side.
    """
    result = {
        "team_left_ct_rounds": 0,
        "team_left_t_rounds": 0,
        "team_right_ct_rounds": 0,
        "team_right_t_rounds": 0,
        "team_left_starting_side": "CT",
    }

    # The breakdown is in the first .match-info-row's .right div
    info_rows = soup.select(".match-info-row")
    if not info_rows:
        logger.warning("No .match-info-row elements found; cannot extract half breakdown")
        return result

    right_div = info_rows[0].select_one(".right")
    if not right_div:
        logger.warning("No .right div in first .match-info-row")
        return result

    # Extract spans with ct-color or t-color classes (the half breakdown values)
    # These are the regulation half values, not the total scores or OT
    side_spans: list[tuple[int, str]] = []
    for span in right_div.select("span"):
        classes = span.get("class", [])
        text = span.get_text(strip=True)
        if "ct-color" in classes or "t-color" in classes:
            try:
                val = int(text)
            except ValueError:
                continue
            side = "CT" if "ct-color" in classes else "T"
            side_spans.append((val, side))

    if len(side_spans) < 4:
        logger.warning(
            "Expected at least 4 ct/t-color spans, found %d", len(side_spans)
        )
        return result

    # Layout: [0] = team_left half1, [1] = team_right half1,
    #         [2] = team_left half2, [3] = team_right half2
    h1_left_val, h1_left_side = side_spans[0]
    h1_right_val, _h1_right_side = side_spans[1]
    h2_left_val, _h2_left_side = side_spans[2]
    h2_right_val, _h2_right_side = side_spans[3]

    # h1_left_side tells us team_left's starting side
    team_left_starting_side = h1_left_side

    if team_left_starting_side == "CT":
        result["team_left_ct_rounds"] = h1_left_val
        result["team_left_t_rounds"] = h2_left_val
        result["team_right_t_rounds"] = h1_right_val
        result["team_right_ct_rounds"] = h2_right_val
    else:  # team_left started T
        result["team_left_t_rounds"] = h1_left_val
        result["team_left_ct_rounds"] = h2_left_val
        result["team_right_ct_rounds"] = h1_right_val
        result["team_right_t_rounds"] = h2_right_val

    result["team_left_starting_side"] = team_left_starting_side
    return result


def _parse_compound_stat(text: str) -> tuple[int, int]:
    """Parse a compound stat like '14(9)' into (main, sub) tuple.

    Returns (main_value, sub_value). Defaults to (0, 0) on parse failure.
    """
    m = re.match(r"(\d+)\((\d+)\)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Try just the main value
    try:
        return int(text), 0
    except (ValueError, TypeError):
        return 0, 0


def _parse_opkd(text: str) -> tuple[int, int]:
    """Parse Op.K-D like '2 : 5' into (opening_kills, opening_deaths).

    Returns (0, 0) on parse failure.
    """
    m = re.match(r"(\d+)\s*:\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def _parse_percentage(text: str) -> float:
    """Parse a percentage like '66.7%' or '+2.90%' into a float.

    Returns 0.0 on parse failure.
    """
    cleaned = text.replace("%", "").replace("+", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _extract_scoreboard(
    soup: BeautifulSoup,
    rating_version: str,
    team_left_id: int,
    team_right_id: int,
) -> list[PlayerStats]:
    """Extract per-player scoreboard stats from totalstats tables.

    First .stats-table.totalstats = team-left, second = team-right.
    Each table has 5 player rows in tbody.
    """
    tables = soup.select(".stats-table.totalstats")
    if len(tables) < 2:
        logger.warning(
            "Expected 2 .stats-table.totalstats tables, found %d", len(tables)
        )
        return []

    players: list[PlayerStats] = []
    team_ids = [team_left_id, team_right_id]

    for table_idx, table in enumerate(tables[:2]):
        team_id = team_ids[table_idx]
        rows = table.select("tbody tr")

        for row in rows:
            # Player ID and name
            player_a = row.select_one("td.st-player a")
            if not player_a:
                logger.warning("Skipping row without player link in table %d", table_idx)
                continue

            player_name = player_a.get_text(strip=True)
            player_href = player_a.get("href", "")
            pid_m = re.search(r"/stats/players/(\d+)/", player_href)
            player_id = int(pid_m.group(1)) if pid_m else 0

            # Kills and headshots: "14(9)"
            kills_td = row.select_one("td.st-kills")
            kills_text = kills_td.get_text(strip=True) if kills_td else "0(0)"
            kills, hs_kills = _parse_compound_stat(kills_text)

            # Assists and flash assists: "2(0)"
            assists_td = row.select_one("td.st-assists")
            assists_text = assists_td.get_text(strip=True) if assists_td else "0(0)"
            assists, flash_assists = _parse_compound_stat(assists_text)

            # Deaths and traded deaths: "15(2)"
            deaths_td = row.select_one("td.st-deaths")
            deaths_text = deaths_td.get_text(strip=True) if deaths_td else "0(0)"
            deaths, traded_deaths = _parse_compound_stat(deaths_text)

            # ADR
            adr_td = row.select_one("td.st-adr")
            adr_text = adr_td.get_text(strip=True) if adr_td else "0"
            try:
                adr = float(adr_text)
            except (ValueError, TypeError):
                adr = 0.0

            # KAST: "66.7%"
            kast_td = row.select_one("td.st-kast")
            kast_text = kast_td.get_text(strip=True) if kast_td else "0%"
            kast = _parse_percentage(kast_text)

            # Rating
            rating_td = row.select_one("td.st-rating")
            rating_text = rating_td.get_text(strip=True) if rating_td else "0"
            try:
                rating = float(rating_text)
            except (ValueError, TypeError):
                rating = 0.0

            # Op.K-D: "2 : 5"
            opkd_td = row.select_one("td.st-opkd")
            opkd_text = opkd_td.get_text(strip=True) if opkd_td else "0 : 0"
            opening_kills, opening_deaths = _parse_opkd(opkd_text)

            # Multi-kills
            mks_td = row.select_one("td.st-mks")
            mks_text = mks_td.get_text(strip=True) if mks_td else "0"
            try:
                multi_kills = int(mks_text)
            except (ValueError, TypeError):
                multi_kills = 0

            # Clutch wins
            clutches_td = row.select_one("td.st-clutches")
            clutches_text = clutches_td.get_text(strip=True) if clutches_td else "0"
            try:
                clutch_wins = int(clutches_text)
            except (ValueError, TypeError):
                clutch_wins = 0

            # Round swing (Rating 3.0 only): "+2.90%"
            round_swing: float | None = None
            if rating_version == "3.0":
                rs_td = row.select_one("td.st-roundSwing")
                if rs_td:
                    rs_text = rs_td.get_text(strip=True)
                    round_swing = _parse_percentage(rs_text)

            players.append(
                PlayerStats(
                    player_id=player_id,
                    player_name=player_name,
                    team_id=team_id,
                    kills=kills,
                    deaths=deaths,
                    assists=assists,
                    flash_assists=flash_assists,
                    hs_kills=hs_kills,
                    kd_diff=kills - deaths,
                    adr=adr,
                    kast=kast,
                    opening_kills=opening_kills,
                    opening_deaths=opening_deaths,
                    fk_diff=opening_kills - opening_deaths,
                    rating=rating,
                    rating_version=rating_version,
                    multi_kills=multi_kills,
                    clutch_wins=clutch_wins,
                    traded_deaths=traded_deaths,
                    round_swing=round_swing,
                )
            )

    return players


def _extract_round_history(
    soup: BeautifulSoup,
    team_left_id: int,
    team_right_id: int,
) -> list[RoundOutcome]:
    """Extract round-by-round history from round history containers.

    Handles 3 patterns:
    - Regular match: 1 container, <= 24 outcomes
    - Single OT: 1 container, > 24 outcomes (up to 30)
    - Extended OT: 2 containers (regulation + overtime)
    """
    containers = soup.select(".round-history-con")
    if not containers:
        logger.warning("No .round-history-con containers found")
        return []

    rounds: list[RoundOutcome] = []
    round_number = 0

    for container in containers:
        team_rows = container.select(".round-history-team-row")
        if len(team_rows) < 2:
            logger.warning(
                "Expected 2 .round-history-team-row per container, found %d",
                len(team_rows),
            )
            continue

        # Top row = team-left, bottom row = team-right
        top_outcomes = team_rows[0].select("img.round-history-outcome")
        bottom_outcomes = team_rows[1].select("img.round-history-outcome")

        for top_img, bottom_img in zip(top_outcomes, bottom_outcomes):
            top_src = top_img.get("src", "")
            bottom_src = bottom_img.get("src", "")

            top_fname = top_src.split("/")[-1] if top_src else ""
            bottom_fname = bottom_src.split("/")[-1] if bottom_src else ""

            top_is_empty = top_fname == "emptyHistory.svg"
            bottom_is_empty = bottom_fname == "emptyHistory.svg"

            if top_is_empty and bottom_is_empty:
                # Should not happen, but defensive
                continue

            round_number += 1

            if not top_is_empty:
                # Team-left won this round
                winner_team_id = team_left_id
                outcome_key = top_fname
            else:
                # Team-right won this round
                winner_team_id = team_right_id
                outcome_key = bottom_fname

            if outcome_key in OUTCOME_MAP:
                winner_side, win_type = OUTCOME_MAP[outcome_key]
            else:
                logger.warning(
                    "Unknown outcome image '%s' in round %d", outcome_key, round_number
                )
                winner_side = "CT"
                win_type = "elimination"

            rounds.append(
                RoundOutcome(
                    round_number=round_number,
                    winner_team_id=winner_team_id,
                    winner_side=winner_side,
                    win_type=win_type,
                )
            )

    return rounds
