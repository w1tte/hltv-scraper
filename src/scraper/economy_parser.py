"""Economy page parser for HLTV map economy pages.

Provides:
- parse_economy: pure function extracting per-round equipment values from economy HTML
- EconomyData, RoundEconomy: structured return types

All selectors verified against 12 real HTML samples in Phase 3 recon.
"""

import json
import logging
from dataclasses import dataclass

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class RoundEconomy:
    """Per-round per-team economy data from economy page."""

    round_number: int
    team_name: str
    equipment_value: int
    buy_type: str  # "full_eco", "semi_eco", "semi_buy", "full_buy"
    won_round: bool
    side: str | None  # "CT" or "T" (from anchor image); None if not determinable


@dataclass
class EconomyData:
    """Complete parsed data from an HLTV economy page."""

    mapstatsid: int
    team1_name: str
    team2_name: str
    rounds: list[RoundEconomy]
    round_count: int  # Number of rounds with economy data (may be < total score for MR12 OT)


def parse_economy(html: str, mapstatsid: int) -> EconomyData:
    """Parse an HLTV economy page into structured data.

    Pure function: HTML string in, EconomyData out. No side effects.

    Args:
        html: Raw HTML string of an economy page.
        mapstatsid: HLTV mapstatsid (for inclusion in result).

    Returns:
        EconomyData with all extracted fields.

    Raises:
        ValueError: If no FusionChart element found on the page.
    """
    soup = BeautifulSoup(html, "lxml")

    ds, round_labels = _parse_fusionchart_economy(soup, mapstatsid)

    if len(ds["dataset"]) < 2:
        raise ValueError(
            f"Economy {mapstatsid}: expected 2 datasets in FusionChart, "
            f"found {len(ds['dataset'])}"
        )

    team1_name = ds["dataset"][0]["seriesname"]
    team2_name = ds["dataset"][1]["seriesname"]

    # Build side map from anchor images (winner's anchor tells us both teams' sides)
    round_sides = _build_round_sides(ds, team1_name, team2_name, round_labels)

    rounds: list[RoundEconomy] = []

    for dataset in ds["dataset"]:
        team_name = dataset["seriesname"]
        for i, point in enumerate(dataset["data"]):
            round_num = int(round_labels[i])
            equip_val = int(point["value"])
            anchor = point.get("anchorImageUrl")

            won = anchor is not None
            side = round_sides.get(round_num, {}).get(team_name)

            buy_type = _classify_buy_type(equip_val)
            rounds.append(
                RoundEconomy(
                    round_number=round_num,
                    team_name=team_name,
                    equipment_value=equip_val,
                    buy_type=buy_type,
                    won_round=won,
                    side=side,
                )
            )

    return EconomyData(
        mapstatsid=mapstatsid,
        team1_name=team1_name,
        team2_name=team2_name,
        rounds=rounds,
        round_count=len(round_labels),
    )


def _parse_fusionchart_economy(
    soup: BeautifulSoup, mapstatsid: int
) -> tuple[dict, list[str]]:
    """Extract FusionChart dataSource and round labels from economy page.

    Returns:
        Tuple of (dataSource dict, list of round label strings).

    Raises:
        ValueError: If no FusionChart element found.
    """
    fc_el = soup.select_one("worker-ignore.graph[data-fusionchart-config]")
    if not fc_el:
        raise ValueError(
            f"Economy {mapstatsid}: no worker-ignore.graph[data-fusionchart-config] element found"
        )

    config = json.loads(fc_el["data-fusionchart-config"])
    ds = config["dataSource"]

    if "categories" not in ds:
        raise ValueError(
            f"Economy {mapstatsid}: FusionChart missing 'categories' key "
            f"(wrong page type served)"
        )

    round_labels = [cat["label"] for cat in ds["categories"][0]["category"]]

    return ds, round_labels


def _build_round_sides(
    ds: dict,
    team1_name: str,
    team2_name: str,
    round_labels: list[str],
) -> dict[int, dict[str, str]]:
    """Build a mapping of round_number -> {team_name: side} from anchor images.

    For each round, exactly one team has an anchorImageUrl (the winner).
    The winner's anchor tells us the winner's side. The loser's side is the opposite.

    Returns:
        Dict mapping round_number to {team_name: "CT" or "T"}.
    """
    round_sides: dict[int, dict[str, str]] = {}

    for dataset in ds["dataset"]:
        team_name = dataset["seriesname"]
        other_team = team2_name if team_name == team1_name else team1_name

        for i, point in enumerate(dataset["data"]):
            round_num = int(round_labels[i])
            anchor = point.get("anchorImageUrl")

            if anchor is None:
                continue

            # This team won -- determine their side from the anchor
            winner_side: str | None = None
            if "ctRoundWon" in anchor:
                winner_side = "CT"
            elif "tRoundWon" in anchor:
                winner_side = "T"

            if winner_side is None:
                logger.warning(
                    "Unexpected anchor image URL in round %d: %s",
                    round_num,
                    anchor,
                )
                continue

            loser_side = "T" if winner_side == "CT" else "CT"

            if round_num not in round_sides:
                round_sides[round_num] = {}

            round_sides[round_num][team_name] = winner_side
            round_sides[round_num][other_team] = loser_side

    return round_sides


def _classify_buy_type(value: int) -> str:
    """Classify equipment value into buy type using HLTV thresholds.

    Thresholds derived from HLTV's own trendlines:
    - Full eco: < $5,000
    - Semi-eco: $5,000 - $9,999
    - Semi-buy: $10,000 - $19,999
    - Full buy: >= $20,000
    """
    if value >= 20000:
        return "full_buy"
    elif value >= 10000:
        return "semi_buy"
    elif value >= 5000:
        return "semi_eco"
    else:
        return "full_eco"
