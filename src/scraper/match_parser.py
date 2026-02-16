"""Match overview page parser for HLTV match detail pages.

Provides:
- parse_match_overview: pure function extracting match data from overview HTML
- MatchOverview, MapResult, VetoStep: structured return types

All selectors verified against 9 real HTML samples in Phase 3 recon.
"""

import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


@dataclass
class VetoStep:
    """A single step in the map veto sequence."""

    step_number: int
    team_name: str | None  # None for "left over"
    action: str  # "removed", "picked", "left_over"
    map_name: str


@dataclass
class MapResult:
    """Per-map result data from a match overview."""

    map_number: int  # 1-based
    map_name: str
    mapstatsid: int | None  # None for forfeit/unplayed maps
    team1_rounds: int | None
    team2_rounds: int | None
    team1_ct_rounds: int | None  # Regulation-only CT rounds
    team1_t_rounds: int | None  # Regulation-only T rounds
    team2_ct_rounds: int | None
    team2_t_rounds: int | None
    is_unplayed: bool
    is_forfeit_map: bool


@dataclass
class MatchOverview:
    """Complete parsed data from an HLTV match overview page."""

    match_id: int
    team1_name: str
    team2_name: str
    team1_id: int
    team2_id: int
    team1_score: int | None  # Raw .won/.lost value. None on full forfeit.
    team2_score: int | None
    best_of: int  # 1, 3, or 5
    is_lan: int  # 0 or 1
    date_unix_ms: int
    event_id: int
    event_name: str
    maps: list[MapResult]
    vetoes: list[VetoStep] | None  # None if unparseable or missing
    is_forfeit: bool  # True if any map has map_name == "Default"


def parse_match_overview(html: str, match_id: int) -> MatchOverview:
    """Parse an HLTV match overview page into structured data.

    Pure function: HTML string in, MatchOverview out. No side effects.

    Args:
        html: Raw HTML string of a match overview page.
        match_id: HLTV match ID (for inclusion in result).

    Returns:
        MatchOverview with all extracted fields.

    Raises:
        ValueError: If required fields (team names, IDs, date, event) are missing.
    """
    soup = BeautifulSoup(html, "lxml")

    metadata = _extract_match_metadata(soup, match_id)
    maps = _extract_maps(soup)
    vetoes = _extract_vetoes(soup)
    is_forfeit = any(m.is_forfeit_map for m in maps)

    return MatchOverview(
        match_id=match_id,
        team1_name=metadata["team1_name"],
        team2_name=metadata["team2_name"],
        team1_id=metadata["team1_id"],
        team2_id=metadata["team2_id"],
        team1_score=metadata["team1_score"],
        team2_score=metadata["team2_score"],
        best_of=metadata["best_of"],
        is_lan=metadata["is_lan"],
        date_unix_ms=metadata["date_unix_ms"],
        event_id=metadata["event_id"],
        event_name=metadata["event_name"],
        maps=maps,
        vetoes=vetoes,
        is_forfeit=is_forfeit,
    )


def _extract_team_score(soup: BeautifulSoup, gradient_class: str) -> int | None:
    """Extract team score from .won or .lost element within a team gradient.

    Returns None if neither .won nor .lost exists (full forfeit).
    """
    won_el = soup.select_one(f".{gradient_class} .won")
    if won_el:
        return int(won_el.text.strip())

    lost_el = soup.select_one(f".{gradient_class} .lost")
    if lost_el:
        return int(lost_el.text.strip())

    return None


