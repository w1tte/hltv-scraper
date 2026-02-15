"""Match discovery from HLTV results listing pages.

Provides:
- DiscoveredMatch: dataclass for a single discovered match entry
- parse_results_page: pure function extracting matches from results HTML
"""

import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredMatch:
    """A match entry extracted from an HLTV results listing page."""

    match_id: int
    url: str  # Relative URL: /matches/2389953/furia-vs-b8-...
    is_forfeit: bool  # True when map-text == "def"
    timestamp_ms: int  # Unix milliseconds from data-zonedgrouping-entry-unix


def parse_results_page(html: str) -> list[DiscoveredMatch]:
    """Parse an HLTV results listing page and return discovered matches.

    Uses the data-zonedgrouping-entry-unix attribute selector to select
    only regular entries. This automatically skips the big-results section
    on page 1 (those entries lack this attribute).

    Args:
        html: Raw HTML string of a results listing page.

    Returns:
        List of DiscoveredMatch objects. Typically 100 per page.
        Returns empty list if no entries found (e.g., non-results HTML).
    """
    soup = BeautifulSoup(html, "lxml")
    entries = soup.select(".result-con[data-zonedgrouping-entry-unix]")

    results: list[DiscoveredMatch] = []
    for entry in entries:
        # Match URL and ID
        link = entry.select_one("a.a-reset")
        if link is None or not link.get("href"):
            logger.warning("Skipping entry: no a.a-reset link found")
            continue

        href = link["href"]
        m = re.search(r"/matches/(\d+)/", href)
        if not m:
            logger.warning("Skipping entry: no match ID in href %r", href)
            continue

        match_id = int(m.group(1))

        # Forfeit flag
        map_text_el = entry.select_one(".map-text")
        map_text = map_text_el.text.strip() if map_text_el else ""
        is_forfeit = map_text == "def"

        # Timestamp
        timestamp_ms = int(entry["data-zonedgrouping-entry-unix"])

        results.append(
            DiscoveredMatch(
                match_id=match_id,
                url=href,
                is_forfeit=is_forfeit,
                timestamp_ms=timestamp_ms,
            )
        )

    return results
