"""Match-complete pipeline (v2).

Architecture: discover all → process all in a worker pool.

Unlike the v1 pipeline (3 separate stage loops streaming into each other),
v2 runs discovery to completion first, then spins up N workers where each
worker owns one match end-to-end:

    overview → all map stats → all perf/economy

Benefits:
  - Each match is fully complete before the worker moves to the next.
  - One browser per worker — no cross-stage coordination needed.
  - Easy to scale: change --workers to add more parallel browsers.
  - Predictable: a match is either untouched or fully scraped.

CLI usage:
  hltv-scraper --pipeline v2 --workers 4 --end-offset 100 --clean
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from scraper.config import ScraperConfig
from scraper.discovery import run_discovery
from scraper.economy_parser import parse_economy
from scraper.map_stats_parser import parse_map_stats
from scraper.match_parser import parse_match_overview
from scraper.models.match import ForfeitMatchModel, MatchModel
from scraper.models.map import MapModel
from scraper.models.veto import VetoModel
from scraper.performance_parser import parse_performance
from scraper.pipeline import ShutdownHandler
from scraper.validation import validate_and_quarantine, validate_batch

logger = logging.getLogger(__name__)

_OVERVIEW_PARSER  = "match_overview_v1"
_MAP_STATS_PARSER = "map_stats_v1"
_PERF_ECON_PARSER = "perf_economy_v1"

_MAP_STATS_URL = "/stats/matches/mapstatsid/{mapstatsid}/x"
_PERF_URL      = "/stats/matches/performance/mapstatsid/{mapstatsid}/x"
_ECON_URL      = "/stats/matches/economy/mapstatsid/{mapstatsid}/x"


# ---------------------------------------------------------------------------
# Per-match complete scraper
# ---------------------------------------------------------------------------

async def _scrape_match(
    match_id: int,
    url: str,
    client,
    match_repo,
    discovery_repo,
    storage,
    config: ScraperConfig,
) -> dict:
    """Fetch, parse, and persist one match completely: overview → maps → perf/econ.

    Returns dict with: ok, maps_done, error.
    """
    result = {"ok": False, "maps_done": 0, "error": None}
    base = config.base_url

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def async_save(html: str, **kwargs) -> None:
        """Save HTML in a thread-pool executor (non-blocking) if save_html is set."""
        if not config.save_html:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: storage.save(html, **kwargs))

    # ------------------------------------------------------------------ #
    # Stage A: Match overview
    # ------------------------------------------------------------------ #
    try:
        html = await client.fetch(base + url, ready_selector=".match-page", page_type="overview")
    except Exception as exc:
        result["error"] = f"overview fetch: {exc}"
        logger.error("Match %d overview fetch: %s", match_id, exc)
        discovery_repo.update_status(match_id, "failed")
        return result

    await async_save(html, match_id=match_id, page_type="overview")

    try:
        parsed = parse_match_overview(html, match_id)
    except Exception as exc:
        result["error"] = f"overview parse: {exc}"
        logger.error("Match %d overview parse: %s", match_id, exc)
        discovery_repo.update_status(match_id, "failed")
        return result

    ts         = now()
    source_url = base + url
    date_iso   = datetime.fromtimestamp(
        parsed.date_unix_ms / 1000, tz=timezone.utc
    ).strftime("%Y-%m-%d")

    match_data = {
        "match_id": match_id, "date": date_iso,
        "date_unix_ms": parsed.date_unix_ms,
        "event_id": parsed.event_id, "event_name": parsed.event_name,
        "team1_id": parsed.team1_id, "team1_name": parsed.team1_name,
        "team2_id": parsed.team2_id, "team2_name": parsed.team2_name,
        "team1_score": parsed.team1_score, "team2_score": parsed.team2_score,
        "best_of": parsed.best_of, "is_lan": parsed.is_lan,
        "match_url": url, "scraped_at": ts, "source_url": source_url,
        "parser_version": _OVERVIEW_PARSER,
    }

    maps_data = [
        {
            "match_id": match_id, "map_number": m.map_number,
            "mapstatsid": m.mapstatsid, "map_name": m.map_name,
            "team1_rounds": m.team1_rounds, "team2_rounds": m.team2_rounds,
            "team1_ct_rounds": m.team1_ct_rounds, "team1_t_rounds": m.team1_t_rounds,
            "team2_ct_rounds": m.team2_ct_rounds, "team2_t_rounds": m.team2_t_rounds,
            "scraped_at": ts, "source_url": source_url,
            "parser_version": _OVERVIEW_PARSER,
        }
        for m in parsed.maps
    ]

    vetoes_data = []
    if parsed.vetoes:
        vetoes_data = [
            {
                "match_id": match_id, "step_number": v.step_number,
                "team_name": v.team_name, "action": v.action,
                "map_name": v.map_name, "scraped_at": ts,
                "source_url": source_url, "parser_version": _OVERVIEW_PARSER,
            }
            for v in parsed.vetoes
        ]

    ctx = {"match_id": match_id}
    model_cls = ForfeitMatchModel if parsed.is_forfeit else MatchModel
    validated_match = validate_and_quarantine(match_data, model_cls, ctx, match_repo)
    if validated_match is None:
        logger.error("Match %d failed validation — quarantined", match_id)
        discovery_repo.update_status(match_id, "failed")
        result["error"] = "validation failed"
        return result

    validated_maps, maps_q = validate_batch(maps_data, MapModel, ctx, match_repo)
    validated_vetoes, vetoes_q = validate_batch(vetoes_data, VetoModel, ctx, match_repo)
    if maps_q or vetoes_q:
        logger.warning("Match %d: quarantined %d maps, %d vetoes", match_id, maps_q, vetoes_q)

    match_repo.upsert_match_overview(
        match_data=match_data,
        maps_data=validated_maps,
        vetoes_data=validated_vetoes,
    )
    discovery_repo.update_status(match_id, "scraped")
    logger.info("Parsed and persisted match %d (%s)", match_id, source_url)

    # ------------------------------------------------------------------ #
    # Stages B + C: parallel per-map fetching
    #
    # Per-map pipeline: for each map, fetch stats → perf → econ back-to-back
    # on the same tab.  All maps run in parallel (staggered 0.1 s apart), so
    # a BO3 fires up to 3 concurrent tab pipelines at once.
    # ------------------------------------------------------------------ #
    if parsed.is_forfeit:
        result["ok"] = True
        return result

    playable = [m for m in parsed.maps if m.mapstatsid]
    if not playable:
        result["ok"] = True
        return result

    # Pre-fetch team resolution data once (used in every perf/econ stage)
    match_row = match_repo.get_match(match_id) or {}
    team_name_to_id = {
        match_row.get("team1_name"): match_row.get("team1_id"),
        match_row.get("team2_name"): match_row.get("team2_id"),
    }

    # ---- Stage B helper ------------------------------------------------
    async def fetch_map_stats_one(m) -> bool:
        mapstatsid = m.mapstatsid
        map_number = m.map_number
        map_url    = base + _MAP_STATS_URL.format(mapstatsid=mapstatsid)
        try:
            map_html = await client.fetch(map_url, page_type="map_stats",
                                          ready_selector=".stats-table")
        except Exception as exc:
            logger.error("Map %d fetch: %s", mapstatsid, exc)
            return False

        await async_save(map_html, match_id=match_id,
                         mapstatsid=mapstatsid, page_type="map_stats")
        try:
            map_parsed = parse_map_stats(map_html, mapstatsid)
        except Exception as exc:
            logger.error("Map %d parse: %s", mapstatsid, exc)
            return False

        ts = now()
        stats_data = [
            {
                "match_id": match_id, "map_number": map_number,
                "player_id": ps.player_id, "player_name": ps.player_name,
                "team_id": ps.team_id,
                "kills": ps.kills, "deaths": ps.deaths, "assists": ps.assists,
                "flash_assists": ps.flash_assists, "hs_kills": ps.hs_kills,
                "kd_diff": ps.kd_diff, "adr": ps.adr, "kast": ps.kast,
                "fk_diff": ps.fk_diff, "rating": ps.rating,
                "kpr": None, "dpr": None, "mk_rating": None,
                "opening_kills": ps.opening_kills, "opening_deaths": ps.opening_deaths,
                "multi_kills": ps.multi_kills, "clutch_wins": ps.clutch_wins,
                "traded_deaths": ps.traded_deaths, "round_swing": ps.round_swing,
                "e_kills": ps.e_kills, "e_deaths": ps.e_deaths,
                "e_hs_kills": ps.e_hs_kills, "e_kd_diff": ps.e_kd_diff,
                "e_adr": ps.e_adr, "e_kast": ps.e_kast,
                "e_opening_kills": ps.e_opening_kills,
                "e_opening_deaths": ps.e_opening_deaths,
                "e_fk_diff": ps.e_fk_diff, "e_traded_deaths": ps.e_traded_deaths,
                "scraped_at": ts, "source_url": map_url,
                "parser_version": _MAP_STATS_PARSER,
            }
            for ps in map_parsed.players
        ]
        rounds_data = [
            {
                "match_id": match_id, "map_number": map_number,
                "round_number": ro.round_number, "winner_side": ro.winner_side,
                "win_type": ro.win_type, "winner_team_id": ro.winner_team_id,
                "scraped_at": ts, "source_url": map_url,
                "parser_version": _MAP_STATS_PARSER,
            }
            for ro in map_parsed.rounds
        ]
        match_repo.upsert_map_stats_complete(stats_data=stats_data, rounds_data=rounds_data)
        logger.info("Parsed and persisted mapstatsid %d (match %d, map %d)",
                    mapstatsid, match_id, map_number)
        return True

    # ---- Stage C helper ------------------------------------------------
    async def fetch_perf_econ_one(m) -> bool:
        mapstatsid = m.mapstatsid
        map_number = m.map_number
        perf_url   = base + _PERF_URL.format(mapstatsid=mapstatsid)
        econ_url   = base + _ECON_URL.format(mapstatsid=mapstatsid)

        # Fetch perf then econ sequentially (same tab).
        # Targeted extraction: ~50–100 KB instead of 5–12 MB per fetch.
        try:
            perf_html = await client.fetch(perf_url, page_type="map_performance",
                                           ready_selector=".player-nick")
            econ_html = await client.fetch(econ_url, page_type="map_economy",
                                           ready_selector="[data-fusionchart-config]")
        except ValueError as exc:
            # Page loaded but no data (e.g. no player stats for this event).
            logger.warning("Map %d perf/econ: no data on page (%s)", mapstatsid, exc)
            match_repo.increment_perf_attempts(match_id, map_number)
            return False
        except Exception as exc:
            logger.error("Map %d perf/econ fetch: %s", mapstatsid, exc)
            return False

        # Fire both saves concurrently in the thread pool (non-blocking)
        await asyncio.gather(
            async_save(perf_html, match_id=match_id,
                       mapstatsid=mapstatsid, page_type="map_performance"),
            async_save(econ_html, match_id=match_id,
                       mapstatsid=mapstatsid, page_type="map_economy"),
        )

        try:
            perf_parsed = parse_performance(perf_html, mapstatsid)
            econ_parsed = parse_economy(econ_html, mapstatsid)
        except ValueError as exc:
            # Expected for matches where HLTV doesn't publish perf/econ data
            # (e.g. some lower-tier events). Increment attempt counter so
            # incremental runs don't retry this map beyond max_attempts.
            logger.warning("Map %d perf/econ: no data available (%s)", mapstatsid, exc)
            match_repo.increment_perf_attempts(match_id, map_number)
            return False
        except Exception as exc:
            logger.error("Map %d perf/econ parse: %s", mapstatsid, exc)
            match_repo.increment_perf_attempts(match_id, map_number)
            return False

        ts       = now()
        existing = {s["player_id"]: s for s in
                    match_repo.get_player_stats(match_id, map_number)}

        perf_stats = [
            {
                "match_id": match_id, "map_number": map_number,
                "player_id": p.player_id,
                "player_name": existing.get(p.player_id, {}).get("player_name", p.player_name),
                "team_id":          existing.get(p.player_id, {}).get("team_id"),
                "kills":            existing.get(p.player_id, {}).get("kills"),
                "deaths":           existing.get(p.player_id, {}).get("deaths"),
                "assists":          existing.get(p.player_id, {}).get("assists"),
                "flash_assists":    existing.get(p.player_id, {}).get("flash_assists"),
                "hs_kills":         existing.get(p.player_id, {}).get("hs_kills"),
                "kd_diff":          existing.get(p.player_id, {}).get("kd_diff"),
                "adr":              existing.get(p.player_id, {}).get("adr"),
                "kast":             existing.get(p.player_id, {}).get("kast"),
                "fk_diff":          existing.get(p.player_id, {}).get("fk_diff"),
                "rating":           existing.get(p.player_id, {}).get("rating"),
                "kpr": p.kpr, "dpr": p.dpr, "mk_rating": p.mk_rating,
                "opening_kills":    existing.get(p.player_id, {}).get("opening_kills"),
                "opening_deaths":   existing.get(p.player_id, {}).get("opening_deaths"),
                "multi_kills":      existing.get(p.player_id, {}).get("multi_kills"),
                "clutch_wins":      existing.get(p.player_id, {}).get("clutch_wins"),
                "traded_deaths":    existing.get(p.player_id, {}).get("traded_deaths"),
                "round_swing":      existing.get(p.player_id, {}).get("round_swing"),
                "e_kills":          existing.get(p.player_id, {}).get("e_kills"),
                "e_deaths":         existing.get(p.player_id, {}).get("e_deaths"),
                "e_hs_kills":       existing.get(p.player_id, {}).get("e_hs_kills"),
                "e_kd_diff":        existing.get(p.player_id, {}).get("e_kd_diff"),
                "e_adr":            existing.get(p.player_id, {}).get("e_adr"),
                "e_kast":           existing.get(p.player_id, {}).get("e_kast"),
                "e_opening_kills":  existing.get(p.player_id, {}).get("e_opening_kills"),
                "e_opening_deaths": existing.get(p.player_id, {}).get("e_opening_deaths"),
                "e_fk_diff":        existing.get(p.player_id, {}).get("e_fk_diff"),
                "e_traded_deaths":  existing.get(p.player_id, {}).get("e_traded_deaths"),
                "scraped_at": ts, "source_url": perf_url,
                "parser_version": _PERF_ECON_PARSER,
            }
            for p in perf_parsed.players
        ]

        econ_t1_id = team_name_to_id.get(econ_parsed.team1_name) or match_row.get("team1_id")
        econ_t2_id = team_name_to_id.get(econ_parsed.team2_name) or match_row.get("team2_id")
        valid_rounds = match_repo.get_valid_round_numbers(match_id, map_number)
        economy_data = []
        for r in econ_parsed.rounds:
            if r.round_number not in valid_rounds:
                continue
            t_id = team_name_to_id.get(r.team_name) or econ_t1_id
            economy_data.append({
                "match_id": match_id, "map_number": map_number,
                "round_number": r.round_number, "team_id": t_id,
                "equipment_value": r.equipment_value, "buy_type": r.buy_type,
                "scraped_at": ts, "source_url": econ_url,
                "parser_version": _PERF_ECON_PARSER,
            })

        kill_matrix_data = [
            {
                "match_id": match_id, "map_number": map_number,
                "matrix_type": k.matrix_type,
                "player1_id": k.player1_id, "player2_id": k.player2_id,
                "player1_kills": k.player1_kills, "player2_kills": k.player2_kills,
                "scraped_at": ts, "source_url": perf_url,
                "parser_version": _PERF_ECON_PARSER,
            }
            for k in perf_parsed.kill_matrix
        ]

        match_repo.upsert_perf_economy_complete(
            perf_stats=perf_stats,
            economy_data=economy_data,
            kill_matrix_data=kill_matrix_data,
        )
        logger.info(
            "Parsed and persisted mapstatsid %d (match %d, map %d): "
            "%d player_stats, %d economy rows, %d kill_matrix entries (%s)",
            mapstatsid, match_id, map_number,
            len(perf_stats), len(economy_data), len(kill_matrix_data), perf_url,
        )
        return True

    async def scrape_map_pipeline(i: int, m) -> bool:
        """Run B→C for one map.  Stagger starts by 0.1 s to avoid
        simultaneous CDP navigation, but chain B→C immediately within
        each map (no waiting for other maps' B to finish first).
        """
        if i > 0:
            await asyncio.sleep(i * 0.1)
        b_ok = await fetch_map_stats_one(m)
        if not b_ok:
            return False
        return await fetch_perf_econ_one(m)

    # ---- Stages B + C: pipelined per-map --------------------------------
    # Each map runs stats → perf/econ back-to-back on its own tab.
    # Maps are staggered 0.1 s apart to avoid simultaneous CDP navigation.
    # As soon as a map's stats fetch completes it immediately starts
    # perf/econ — no waiting for the other maps' stats to finish first.
    bc_results = await asyncio.gather(
        *[scrape_map_pipeline(i, m) for i, m in enumerate(playable)],
        return_exceptions=True,
    )
    maps_done = sum(1 for r in bc_results if r is True)

    result["maps_done"] = maps_done
    result["ok"] = True
    return result


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_pipeline_v2(
    clients: list,
    match_repo,
    discovery_repo,
    storage,
    config: ScraperConfig,
    shutdown: ShutdownHandler,
    incremental: bool = True,
    force_rescrape: bool = False,
) -> dict:
    """Run pipeline v2: discover all → parallel worker pool per match."""
    results = {
        "discovery": {},
        "overview":     {"parsed": 0, "failed": 0},
        "map_stats":    {"parsed": 0, "failed": 0},
        "perf_economy": {"parsed": 0, "failed": 0},
        "halted": False, "halt_reason": None,
    }

    if force_rescrape:
        reset = discovery_repo.reset_failed_matches()
        if reset:
            logger.info("Reset %d failed matches to pending", reset)

    # ------------------------------------------------------------------ #
    # Phase 1: Discovery — completes fully before any match is processed
    # ------------------------------------------------------------------ #
    logger.info("=== Phase 1: Discovery ===")
    try:
        disc = await run_discovery(
            clients[:1], discovery_repo, storage, config,
            incremental=incremental, shutdown=shutdown,
        )
        results["discovery"] = disc
        logger.info(
            "Discovery complete — %d matches found. "
            "Starting worker pool (%d parallel browsers).",
            disc.get("matches_found", 0), len(clients),
        )
    except Exception as exc:
        logger.error("Discovery failed: %s", exc)
        results.update(halted=True, halt_reason=f"Discovery failed: {exc}")
        return results

    if shutdown.is_set:
        results.update(halted=True, halt_reason="Shutdown requested")
        return results

    # ------------------------------------------------------------------ #
    # Phase 2: Worker pool — each client processes one match end-to-end
    # ------------------------------------------------------------------ #
    # Always fetch all pending — do NOT limit by matches_found (which is 0 on
    # incremental resume when discovery skips already-seen pages).
    pending = discovery_repo.get_pending_matches(limit=50000)
    total = len(pending)
    logger.info("=== Phase 2: Processing %d matches with %d workers ===",
                total, len(clients))

    client_queue: asyncio.Queue = asyncio.Queue()
    for c in clients:
        client_queue.put_nowait(c)

    done = 0
    failed = 0
    t0 = time.monotonic()

    async def process_one(entry: dict) -> None:
        nonlocal done, failed
        if shutdown.is_set:
            return
        client = await client_queue.get()
        try:
            r = await _scrape_match(
                match_id=entry["match_id"], url=entry["url"],
                client=client, match_repo=match_repo,
                discovery_repo=discovery_repo, storage=storage,
                config=config,
            )
            if r["ok"]:
                done += 1
                results["overview"]["parsed"]     += 1
                results["map_stats"]["parsed"]    += r["maps_done"]
                results["perf_economy"]["parsed"] += r["maps_done"]
                logger.info("[%d/%d] Match %d complete (%d maps)",
                            done + failed, total, entry["match_id"], r["maps_done"])
            else:
                failed += 1
                results["overview"]["failed"] += 1
                logger.warning("[%d/%d] Match %d failed: %s",
                               done + failed, total, entry["match_id"], r["error"])
        except Exception as exc:
            # Catch unexpected errors so one bad task doesn't kill the gather
            failed += 1
            results["overview"]["failed"] += 1
            logger.error("Unexpected error on match %d: %s", entry["match_id"], exc)
        finally:
            client_queue.put_nowait(client)

    # return_exceptions=True: one task's failure won't cancel the others
    await asyncio.gather(*[process_one(e) for e in pending], return_exceptions=True)

    logger.info("Worker pool done: %d ok, %d failed, %.0fs elapsed",
                done, failed, time.monotonic() - t0)
    return results
