"""Performance and economy extraction orchestrator.

Coordinates fetching, storing, parsing, and persisting performance
metrics, economy data, and kill matrix data for each pending map.
Fetches both performance and economy pages per map in a single batch,
parses with parse_performance() and parse_economy(), merges performance
data onto existing player_stats (preserving Phase 6 values), filters
economy rows to valid round_history entries, and persists atomically.
"""

import logging
from datetime import datetime, timezone

from scraper.economy_parser import parse_economy
from scraper.models import EconomyModel, KillMatrixModel, PlayerStatsModel
from scraper.performance_parser import parse_performance
from scraper.validation import check_economy_alignment, validate_batch

logger = logging.getLogger(__name__)

PARSER_VERSION = "perf_economy_v1"
PERF_URL_TEMPLATE = "/stats/matches/performance/mapstatsid/{mapstatsid}/x"
ECON_URL_TEMPLATE = "/stats/matches/economy/mapstatsid/{mapstatsid}/x"


async def run_performance_economy(
    client,         # HLTVClient
    match_repo,     # MatchRepository
    storage,        # HtmlStorage
    config,         # ScraperConfig
) -> dict:
    """Fetch, store, parse, and persist performance + economy pages.

    Implements a fetch-first batch strategy: fetch all pages (both perf
    and econ for each map) first, then parse and persist.  On any fetch
    failure mid-batch, the entire batch is discarded (map entries remain
    pending for retry).  Parse/persist failures are handled per-map
    (failed maps are logged and others continue).

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

    # 1. Get pending maps (Phase 6 complete, Phase 7 not yet run)
    pending = match_repo.get_pending_perf_economy(
        limit=config.perf_economy_batch_size
    )
    stats["batch_size"] = len(pending)

    if not pending:
        logger.info("No pending maps for performance/economy extraction")
        return stats

    logger.info(
        "Processing batch of %d pending maps for performance/economy",
        len(pending),
    )

    # 2. Fetch phase -- concurrent fetching with per-item failure handling
    #    Build interleaved URL list: [perf0, econ0, perf1, econ1, ...]
    all_urls = []
    for entry in pending:
        mapstatsid = entry["mapstatsid"]
        all_urls.append(config.base_url + PERF_URL_TEMPLATE.format(mapstatsid=mapstatsid))
        all_urls.append(config.base_url + ECON_URL_TEMPLATE.format(mapstatsid=mapstatsid))

    all_results = await client.fetch_many(all_urls)

    fetched_entries: list[dict] = []
    for i, entry in enumerate(pending):
        mapstatsid = entry["mapstatsid"]
        match_id = entry["match_id"]
        perf_result = all_results[i * 2]
        econ_result = all_results[i * 2 + 1]

        if isinstance(perf_result, Exception):
            logger.error(
                "Fetch failed for performance page mapstatsid %d: %s",
                mapstatsid, perf_result,
            )
            stats["fetch_errors"] += 1
            continue
        if isinstance(econ_result, Exception):
            logger.error(
                "Fetch failed for economy page mapstatsid %d: %s",
                mapstatsid, econ_result,
            )
            stats["fetch_errors"] += 1
            continue

        storage.save(
            perf_result,
            match_id=match_id,
            page_type="map_performance",
            mapstatsid=mapstatsid,
        )
        storage.save(
            econ_result,
            match_id=match_id,
            page_type="map_economy",
            mapstatsid=mapstatsid,
        )
        fetched_entries.append(entry)
        logger.debug("Fetched perf+econ for mapstatsid %d", mapstatsid)

    stats["fetched"] = len(fetched_entries)

    # 3. Parse + persist phase -- per-map failure handling
    for entry in fetched_entries:
        mapstatsid = entry["mapstatsid"]
        match_id = entry["match_id"]
        map_number = entry["map_number"]

        try:
            # Load stored HTML
            perf_html = storage.load(
                match_id=match_id,
                page_type="map_performance",
                mapstatsid=mapstatsid,
            )
            econ_html = storage.load(
                match_id=match_id,
                page_type="map_economy",
                mapstatsid=mapstatsid,
            )

            # Parse both pages
            perf_result = parse_performance(perf_html, mapstatsid)
            econ_result = parse_economy(econ_html, mapstatsid)

            now = datetime.now(timezone.utc).isoformat()
            perf_source_url = config.base_url + PERF_URL_TEMPLATE.format(
                mapstatsid=mapstatsid
            )
            econ_source_url = config.base_url + ECON_URL_TEMPLATE.format(
                mapstatsid=mapstatsid
            )

            # --- Build perf_stats dicts (read-merge to preserve Phase 6 data) ---
            existing_stats = match_repo.get_player_stats(match_id, map_number)
            existing_by_pid = {s["player_id"]: s for s in existing_stats}

            perf_stats = []
            for p in perf_result.players:
                base = existing_by_pid.get(p.player_id, {})
                perf_stats.append({
                    "match_id": match_id,
                    "map_number": map_number,
                    "player_id": p.player_id,
                    "player_name": base.get("player_name", p.player_name),
                    "team_id": base.get("team_id"),
                    "kills": base.get("kills"),
                    "deaths": base.get("deaths"),
                    "assists": base.get("assists"),
                    "flash_assists": base.get("flash_assists"),
                    "hs_kills": base.get("hs_kills"),
                    "kd_diff": base.get("kd_diff"),
                    "adr": base.get("adr"),
                    "kast": base.get("kast"),
                    "fk_diff": base.get("fk_diff"),
                    "rating": base.get("rating"),
                    # Phase 7 fields from performance parser
                    "kpr": p.kpr,
                    "dpr": p.dpr,
                    "mk_rating": p.mk_rating,
                    # Phase 6 fields preserved from existing row
                    "opening_kills": base.get("opening_kills"),
                    "opening_deaths": base.get("opening_deaths"),
                    "multi_kills": base.get("multi_kills"),
                    "clutch_wins": base.get("clutch_wins"),
                    "traded_deaths": base.get("traded_deaths"),
                    "round_swing": base.get("round_swing"),
                    "scraped_at": now,
                    "source_url": perf_source_url,
                    "parser_version": PARSER_VERSION,
                })

            # --- Resolve team_ids for economy data ---
            match_data = match_repo.get_match(match_id)

            team_name_to_id: dict[str, int | None] = {}
            if match_data:
                team_name_to_id[match_data["team1_name"]] = match_data["team1_id"]
                team_name_to_id[match_data["team2_name"]] = match_data["team2_id"]

            # Try FusionChart team names against match team names
            econ_team1_id = team_name_to_id.get(econ_result.team1_name)
            econ_team2_id = team_name_to_id.get(econ_result.team2_name)

            # If name matching fails for either team, use positional fallback
            if econ_team1_id is None or econ_team2_id is None:
                logger.warning(
                    "Economy team name mismatch for match %d: economy has '%s'/'%s', "
                    "match has '%s'/'%s'. Using positional fallback.",
                    match_id,
                    econ_result.team1_name,
                    econ_result.team2_name,
                    match_data.get("team1_name", "?") if match_data else "?",
                    match_data.get("team2_name", "?") if match_data else "?",
                )
                if match_data:
                    econ_team1_id = match_data["team1_id"]
                    econ_team2_id = match_data["team2_id"]

            econ_name_to_id = {
                econ_result.team1_name: econ_team1_id,
                econ_result.team2_name: econ_team2_id,
            }

            # --- Filter economy rows to valid round numbers (FK safety) ---
            valid_rounds = match_repo.get_valid_round_numbers(match_id, map_number)

            economy_data = []
            skipped_rounds = 0
            for r in econ_result.rounds:
                if r.round_number not in valid_rounds:
                    skipped_rounds += 1
                    continue
                team_id = econ_name_to_id.get(r.team_name)
                if team_id is None:
                    logger.warning(
                        "Cannot resolve team_id for '%s', skipping economy round %d",
                        r.team_name,
                        r.round_number,
                    )
                    continue
                economy_data.append({
                    "match_id": match_id,
                    "map_number": map_number,
                    "round_number": r.round_number,
                    "team_id": team_id,
                    "equipment_value": r.equipment_value,
                    "buy_type": r.buy_type,
                    "scraped_at": now,
                    "source_url": econ_source_url,
                    "parser_version": PARSER_VERSION,
                })

            if skipped_rounds > 0:
                logger.info(
                    "Skipped %d economy rounds not in round_history for match %d map %d",
                    skipped_rounds,
                    match_id,
                    map_number,
                )

            # --- Build kill_matrix_data dicts ---
            kill_matrix_data = []
            for km in perf_result.kill_matrix:
                kill_matrix_data.append({
                    "match_id": match_id,
                    "map_number": map_number,
                    "matrix_type": km.matrix_type,
                    "player1_id": km.player1_id,
                    "player2_id": km.player2_id,
                    "player1_kills": km.player1_kills,
                    "player2_kills": km.player2_kills,
                    "scraped_at": now,
                    "source_url": perf_source_url,
                    "parser_version": PARSER_VERSION,
                })

            # --- Validate before persist ---
            ctx = {"match_id": match_id, "map_number": map_number}

            validated_perf, perf_q = validate_batch(
                perf_stats, PlayerStatsModel, ctx, match_repo
            )
            validated_econ, econ_q = validate_batch(
                economy_data, EconomyModel, ctx, match_repo
            )
            validated_km, km_q = validate_batch(
                kill_matrix_data, KillMatrixModel, ctx, match_repo
            )

            if perf_q or econ_q or km_q:
                logger.warning(
                    "mapstatsid %d: quarantined %d perf_stats, "
                    "%d economy, %d kill_matrix",
                    mapstatsid, perf_q, econ_q, km_q,
                )

            if not validated_perf:
                logger.error(
                    "All perf_stats quarantined for mapstatsid %d, skipping",
                    mapstatsid,
                )
                stats["failed"] += 1
                continue

            # Batch-level check: economy alignment
            econ_warnings = check_economy_alignment(
                validated_econ, valid_rounds, match_id, map_number
            )
            for w in econ_warnings:
                logger.warning(w)

            # --- Persist atomically ---
            match_repo.upsert_perf_economy_complete(
                validated_perf, validated_econ, validated_km
            )
            stats["parsed"] += 1
            logger.info(
                "Parsed and persisted mapstatsid %d (match %d, map %d): "
                "%d player_stats, %d economy rows, %d kill_matrix entries",
                mapstatsid,
                match_id,
                map_number,
                len(validated_perf),
                len(validated_econ),
                len(validated_km),
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
