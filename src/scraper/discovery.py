"""Match discovery from HLTV results listing pages.

Provides:
- DiscoveredMatch: dataclass for a single discovered match entry
- parse_results_page: pure function extracting matches from results HTML
- run_discovery: async orchestrator for paginated discovery loop
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

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


async def run_discovery(
    clients,          # list[HLTVClient] -- uses clients[0] for sequential fetching
    repo,             # DiscoveryRepository
    storage,          # HtmlStorage
    config,           # ScraperConfig
    incremental: bool = True,
    shutdown=None,    # Any object with .is_set property (duck typing)
) -> dict:
    """Paginate HLTV results pages and populate the scrape_queue.

    For each offset from config.start_offset to config.max_offset (step 100):
    1. Check shutdown flag
    2. Skip if offset already in discovery_progress (resume support)
    3. Fetch the results page via clients[0].fetch()
    4. Parse entries via parse_results_page()
    5. In incremental mode, check for early termination (all matches known)
    6. Persist batch + mark offset complete via repo.persist_page()

    Args:
        clients: List of HLTVClient instances (uses first one).
        repo: DiscoveryRepository instance.
        storage: HtmlStorage instance.
        config: ScraperConfig instance.
        incremental: If True (default), stop when an entire page of
            matches is already in the DB. Pass False for full re-discovery.
        shutdown: Optional object with an ``is_set`` property. When set,
            discovery stops at the next loop iteration boundary.

    Returns:
        Dict with stats: pages_fetched, pages_skipped, matches_found,
        new_matches, errors.
    """
    completed = repo.get_completed_offsets()
    stats = {
        "pages_fetched": 0,
        "pages_skipped": 0,
        "matches_found": 0,
        "new_matches": 0,
        "errors": 0,
    }

    prev_page_count = config.results_per_page  # assume full until proven otherwise
    for offset in range(config.start_offset, config.max_offset, config.results_per_page):
        # Check shutdown flag
        if shutdown is not None and shutdown.is_set:
            logger.info("Shutdown requested, stopping discovery at offset %d", offset)
            break

        if offset in completed:
            stats["pages_skipped"] += 1
            logger.debug("Skipping offset %d (already complete)", offset)
            continue

        try:
            # 1. Fetch — rotate across all clients for resilience
            url = f"{config.base_url}/results?offset={offset}&gameType={config.game_type}"
            client_index = (stats["pages_fetched"] + stats["errors"]) % len(clients)
            html = await clients[client_index].fetch(
                url,
                ready_selector=".result-con",  # wait for JS-rendered match list
            )

            # 2. Parse
            matches = parse_results_page(html)

            # 4. Validate entry count
            if len(matches) == 0:
                # Check if previous page was a short page (end of results)
                if stats["pages_fetched"] > 0 and prev_page_count < config.results_per_page:
                    logger.info(
                        "Offset %d: 0 entries (previous page had %d < %d). "
                        "End of results reached.",
                        offset, prev_page_count, config.results_per_page,
                    )
                    break

                # Genuinely unexpected — dump HTML for debugging
                from pathlib import Path
                debug_path = Path(config.data_dir) / f"debug_offset_{offset}.html"
                debug_path.write_text(html, encoding="utf-8")
                logger.error(
                    "Offset %d: 0 entries found (possible Cloudflare issue). "
                    "HTML dumped to %s. Stopping pagination.",
                    offset, debug_path,
                )
                stats["errors"] += 1
                raise RuntimeError(
                    f"Zero entries found at offset {offset}. "
                    "Likely Cloudflare interstitial or page structure change."
                )

            if len(matches) != config.results_per_page:
                logger.warning(
                    "Offset %d: expected %d entries, got %d",
                    offset, config.results_per_page, len(matches),
                )

            # 5. Check incremental early termination BEFORE persisting
            match_ids = [m.match_id for m in matches]
            if incremental:
                new_count = repo.count_new_matches(match_ids)
                stats["new_matches"] += new_count
                if new_count == 0:
                    logger.info(
                        "All %d matches on offset %d already known. "
                        "Stopping incremental discovery.",
                        len(matches), offset,
                    )
                    break

            # 6. Persist batch + mark offset complete (atomic)
            now = datetime.now(timezone.utc).isoformat()
            batch = [
                {
                    "match_id": m.match_id,
                    "url": m.url,
                    "offset": offset,
                    "discovered_at": now,
                    "is_forfeit": int(m.is_forfeit),
                }
                for m in matches
            ]
            repo.persist_page(batch, offset)

            prev_page_count = len(matches)
            stats["pages_fetched"] += 1
            stats["matches_found"] += len(matches)
            logger.info(
                "Offset %d: %d matches (%d new, total: %d)",
                offset, len(matches),
                new_count if incremental else len(matches),
                stats["matches_found"],
            )

        except RuntimeError:
            raise  # Re-raise the zero-entries error
        except Exception as exc:
            logger.error("Offset %d failed: %s", offset, exc)
            stats["errors"] += 1
            raise  # Let caller decide retry policy

    # In non-incremental mode, new_matches equals matches_found
    if not incremental:
        stats["new_matches"] = stats["matches_found"]

    logger.info(
        "Discovery complete: %d pages fetched, %d skipped, "
        "%d matches found (%d new)",
        stats["pages_fetched"], stats["pages_skipped"],
        stats["matches_found"], stats["new_matches"],
    )
    return stats
