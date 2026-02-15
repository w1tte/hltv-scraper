"""Match overview extraction orchestrator.

Coordinates fetching, storing, parsing, and persisting match overview data.
Pulls pending matches from the scrape_queue, fetches their overview pages,
stores raw HTML, parses with parse_match_overview(), and persists all
extracted data (match, maps, vetoes, players) to the database.
"""

import logging
from datetime import datetime, timezone

from scraper.match_parser import parse_match_overview

logger = logging.getLogger(__name__)

PARSER_VERSION = "match_overview_v1"


async def run_match_overview(
    client,              # HLTVClient
    match_repo,          # MatchRepository
    discovery_repo,      # DiscoveryRepository
    storage,             # HtmlStorage
    config,              # ScraperConfig
) -> dict:
    """Fetch, store, parse, and persist match overview pages.

    Implements a fetch-first batch strategy: fetch all pages in the batch
    first, then parse and persist.  On any fetch failure mid-batch, the
    entire batch is discarded (queue entries remain 'pending' for retry).
    Parse/persist failures are handled per-match (mark individual matches
    as 'failed' and continue).

    Args:
        client: HLTVClient instance (must be started).
        match_repo: MatchRepository instance.
        discovery_repo: DiscoveryRepository instance.
        storage: HtmlStorage instance.
        config: ScraperConfig instance.

    Returns:
        Dict with stats: batch_size, fetched, parsed, failed, fetch_errors.
    """
    stats = {
        "batch_size": 0,
        "fetched": 0,
        "parsed": 0,
        "failed": 0,
        "fetch_errors": 0,
    }

    # 1. Get pending matches
    pending = discovery_repo.get_pending_matches(limit=config.overview_batch_size)
    stats["batch_size"] = len(pending)

    if not pending:
        logger.info("No pending matches to process")
        return stats

    logger.info("Processing batch of %d pending matches", len(pending))

    # 2. Fetch phase -- fetch all pages, discard batch on any failure
    fetched_entries: list[dict] = []
    for entry in pending:
        url = config.base_url + entry["url"]
        try:
            html = await client.fetch(url)
            storage.save(html, match_id=entry["match_id"], page_type="overview")
            fetched_entries.append(entry)
            logger.debug("Fetched match %d", entry["match_id"])
        except Exception as exc:
            logger.error(
                "Fetch failed for match %d: %s. Discarding entire batch.",
                entry["match_id"],
                exc,
            )
            stats["fetch_errors"] += 1
            return stats

    stats["fetched"] = len(fetched_entries)

    # 3. Parse + persist phase -- per-match failure handling
    for entry in fetched_entries:
        match_id = entry["match_id"]
        try:
            html = storage.load(match_id=match_id, page_type="overview")
            result = parse_match_overview(html, match_id)

            now = datetime.now(timezone.utc).isoformat()
            source_url = config.base_url + entry["url"]

            # Convert date from unix ms to ISO 8601
            date_iso = datetime.fromtimestamp(
                result.date_unix_ms / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")

            # Build match data dict
            match_data = {
                "match_id": match_id,
                "date": date_iso,
                "event_id": result.event_id,
                "event_name": result.event_name,
                "team1_id": result.team1_id,
                "team1_name": result.team1_name,
                "team2_id": result.team2_id,
                "team2_name": result.team2_name,
                "team1_score": result.team1_score,
                "team2_score": result.team2_score,
                "best_of": result.best_of,
                "is_lan": result.is_lan,
                "match_url": entry["url"],
                "scraped_at": now,
                "source_url": source_url,
                "parser_version": PARSER_VERSION,
            }

            # Build maps data
            maps_data = [
                {
                    "match_id": match_id,
                    "map_number": m.map_number,
                    "mapstatsid": m.mapstatsid,
                    "map_name": m.map_name,
                    "team1_rounds": m.team1_rounds,
                    "team2_rounds": m.team2_rounds,
                    "team1_ct_rounds": m.team1_ct_rounds,
                    "team1_t_rounds": m.team1_t_rounds,
                    "team2_ct_rounds": m.team2_ct_rounds,
                    "team2_t_rounds": m.team2_t_rounds,
                    "scraped_at": now,
                    "source_url": source_url,
                    "parser_version": PARSER_VERSION,
                }
                for m in result.maps
            ]

            # Build vetoes data
            vetoes_data = []
            if result.vetoes:
                vetoes_data = [
                    {
                        "match_id": match_id,
                        "step_number": v.step_number,
                        "team_name": v.team_name,
                        "action": v.action,
                        "map_name": v.map_name,
                        "scraped_at": now,
                        "source_url": source_url,
                        "parser_version": PARSER_VERSION,
                    }
                    for v in result.vetoes
                ]

            # Build players data
            players_data = [
                {
                    "match_id": match_id,
                    "player_id": p.player_id,
                    "player_name": p.player_name,
                    "team_id": p.team_id,
                    "team_num": p.team_num,
                    "scraped_at": now,
                    "source_url": source_url,
                    "parser_version": PARSER_VERSION,
                }
                for p in result.players
            ]

            # Persist atomically
            match_repo.upsert_match_overview(
                match_data, maps_data, vetoes_data, players_data
            )
            discovery_repo.update_status(match_id, "scraped")
            stats["parsed"] += 1
            logger.info("Parsed and persisted match %d", match_id)

        except Exception as exc:
            logger.error("Parse/persist failed for match %d: %s", match_id, exc)
            discovery_repo.update_status(match_id, "failed")
            stats["failed"] += 1

    logger.info(
        "Batch complete: %d fetched, %d parsed, %d failed",
        stats["fetched"],
        stats["parsed"],
        stats["failed"],
    )
    return stats
