"""Map stats extraction orchestrator.

Coordinates fetching, storing, parsing, and persisting per-map
scoreboard and round history data.  Pulls pending maps from the
database (maps with a mapstatsid but no player_stats rows yet),
fetches their map stats pages, stores raw HTML, parses with
parse_map_stats(), and persists player_stats + round_history to the DB.
"""

import logging
from datetime import datetime, timezone

from scraper.map_stats_parser import parse_map_stats
from scraper.models import PlayerStatsModel, RoundHistoryModel
from scraper.validation import check_player_count, validate_batch

logger = logging.getLogger(__name__)

PARSER_VERSION = "map_stats_v1"
MAP_STATS_URL_TEMPLATE = "/stats/matches/mapstatsid/{mapstatsid}/x"


async def run_map_stats(
    client,         # HLTVClient
    match_repo,     # MatchRepository
    storage,        # HtmlStorage
    config,         # ScraperConfig
) -> dict:
    """Fetch, store, parse, and persist map stats pages.

    Implements a fetch-first batch strategy: fetch all pages in the batch
    first, then parse and persist.  On any fetch failure mid-batch, the
    entire batch is discarded (map entries remain pending for retry).
    Parse/persist failures are handled per-map (failed maps are logged
    and others continue).

    Args:
        client: HLTVClient instance (must be started).
        match_repo: MatchRepository instance.
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

    # 1. Get pending maps
    pending = match_repo.get_pending_map_stats(limit=config.map_stats_batch_size)
    stats["batch_size"] = len(pending)

    if not pending:
        logger.info("No pending maps to process")
        return stats

    logger.info("Processing batch of %d pending maps", len(pending))

    # 2. Fetch phase -- fetch all pages, discard batch on any failure
    fetched_entries: list[dict] = []
    for entry in pending:
        url = config.base_url + MAP_STATS_URL_TEMPLATE.format(
            mapstatsid=entry["mapstatsid"]
        )
        try:
            html = await client.fetch(url)
            storage.save(
                html,
                match_id=entry["match_id"],
                page_type="map_stats",
                mapstatsid=entry["mapstatsid"],
            )
            fetched_entries.append(entry)
            logger.debug("Fetched mapstatsid %d", entry["mapstatsid"])
        except Exception as exc:
            logger.error(
                "Fetch failed for mapstatsid %d: %s. Discarding entire batch.",
                entry["mapstatsid"],
                exc,
            )
            stats["fetch_errors"] += 1
            return stats

    stats["fetched"] = len(fetched_entries)

    # 3. Parse + persist phase -- per-map failure handling
    for entry in fetched_entries:
        mapstatsid = entry["mapstatsid"]
        match_id = entry["match_id"]
        map_number = entry["map_number"]
        try:
            html = storage.load(
                match_id=match_id,
                page_type="map_stats",
                mapstatsid=mapstatsid,
            )
            result = parse_map_stats(html, mapstatsid)

            now = datetime.now(timezone.utc).isoformat()
            source_url = config.base_url + MAP_STATS_URL_TEMPLATE.format(
                mapstatsid=mapstatsid
            )

            # Build player_stats dicts for UPSERT
            stats_data = []
            for ps in result.players:
                stats_data.append({
                    "match_id": match_id,
                    "map_number": map_number,
                    "player_id": ps.player_id,
                    "player_name": ps.player_name,
                    "team_id": ps.team_id,
                    "kills": ps.kills,
                    "deaths": ps.deaths,
                    "assists": ps.assists,
                    "flash_assists": ps.flash_assists,
                    "hs_kills": ps.hs_kills,
                    "kd_diff": ps.kd_diff,
                    "adr": ps.adr,
                    "kast": ps.kast,
                    "fk_diff": ps.fk_diff,
                    "rating_2": ps.rating if ps.rating_version == "2.0" else None,
                    "rating_3": ps.rating if ps.rating_version == "3.0" else None,
                    "kpr": None,       # Phase 7 -- performance page
                    "dpr": None,       # Phase 7 -- performance page
                    "impact": None,    # Phase 7 -- performance page
                    "opening_kills": ps.opening_kills,
                    "opening_deaths": ps.opening_deaths,
                    "multi_kills": ps.multi_kills,
                    "clutch_wins": ps.clutch_wins,
                    "traded_deaths": ps.traded_deaths,
                    "round_swing": ps.round_swing,
                    "mk_rating": None,  # Phase 7 -- performance page
                    "scraped_at": now,
                    "source_url": source_url,
                    "parser_version": PARSER_VERSION,
                })

            # Build round_history dicts for UPSERT
            rounds_data = []
            for ro in result.rounds:
                rounds_data.append({
                    "match_id": match_id,
                    "map_number": map_number,
                    "round_number": ro.round_number,
                    "winner_side": ro.winner_side,
                    "win_type": ro.win_type,
                    "winner_team_id": ro.winner_team_id,
                    "scraped_at": now,
                    "source_url": source_url,
                    "parser_version": PARSER_VERSION,
                })

            # --- Validate before persist ---
            ctx = {"match_id": match_id, "map_number": map_number}

            validated_stats, stats_q = validate_batch(
                stats_data, PlayerStatsModel, ctx, match_repo
            )
            validated_rounds, rounds_q = validate_batch(
                rounds_data, RoundHistoryModel, ctx, match_repo
            )

            if stats_q or rounds_q:
                logger.warning(
                    "mapstatsid %d: quarantined %d player_stats, %d rounds",
                    mapstatsid, stats_q, rounds_q,
                )

            if not validated_stats:
                logger.error(
                    "All player_stats quarantined for mapstatsid %d, skipping",
                    mapstatsid,
                )
                stats["failed"] += 1
                continue

            # Batch-level check: player count
            player_warnings = check_player_count(
                validated_stats, match_id, map_number
            )
            for w in player_warnings:
                logger.warning(w)

            # Persist atomically
            match_repo.upsert_map_stats_complete(
                validated_stats, validated_rounds
            )
            stats["parsed"] += 1
            logger.info(
                "Parsed and persisted mapstatsid %d (match %d, map %d)",
                mapstatsid, match_id, map_number,
            )

        except Exception as exc:
            logger.error(
                "Parse/persist failed for mapstatsid %d: %s", mapstatsid, exc
            )
            stats["failed"] += 1

    logger.info(
        "Batch complete: %d fetched, %d parsed, %d failed",
        stats["fetched"],
        stats["parsed"],
        stats["failed"],
    )
    return stats