def _extract_match_metadata(soup: BeautifulSoup, match_id: int) -> dict:
    """Extract match-level metadata from the overview page."""
    # Team names (required)
    t1_name_el = soup.select_one(".team1-gradient .teamName")
    t2_name_el = soup.select_one(".team2-gradient .teamName")
    if not t1_name_el or not t2_name_el:
        raise ValueError(
            f"Match {match_id}: missing team name elements "
            f"(team1={t1_name_el}, team2={t2_name_el})"
        )
    team1_name = t1_name_el.text.strip()
    team2_name = t2_name_el.text.strip()

    # Team IDs from href (required)
    t1_link = soup.select_one('.team1-gradient a[href*="/team/"]')
    t2_link = soup.select_one('.team2-gradient a[href*="/team/"]')
    if not t1_link or not t2_link:
        raise ValueError(
            f"Match {match_id}: missing team link elements "
            f"(team1={t1_link}, team2={t2_link})"
        )
    t1_m = re.search(r"/team/(\d+)/", t1_link["href"])
    t2_m = re.search(r"/team/(\d+)/", t2_link["href"])
    if not t1_m or not t2_m:
        raise ValueError(
            f"Match {match_id}: could not parse team IDs from hrefs "
            f"(team1={t1_link['href']}, team2={t2_link['href']})"
        )
    team1_id = int(t1_m.group(1))
    team2_id = int(t2_m.group(1))

    # Scores (optional -- absent on full forfeit)
    team1_score = _extract_team_score(soup, "team1-gradient")
    team2_score = _extract_team_score(soup, "team2-gradient")

    # Date (required)
    date_el = soup.select_one(".timeAndEvent .date[data-unix]")
    if not date_el:
        raise ValueError(f"Match {match_id}: missing date element")
    date_unix_ms = int(date_el["data-unix"])

    # Event (required)
    event_a = soup.select_one('.timeAndEvent .event a[href*="/events/"]')
    if not event_a:
        raise ValueError(f"Match {match_id}: missing event link element")
    event_name = event_a.text.strip()
    event_m = re.search(r"/events/(\d+)/", event_a["href"])
    if not event_m:
        raise ValueError(
            f"Match {match_id}: could not parse event ID from href "
            f"({event_a['href']})"
        )
    event_id = int(event_m.group(1))

    # Format: "Best of N (LAN|Online)"
    fmt_el = soup.select_one(".padding.preformatted-text")
    best_of = 1
    is_lan = 0
    if fmt_el:
        fmt_text = fmt_el.text.strip()
        bo_match = re.search(r"Best of (\d+)", fmt_text)
        if bo_match:
            best_of = int(bo_match.group(1))
        else:
            logger.warning("Match %d: could not parse best_of from format text", match_id)

        lan_match = re.search(r"\((LAN|Online)\)", fmt_text)
        if lan_match:
            is_lan = 1 if lan_match.group(1) == "LAN" else 0
        else:
            logger.warning("Match %d: could not parse LAN/Online from format text", match_id)
    else:
        logger.warning("Match %d: no format text element found", match_id)

    return {
        "team1_name": team1_name,
        "team2_name": team2_name,
        "team1_id": team1_id,
        "team2_id": team2_id,
        "team1_score": team1_score,
        "team2_score": team2_score,
        "date_unix_ms": date_unix_ms,
        "event_name": event_name,
        "event_id": event_id,
        "best_of": best_of,
        "is_lan": is_lan,
    }


def _parse_half_scores(hs_el: Tag) -> dict:
    """Parse half-score spans into structured CT/T round breakdowns.

    Returns dict with keys: team1_ct, team1_t, team2_ct, team2_t.
    All values are regulation-only (overtime spans lack ct/t classes).
    """
    spans = hs_el.select("span")

    # Extract numeric values with their side class
    scored_values: list[tuple[int, str | None]] = []
    for s in spans:
        text = s.text.strip()
        if not text or text in ("(", ")", ";", ":", ""):
            continue
        try:
            val = int(text)
        except ValueError:
            continue
        classes = s.get("class", [])
        side: str | None = None
        if "ct" in classes:
            side = "ct"
        elif "t" in classes:
            side = "t"
        scored_values.append((val, side))

    result: dict[str, int | None] = {
        "team1_ct": None,
        "team1_t": None,
        "team2_ct": None,
        "team2_t": None,
    }

    if len(scored_values) < 4:
        return result

    # Regulation halves: first 4 values with ct/t classes
    # Layout: pos 0,1 = half1 (team1_half1, team2_half1)
    #         pos 2,3 = half2 (team1_half2, team2_half2)
    h1_t1_val, h1_t1_side = scored_values[0]
    h1_t2_val, _h1_t2_side = scored_values[1]
    h2_t1_val, _h2_t1_side = scored_values[2]
    h2_t2_val, _h2_t2_side = scored_values[3]

    if h1_t1_side == "ct":
        # Team1 started CT side in half 1
        result["team1_ct"] = h1_t1_val
        result["team1_t"] = h2_t1_val
        result["team2_t"] = h1_t2_val
        result["team2_ct"] = h2_t2_val
    elif h1_t1_side == "t":
        # Team1 started T side in half 1
        result["team1_t"] = h1_t1_val
        result["team1_ct"] = h2_t1_val
        result["team2_ct"] = h1_t2_val
        result["team2_t"] = h2_t2_val
    else:
        logger.warning("Half-score span 0 has no ct/t class; cannot determine sides")

    return result


