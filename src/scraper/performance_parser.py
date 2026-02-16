"""Performance page parser for HLTV map performance pages.

Provides:
- parse_performance: pure function extracting player metrics and kill matrix from performance HTML
- PerformanceData, PlayerPerformance, KillMatrixEntry, TeamOverview: structured return types

All selectors verified against 12 real HTML samples in Phase 3 recon.
Primary data source: FusionChart JSON in data-fusionchart-config attribute (use displayValue, NOT value).
"""

import json
import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


@dataclass
class PlayerPerformance:
    """Per-player rate metrics from FusionChart bar graph."""

    player_id: int
    player_name: str
    kpr: float
    dpr: float
    kast: float  # Percentage 0-100, stripped of '%'
    adr: float
    rating: float
    mk_rating: float
    round_swing: float  # signed percentage


@dataclass
class KillMatrixEntry:
    """Head-to-head kill count between two players."""

    matrix_type: str  # "all", "first_kill", "awp"
    player1_id: int  # Row player (team2)
    player2_id: int  # Column player (team1)
    player1_kills: int  # Row player kills
    player2_kills: int  # Column player kills


@dataclass
class TeamOverview:
    """Team-level aggregated stats from performance overview table."""

    team_name: str
    total_kills: int
    total_deaths: int
    total_assists: int


@dataclass
class PerformanceData:
    """Complete parsed data from an HLTV performance page."""

    mapstatsid: int
    players: list[PlayerPerformance]
    kill_matrix: list[KillMatrixEntry]
    teams: list[TeamOverview]


def _safe_float(value: str, default: float = 0.0) -> float:
    """Parse a float from a displayValue string, handling '-' (dash) as default.

    HLTV uses '-' when a stat is unavailable (e.g., ADR for a player with 0 damage).
    """
    cleaned = value.rstrip("%").lstrip("+").strip()
    if not cleaned or cleaned == "-":
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def _safe_float_signed(value: str, default: float = 0.0) -> float:
    """Parse a signed float from a displayValue like '+12.23%' or '-1.93%'.

    Preserves sign. Handles '-' (dash) as default.
    """
    cleaned = value.rstrip("%").strip()
    if not cleaned or cleaned == "-":
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


# Mapping from kill matrix container ID to matrix_type
_MATRIX_TYPE_MAP: dict[str, str] = {
    "ALL-content": "all",
    "FIRST_KILL-content": "first_kill",
    "AWP-content": "awp",
}


def parse_performance(html: str, mapstatsid: int) -> PerformanceData:
    """Parse an HLTV performance page into structured data.

    Pure function: HTML string in, PerformanceData out. No side effects.

    Args:
        html: Raw HTML string of a performance page.
        mapstatsid: HLTV mapstatsid (for inclusion in result).

    Returns:
        PerformanceData with all extracted fields.

    Raises:
        ValueError: If critical data is missing (no player cards, no FusionChart config).
    """
    soup = BeautifulSoup(html, "lxml")

    players = _parse_player_cards(soup)
    kill_matrix = _parse_kill_matrix(soup)
    teams = _parse_team_overview(soup)

    return PerformanceData(
        mapstatsid=mapstatsid,
        players=players,
        kill_matrix=kill_matrix,
        teams=teams,
    )


def _parse_player_cards(
    soup: BeautifulSoup,
) -> list[PlayerPerformance]:
    """Extract performance metrics from all 10 player cards.

    Each player card is a .standard-box containing a [data-fusionchart-config] element.
    Player identity comes from .headline a[href] and .player-nick.
    Metrics come from the FusionChart JSON bars using displayValue (NOT value).
    """
    chart_elements = soup.select("[data-fusionchart-config]")
    if not chart_elements:
        raise ValueError("No [data-fusionchart-config] elements found on performance page")

    players: list[PlayerPerformance] = []

    for chart_el in chart_elements:
        # Find the enclosing .standard-box
        box = chart_el.find_parent("div", class_="standard-box")
        if not box:
            logger.warning("FusionChart element without .standard-box parent, skipping")
            continue

        # Player identity
        headline_a = box.select_one(".headline a[href]")
        if not headline_a:
            logger.warning("Player card without .headline a[href], skipping")
            continue

        nick_el = box.select_one(".player-nick")
        player_name = nick_el.get_text(strip=True) if nick_el else ""
        if not player_name:
            # Fallback: use link text
            player_name = headline_a.get_text(strip=True)

        href = headline_a.get("href", "")
        pid_m = re.search(r"/player/(\d+)/", href)
        if not pid_m:
            logger.warning("Could not parse player ID from href: %s", href)
            continue
        player_id = int(pid_m.group(1))

        # FusionChart JSON
        try:
            config = json.loads(chart_el["data-fusionchart-config"])
            bars = config["dataSource"]["data"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse FusionChart JSON for player %s: %s", player_name, e)
            continue

        bar_map = {bar["label"]: bar["displayValue"] for bar in bars}

        # Common metrics (use _safe_float to handle '-' dash values)
        try:
            kpr = _safe_float(bar_map["KPR"])
            dpr = _safe_float(bar_map["DPR"])
            kast = _safe_float(bar_map["KAST"].rstrip("%"))
            adr = _safe_float(bar_map["ADR"])
        except KeyError as e:
            logger.warning("Missing common metric key for player %s: %s", player_name, e)
            continue

        # Rating 3.0 metrics (all CS2 matches)
        try:
            rating = _safe_float(bar_map["Rating 3.0"])
            mk_rating = _safe_float(bar_map["MK rating"])
            round_swing = _safe_float_signed(bar_map["Swing"])
        except KeyError as e:
            logger.warning(
                "Missing Rating 3.0 metric key for player %s: %s", player_name, e
            )
            continue

        players.append(
            PlayerPerformance(
                player_id=player_id,
                player_name=player_name,
                kpr=kpr,
                dpr=dpr,
                kast=kast,
                adr=adr,
                rating=rating,
                mk_rating=mk_rating,
                round_swing=round_swing,
            )
        )

    if not players:
        raise ValueError("No player cards could be parsed from performance page")

    return players


def _parse_kill_matrix(soup: BeautifulSoup) -> list[KillMatrixEntry]:
    """Parse all 3 kill matrix types (all, first_kill, awp).

    Each .killmatrix-content has an ID mapping to a matrix_type.
    Column headers (.killmatrix-topbar td a) are team1 players.
    Data rows (tr:not(.killmatrix-topbar)) have team2 row player + kill cells.
    """
    entries: list[KillMatrixEntry] = []

    km_containers = soup.select(".killmatrix-content")
    if not km_containers:
        logger.warning("No .killmatrix-content elements found")
        return entries

    for container in km_containers:
        container_id = container.get("id", "")
        matrix_type = _MATRIX_TYPE_MAP.get(container_id)
        if not matrix_type:
            logger.warning("Unknown kill matrix container ID: %s", container_id)
            continue

        table = container.select_one(".stats-table")
        if not table:
            logger.warning("No .stats-table in %s", container_id)
            continue

        # Column headers = team1 players
        topbar = table.select_one(".killmatrix-topbar")
        if not topbar:
            logger.warning("No .killmatrix-topbar in %s", container_id)
            continue

        col_links = topbar.select("td a")
        col_ids: list[int] = []
        for a_el in col_links:
            href = a_el.get("href", "")
            m = re.search(r"(?:/player/|/stats/players/)(\d+)/", href)
            col_ids.append(int(m.group(1)) if m else 0)

        # Data rows = team2 players
        data_rows = table.select("tr:not(.killmatrix-topbar)")
        for row in data_rows:
            row_td = row.select_one("td.team2")
            if not row_td:
                continue

            row_link = row_td.select_one("a")
            if not row_link:
                continue

            row_href = row_link.get("href", "")
            m = re.search(r"(?:/player/|/stats/players/)(\d+)/", row_href)
            row_player_id = int(m.group(1)) if m else 0

            cells = row.select("td.text-center")
            for i, cell in enumerate(cells):
                if i >= len(col_ids):
                    break

                t2_score_el = cell.select_one(".team2-player-score")
                t1_score_el = cell.select_one(".team1-player-score")

                try:
                    t2_kills = int(t2_score_el.get_text(strip=True)) if t2_score_el else 0
                except ValueError:
                    t2_kills = 0
                try:
                    t1_kills = int(t1_score_el.get_text(strip=True)) if t1_score_el else 0
                except ValueError:
                    t1_kills = 0

                entries.append(
                    KillMatrixEntry(
                        matrix_type=matrix_type,
                        player1_id=row_player_id,
                        player2_id=col_ids[i],
                        player1_kills=t2_kills,
                        player2_kills=t1_kills,
                    )
                )

    return entries


def _parse_team_overview(soup: BeautifulSoup) -> list[TeamOverview]:
    """Extract team-level kills/deaths/assists from the overview table.

    The .overview-table has 4 rows: 1 header + 3 data (Kills, Deaths, Assists).
    Team names come from header row img.team-logo[alt].
    """
    ov_table = soup.select_one(".overview-table")
    if not ov_table:
        logger.warning("No .overview-table found")
        return []

    # Extract team names from header row
    header_row = ov_table.select_one("tr")
    if not header_row:
        logger.warning("No header row in .overview-table")
        return []

    t1_img = header_row.select_one("th.team1-column img.team-logo")
    t2_img = header_row.select_one("th.team2-column img.team-logo")

    team1_name = t1_img["alt"] if t1_img and t1_img.get("alt") else "Team 1"
    team2_name = t2_img["alt"] if t2_img and t2_img.get("alt") else "Team 2"

    # Extract data rows by label
    stats: dict[str, tuple[int, int]] = {}
    for row in ov_table.select("tr"):
        label_el = row.select_one(".name-column")
        if not label_el:
            continue
        label = label_el.get_text(strip=True)
        if not label:
            continue

        t1_el = row.select_one(".team1-column")
        t2_el = row.select_one(".team2-column")

        try:
            t1_val = int(t1_el.get_text(strip=True)) if t1_el else 0
        except ValueError:
            t1_val = 0
        try:
            t2_val = int(t2_el.get_text(strip=True)) if t2_el else 0
        except ValueError:
            t2_val = 0

        stats[label] = (t1_val, t2_val)

    kills = stats.get("Kills", (0, 0))
    deaths = stats.get("Deaths", (0, 0))
    assists = stats.get("Assists", (0, 0))

    return [
        TeamOverview(
            team_name=team1_name,
            total_kills=kills[0],
            total_deaths=deaths[0],
            total_assists=assists[0],
        ),
        TeamOverview(
            team_name=team2_name,
            total_kills=kills[1],
            total_deaths=deaths[1],
            total_assists=assists[1],
        ),
    ]