def _extract_maps(soup: BeautifulSoup) -> list[MapResult]:
    """Extract per-map data from map holders."""
    maps: list[MapResult] = []

    for i, mh in enumerate(soup.select(".mapholder"), start=1):
        mapname_el = mh.select_one(".mapname")
        map_name = mapname_el.text.strip() if mapname_el else "Unknown"

        # Unplayed detection: .optional child div inside .mapholder
        is_unplayed = mh.select_one(".optional") is not None

        # Forfeit map detection
        is_forfeit_map = map_name == "Default"

        # Scores
        team1_rounds: int | None = None
        team2_rounds: int | None = None
        if not is_unplayed:
            score_left = mh.select_one(".results-left .results-team-score")
            score_right = mh.select_one(".results-right .results-team-score")
            if score_left:
                text = score_left.text.strip()
                if text != "-":
                    try:
                        team1_rounds = int(text)
                    except ValueError:
                        pass
            if score_right:
                text = score_right.text.strip()
                if text != "-":
                    try:
                        team2_rounds = int(text)
                    except ValueError:
                        pass

        # MapStatsID
        mapstatsid: int | None = None
        stats_link = mh.select_one("a.results-stats[href]")
        if stats_link:
            m = re.search(r"/mapstatsid/(\d+)/", stats_link["href"])
            if m:
                mapstatsid = int(m.group(1))

        # Half scores (CT/T breakdown) -- only for played, non-forfeit maps
        team1_ct: int | None = None
        team1_t: int | None = None
        team2_ct: int | None = None
        team2_t: int | None = None
        if not is_unplayed and not is_forfeit_map:
            hs_el = mh.select_one(".results-center-half-score")
            if hs_el:
                halves = _parse_half_scores(hs_el)
                team1_ct = halves["team1_ct"]
                team1_t = halves["team1_t"]
                team2_ct = halves["team2_ct"]
                team2_t = halves["team2_t"]

        maps.append(
            MapResult(
                map_number=i,
                map_name=map_name,
                mapstatsid=mapstatsid,
                team1_rounds=team1_rounds,
                team2_rounds=team2_rounds,
                team1_ct_rounds=team1_ct,
                team1_t_rounds=team1_t,
                team2_ct_rounds=team2_ct,
                team2_t_rounds=team2_t,
                is_unplayed=is_unplayed,
                is_forfeit_map=is_forfeit_map,
            )
        )

    return maps


def _extract_vetoes(soup: BeautifulSoup) -> list[VetoStep] | None:
    """Extract veto sequence from the second veto box.

    Index [0] is format/stage info. Index [1] is the actual veto sequence.
    Returns None if fewer than 2 veto boxes or no parseable veto lines.
    """
    veto_boxes = soup.select(".veto-box")
    if len(veto_boxes) < 2:
        logger.warning("Fewer than 2 veto boxes found; cannot extract vetoes")
        return None

    veto_div = veto_boxes[1]
    lines = veto_div.select(".padding > div")
    if not lines:
        logger.warning("No veto lines found in second veto box")
        return None

    vetoes: list[VetoStep] = []
    for line in lines:
        text = line.text.strip()

        m_remove = re.match(r"(\d+)\. (.+) removed (.+)", text)
        m_pick = re.match(r"(\d+)\. (.+) picked (.+)", text)
        m_left = re.match(r"(\d+)\. (.+) was left over", text)

        if m_remove:
            vetoes.append(
                VetoStep(
                    step_number=int(m_remove.group(1)),
                    team_name=m_remove.group(2).strip(),
                    action="removed",
                    map_name=m_remove.group(3).strip(),
                )
            )
        elif m_pick:
            vetoes.append(
                VetoStep(
                    step_number=int(m_pick.group(1)),
                    team_name=m_pick.group(2).strip(),
                    action="picked",
                    map_name=m_pick.group(3).strip(),
                )
            )
        elif m_left:
            vetoes.append(
                VetoStep(
                    step_number=int(m_left.group(1)),
                    team_name=None,
                    action="left_over",
                    map_name=m_left.group(2).strip(),
                )
            )

    return vetoes if vetoes else None
