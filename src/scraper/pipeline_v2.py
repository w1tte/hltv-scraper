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
        html = await client.fetch(base + url, ready_selector=".team1-gradient", page_type="overview")
    except Exception as exc:
        result["error"] = f"overview fetch: {exc}"
        logger.error("Match %d overview fetch: %s", match_id, exc)
        return result

    await async_save(html, match_id=match_id, page_type="overview")

    try:
        parsed = parse_match_overview(html, match_id)
    except Exception as exc:
        result["error"] = f"overview parse: {exc}"
        logger.error("Match %d overview parse: %s", match_id, exc)
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
        result["error"] = "validation failed"
        return result

    validated_maps, maps_q = validate_batch(maps_data, MapModel, ctx, match_repo)
    validated_vetoes, vetoes_q = validate_batch(vetoes_data, VetoModel, ctx, match_repo)
    if maps_q or vetoes_q:
        logger.warning("Match %d: quarantined %d maps, %d vetoes", match_id, maps_q, vetoes_q)

    # Overview data collected but NOT persisted yet — will be persisted
    # atomically with all map data only if every stage succeeds.
    maps_data = validated_maps
    vetoes_data = validated_vetoes
    logger.debug("Overview parsed for match %d (%s)", match_id, source_url)

    # ------------------------------------------------------------------ #
    # Stages B + C: parallel per-map fetching
    #
    # Per-map pipeline: for each map, fetch stats → perf → econ back-to-back
    # on the same tab.  All maps run in parallel (staggered 0.1 s apart), so
    # a BO3 fires up to 3 concurrent tab pipelines at once.
    #
    # Nothing is persisted until ALL maps complete successfully.
    # ------------------------------------------------------------------ #
    if parsed.is_forfeit:
        # Forfeits have no map data — persist overview only
        match_repo.persist_complete_match(
            match_data=match_data, maps_data=maps_data,
            vetoes_data=vetoes_data, all_stats=[], all_rounds=[],
            all_economy=[], all_kill_matrix=[],
        )
        result["ok"] = True
        return result

    playable = [m for m in parsed.maps if m.mapstatsid]
    if not playable:
        match_repo.persist_complete_match(
            match_data=match_data, maps_data=maps_data,
            vetoes_data=vetoes_data, all_stats=[], all_rounds=[],
            all_economy=[], all_kill_matrix=[],
        )
        result["ok"] = True
        return result

    # Team name→id mapping for economy data (resolved from overview)
    match_row = match_data
    team_name_to_id = {
        match_data.get("team1_name"): match_data.get("team1_id"),
        match_data.get("team2_name"): match_data.get("team2_id"),
    }

    # ---- Stage B helper ------------------------------------------------
    async def fetch_map_stats_one(m, tab=None) -> dict | None:
        """Fetch and parse map stats. Returns collected data dict or None on failure."""
        mapstatsid = m.mapstatsid
        map_number = m.map_number
        map_url    = base + _MAP_STATS_URL.format(mapstatsid=mapstatsid)
        try:
            if tab is not None:
                map_html = await client.fetch_with_tab(
                    tab, map_url, page_type="map_stats", ready_selector=".stats-table")
            else:
                map_html = await client.fetch(
                    map_url, page_type="map_stats", ready_selector=".stats-table")
        except ValueError as exc:
            logger.warning("Map %d fetch: no data (%s)", mapstatsid, exc)
            return None
        except Exception as exc:
            logger.error("Map %d fetch: %s", mapstatsid, exc)
            return None

        await async_save(map_html, match_id=match_id,
                         mapstatsid=mapstatsid, page_type="map_stats")
        try:
            map_parsed = parse_map_stats(map_html, mapstatsid)
        except ValueError as exc:
            logger.warning("Map %d parse: %s", mapstatsid, exc)
            return None
        except Exception as exc:
            logger.error("Map %d parse: %s", mapstatsid, exc)
            return None

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
        logger.info("Fetched mapstatsid %d (match %d, map %d)",
                    mapstatsid, match_id, map_number)
        return {"stats": stats_data, "rounds": rounds_data}

    # ---- Stage C helper ------------------------------------------------
    async def fetch_perf_econ_one(m, stats_lookup: dict, round_numbers: set, tab=None) -> dict | None:
        """Fetch and parse perf+econ. Returns collected data dict or None on failure.

        Args:
            stats_lookup: {player_id: stats_dict} from stage B for in-memory merge.
            round_numbers: set of valid round numbers from stage B round_history.
        """
        mapstatsid = m.mapstatsid
        map_number = m.map_number
        perf_url   = base + _PERF_URL.format(mapstatsid=mapstatsid)
        econ_url   = base + _ECON_URL.format(mapstatsid=mapstatsid)

        try:
            if tab is not None:
                perf_html = await client.fetch_with_tab(
                    tab, perf_url, page_type="map_performance",
                    ready_selector=".player-nick")
                econ_html = await client.fetch_with_tab(
                    tab, econ_url, page_type="map_economy",
                    ready_selector="[data-fusionchart-config]")
            else:
                perf_html = await client.fetch(perf_url, page_type="map_performance",
                                               ready_selector=".player-nick")
                econ_html = await client.fetch(econ_url, page_type="map_economy",
                                               ready_selector="[data-fusionchart-config]")
        except ValueError as exc:
            logger.warning("Map %d perf/econ: no data on page (%s)", mapstatsid, exc)
            return None
        except Exception as exc:
            logger.error("Map %d perf/econ fetch: %s", mapstatsid, exc)
            return None

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
            logger.warning("Map %d perf/econ: no data available (%s)", mapstatsid, exc)
            return None
        except Exception as exc:
            logger.error("Map %d perf/econ parse: %s", mapstatsid, exc)
            return None

        ts = now()
        # Merge basic stats (from stage B in-memory) with perf fields
        perf_stats = [
            {
                "match_id": match_id, "map_number": map_number,
                "player_id": p.player_id,
                "player_name": stats_lookup.get(p.player_id, {}).get("player_name", p.player_name),
                "team_id":          stats_lookup.get(p.player_id, {}).get("team_id"),
                "kills":            stats_lookup.get(p.player_id, {}).get("kills"),
                "deaths":           stats_lookup.get(p.player_id, {}).get("deaths"),
                "assists":          stats_lookup.get(p.player_id, {}).get("assists"),
                "flash_assists":    stats_lookup.get(p.player_id, {}).get("flash_assists"),
                "hs_kills":         stats_lookup.get(p.player_id, {}).get("hs_kills"),
                "kd_diff":          stats_lookup.get(p.player_id, {}).get("kd_diff"),
                "adr":              stats_lookup.get(p.player_id, {}).get("adr"),
                "kast":             stats_lookup.get(p.player_id, {}).get("kast"),
                "fk_diff":          stats_lookup.get(p.player_id, {}).get("fk_diff"),
                "rating":           stats_lookup.get(p.player_id, {}).get("rating"),
                "kpr": p.kpr, "dpr": p.dpr, "mk_rating": p.mk_rating,
                "opening_kills":    stats_lookup.get(p.player_id, {}).get("opening_kills"),
                "opening_deaths":   stats_lookup.get(p.player_id, {}).get("opening_deaths"),
                "multi_kills":      stats_lookup.get(p.player_id, {}).get("multi_kills"),
                "clutch_wins":      stats_lookup.get(p.player_id, {}).get("clutch_wins"),
                "traded_deaths":    stats_lookup.get(p.player_id, {}).get("traded_deaths"),
                "round_swing":      stats_lookup.get(p.player_id, {}).get("round_swing"),
                "e_kills":          stats_lookup.get(p.player_id, {}).get("e_kills"),
                "e_deaths":         stats_lookup.get(p.player_id, {}).get("e_deaths"),
                "e_hs_kills":       stats_lookup.get(p.player_id, {}).get("e_hs_kills"),
                "e_kd_diff":        stats_lookup.get(p.player_id, {}).get("e_kd_diff"),
                "e_adr":            stats_lookup.get(p.player_id, {}).get("e_adr"),
                "e_kast":           stats_lookup.get(p.player_id, {}).get("e_kast"),
                "e_opening_kills":  stats_lookup.get(p.player_id, {}).get("e_opening_kills"),
                "e_opening_deaths": stats_lookup.get(p.player_id, {}).get("e_opening_deaths"),
                "e_fk_diff":        stats_lookup.get(p.player_id, {}).get("e_fk_diff"),
                "e_traded_deaths":  stats_lookup.get(p.player_id, {}).get("e_traded_deaths"),
                "scraped_at": ts, "source_url": perf_url,
                "parser_version": _PERF_ECON_PARSER,
            }
            for p in perf_parsed.players
        ]

        econ_t1_id = team_name_to_id.get(econ_parsed.team1_name) or match_data.get("team1_id")
        economy_data = []
        for r in econ_parsed.rounds:
            if r.round_number not in round_numbers:
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

        logger.info(
            "Fetched perf/econ mapstatsid %d (match %d, map %d): "
            "%d player_stats, %d economy rows, %d kill_matrix entries",
            mapstatsid, match_id, map_number,
            len(perf_stats), len(economy_data), len(kill_matrix_data),
        )
        return {"stats": perf_stats, "economy": economy_data, "kill_matrix": kill_matrix_data}

    async def scrape_map_pipeline(i: int, m) -> dict | None:
        """Run B→C for one map on a single pinned tab.

        Returns dict with all collected data, or None if any stage failed.
        """
        if i > 0:
            await asyncio.sleep(i * 0.02)
        async with client.pinned_tab() as tab:
            b_data = await fetch_map_stats_one(m, tab)
            if b_data is None:
                return None
            # Build lookup for in-memory merge (replaces DB query)
            stats_lookup = {s["player_id"]: s for s in b_data["stats"]}
            round_numbers = {r["round_number"] for r in b_data["rounds"]}
            c_data = await fetch_perf_econ_one(m, stats_lookup, round_numbers, tab)
            if c_data is None:
                return None
            return {
                "map_stats": b_data["stats"],
                "rounds": b_data["rounds"],
                "perf_stats": c_data["stats"],
                "economy": c_data["economy"],
                "kill_matrix": c_data["kill_matrix"],
            }

    # ---- Stages B + C: pipelined per-map --------------------------------
    bc_results = await asyncio.gather(
        *[scrape_map_pipeline(i, m) for i, m in enumerate(playable)],
        return_exceptions=True,
    )

    # Check if ALL maps succeeded
    maps_failed = [
        m.mapstatsid for m, r in zip(playable, bc_results)
        if not isinstance(r, dict)
    ]

    if maps_failed:
        result["ok"] = False
        result["maps_done"] = 0
        result["error"] = f"{len(maps_failed)}/{len(playable)} maps failed (mapstatsids: {maps_failed})"
        logger.warning("Match %d incomplete: %d/%d maps failed %s",
                       match_id, len(maps_failed), len(playable), maps_failed)
        return result

    # All maps succeeded — persist everything atomically
    all_stats = []
    all_rounds = []
    all_economy = []
    all_kill_matrix = []
    for r in bc_results:
        # perf_stats is the merged version (basic + perf fields) — use it
        # instead of map_stats to avoid duplicate inserts
        all_stats.extend(r["perf_stats"])
        all_rounds.extend(r["rounds"])
        all_economy.extend(r["economy"])
        all_kill_matrix.extend(r["kill_matrix"])

    match_repo.persist_complete_match(
        match_data=match_data,
        maps_data=maps_data,
        vetoes_data=vetoes_data,
        all_stats=all_stats,
        all_rounds=all_rounds,
        all_economy=all_economy,
        all_kill_matrix=all_kill_matrix,
    )
    result["ok"] = True
    result["maps_done"] = len(playable)
    logger.info("Persisted match %d: %d maps, %d stats, %d rounds, %d economy, %d kill_matrix",
                match_id, len(playable), len(all_stats), len(all_rounds),
                len(all_economy), len(all_kill_matrix))
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
    skip_discovery: bool = False,
) -> dict:
    """Run pipeline v2: discover all → parallel worker pool per match."""
    results = {
        "discovery": {},
        "overview":     {"parsed": 0, "failed": 0},
        "map_stats":    {"parsed": 0, "failed": 0},
        "perf_economy": {"parsed": 0, "failed": 0},
        "halted": False, "halt_reason": None,
    }

    # Crash recovery: reset in-progress matches from previous interrupted run
    recovered = discovery_repo.recover_in_progress()
    if recovered:
        logger.info("Recovered %d in-flight matches from previous crash → pending", recovered)

    # Auto-reset failed matches that haven't exhausted retries (< 5 attempts)
    reset = discovery_repo.reset_failed_matches()
    if reset:
        logger.info("Reset %d failed matches to pending (attempts < 5)", reset)

    # ------------------------------------------------------------------ #
    # Phase 1: Discovery — completes fully before any match is processed
    # ------------------------------------------------------------------ #
    if skip_discovery:
        logger.info("=== Phase 1: Discovery (skipped — already done) ===")
    else:
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
    # Log queue summary so the user sees resume progress
    qs = discovery_repo.get_queue_summary()
    if qs["scraped"] or qs["failed"]:
        logger.info("Resuming: %d pending, %d scraped, %d failed (%d total)",
                     qs["pending"], qs["scraped"], qs["failed"], qs["total"])

    # Always fetch all pending — do NOT limit by matches_found (which is 0 on
    # incremental resume when discovery skips already-seen pages).
    pending = discovery_repo.get_pending_matches(limit=50000)
    total = len(pending)
    logger.info("=== Phase 2: Processing %d matches with %d workers ===",
                total, len(clients))

    client_queue: asyncio.Queue = asyncio.Queue()
    for c in clients:
        client_queue.put_nowait(c)

    counters = {"done": 0, "failed": 0}
    # Per-client consecutive failure tracker (timeouts + match failures)
    client_failures: dict[int, int] = {id(c): 0 for c in clients}
    _FAILURE_RESTART_THRESHOLD = 3  # rotate proxy after 3 consecutive failures
    # Per-client match counter for proactive proxy rotation
    client_match_count: dict[int, int] = {id(c): 0 for c in clients}
    _PROXY_ROTATE_EVERY = 150  # restarts waste ~15s; with 6 workers across 20 proxies, rotate infrequently
    # Track consecutive restart failures per client to prevent death spiral
    client_restart_failures: dict[int, int] = {id(c): 0 for c in clients}
    _MAX_RESTART_FAILURES = 5  # after 5 failed restarts, long cooldown
    _GLOBAL_RESTART_FAILURE_LIMIT = 20  # if total restart failures hit this, nuke all chrome
    # Serialize browser restarts — concurrent restarts compete for PIDs and fail each other
    _restart_lock = asyncio.Lock()
    # Watchdog: track active workers to detect stuck ones
    active_workers: dict[int, dict] = {}  # client_id -> {match_id, started_at, task}
    t0 = time.monotonic()

    async def process_one(entry: dict) -> None:
        # Acquire client FIRST to prevent queue leaks on early-return paths.
        client = await client_queue.get()
        active_workers[id(client)] = {
            "match_id": entry["match_id"],
            "started_at": time.monotonic(),
            "task": asyncio.current_task(),
        }
        try:
            if shutdown.is_set:
                return

            # Mark match as in-progress for crash recovery tracking (US-008)
            discovery_repo.mark_in_progress(entry["match_id"])

            # Health check: restart browser if Chrome crashed or unresponsive
            if not client.is_healthy:
                async with _restart_lock:
                    # Re-check after acquiring lock — another worker's restart
                    # may have freed resources that fixed our browser too.
                    if not client.is_healthy:
                        rf = client_restart_failures.get(id(client), 0)
                        total_rf = sum(client_restart_failures.values())
                        if total_rf >= _GLOBAL_RESTART_FAILURE_LIMIT:
                            logger.error(
                                "Global restart failures hit %d — killing all Chrome "
                                "processes and cooling down 60s",
                                total_rf,
                            )
                            await client._kill_stale_chrome()
                            for k in client_restart_failures:
                                client_restart_failures[k] = 0
                            await asyncio.sleep(60.0)
                        elif rf >= _MAX_RESTART_FAILURES:
                            logger.warning(
                                "Client has %d consecutive restart failures — cooling down 30s",
                                rf,
                            )
                            await asyncio.sleep(30.0)
                        try:
                            await client.restart()
                            client_failures[id(client)] = 0
                            client_restart_failures[id(client)] = 0
                        except Exception as restart_exc:
                            client_restart_failures[id(client)] = rf + 1
                            logger.error("Browser restart failed for match %d (attempt %d): %s",
                                         entry["match_id"], rf + 1, restart_exc)
                            counters["failed"] += 1
                            results["overview"]["failed"] += 1
                            await asyncio.sleep(min(5.0 * (rf + 1), 30.0))
                            return

            # Per-match timeout: defense-in-depth against hung matches
            try:
                r = await asyncio.wait_for(
                    _scrape_match(
                        match_id=entry["match_id"], url=entry["url"],
                        client=client, match_repo=match_repo,
                        discovery_repo=discovery_repo, storage=storage,
                        config=config,
                    ),
                    timeout=config.per_match_timeout,
                )
            except asyncio.TimeoutError:
                logger.error("Match %d timed out after %.0fs",
                             entry["match_id"], config.per_match_timeout)
                discovery_repo.mark_failed(entry["match_id"])
                counters["failed"] += 1
                results["overview"]["failed"] += 1
                # Circuit breaker: restart browser after consecutive failures
                client_failures[id(client)] = client_failures.get(id(client), 0) + 1
                if client_failures[id(client)] >= _FAILURE_RESTART_THRESHOLD:
                    logger.warning(
                        "Client hit %d consecutive failures — rotating proxy",
                        client_failures[id(client)],
                    )
                    async with _restart_lock:
                        try:
                            await client.restart()
                            client_failures[id(client)] = 0
                            client_restart_failures[id(client)] = 0
                        except Exception:
                            client_restart_failures[id(client)] = client_restart_failures.get(id(client), 0) + 1
                            logger.error("Circuit-breaker restart failed (attempt %d)",
                                         client_restart_failures[id(client)])
                return

            client_match_count[id(client)] = client_match_count.get(id(client), 0) + 1

            # Log proxy health stats every 50 matches (across all workers)
            total_done = counters["done"] + counters["failed"] + 1
            if total_done % 50 == 0:
                health = getattr(client, "_proxy_health", None)
                if health:
                    health.log_health_summary()

            if r["ok"]:
                client_failures[id(client)] = 0
                discovery_repo.update_status(entry["match_id"], "scraped")
                counters["done"] += 1
                results["overview"]["parsed"]     += 1
                results["map_stats"]["parsed"]    += r["maps_done"]
                results["perf_economy"]["parsed"] += r["maps_done"]
                logger.info("[%d/%d] Match %d complete (%d maps)",
                            counters["done"] + counters["failed"], total,
                            entry["match_id"], r["maps_done"])

                # Proactive proxy rotation every N matches
                if (client_match_count[id(client)] % _PROXY_ROTATE_EVERY == 0
                        and hasattr(client, '_proxy_urls') and client._proxy_urls):
                    try:
                        await client.restart()
                        client_failures[id(client)] = 0
                        client_restart_failures[id(client)] = 0
                    except Exception:
                        logger.error("Proactive proxy rotation restart failed")

                # Memory-based browser recycling (US-006)
                elif (config.memory_limit_mb > 0
                      and client_match_count[id(client)] % config.memory_check_interval == 0):
                    rss_mb = client.get_browser_rss_mb()
                    if rss_mb is not None:
                        logger.info(
                            "Memory check: %.1f MB / %d MB threshold "
                            "(%d matches since last restart)",
                            rss_mb, config.memory_limit_mb,
                            client_match_count[id(client)],
                        )
                        if rss_mb > config.memory_limit_mb:
                            logger.warning(
                                "Browser RSS %.1f MB exceeds %d MB limit — recycling",
                                rss_mb, config.memory_limit_mb,
                            )
                            try:
                                await client.restart()
                                client_failures[id(client)] = 0
                                client_restart_failures[id(client)] = 0
                                client_match_count[id(client)] = 0
                            except Exception:
                                logger.error("Memory-triggered browser restart failed")
            else:
                discovery_repo.mark_failed(entry["match_id"])
                counters["failed"] += 1
                results["overview"]["failed"] += 1
                logger.warning("[%d/%d] Match %d failed: %s",
                               counters["done"] + counters["failed"], total,
                               entry["match_id"], r["error"])
                # Circuit breaker: rotate proxy after consecutive match failures
                client_failures[id(client)] = client_failures.get(id(client), 0) + 1
                if client_failures[id(client)] >= _FAILURE_RESTART_THRESHOLD:
                    logger.warning(
                        "Client hit %d consecutive failures — rotating proxy",
                        client_failures[id(client)],
                    )
                    async with _restart_lock:
                        try:
                            await client.restart()
                            client_failures[id(client)] = 0
                            client_restart_failures[id(client)] = 0
                        except Exception:
                            client_restart_failures[id(client)] = client_restart_failures.get(id(client), 0) + 1
                            logger.error("Circuit-breaker restart failed (attempt %d)",
                                         client_restart_failures[id(client)])
        except asyncio.CancelledError:
            # Watchdog cancelled us — match already marked failed by watchdog.
            # Let the is_healthy check handle browser restart on next acquire.
            logger.warning("Worker cancelled by watchdog for match %d", entry["match_id"])
            raise
        except Exception as exc:
            counters["failed"] += 1
            results["overview"]["failed"] += 1
            logger.error("Unexpected error on match %d: %s", entry["match_id"], exc)
            # If the browser died during the match, try to restart it
            if not client.is_healthy:
                try:
                    await client.restart()
                    client_failures[id(client)] = 0
                except Exception:
                    logger.error("Post-crash browser restart also failed")
        finally:
            active_workers.pop(id(client), None)
            client_queue.put_nowait(client)

    # ---- Watchdog: detect and restart stuck workers ----------------------
    async def _watchdog():
        """Periodically check for workers stuck longer than watchdog_timeout."""
        while not shutdown.is_set:
            await asyncio.sleep(60)
            now = time.monotonic()
            for client_id, info in list(active_workers.items()):
                elapsed = now - info["started_at"]
                if elapsed > config.watchdog_timeout:
                    match_id = info["match_id"]
                    logger.warning(
                        "Watchdog: worker stuck on match %d for %.0fs "
                        "(timeout=%.0fs) — killing task",
                        match_id, elapsed, config.watchdog_timeout,
                    )
                    # Mark match as failed so it returns to pending on retry
                    try:
                        discovery_repo.mark_failed(match_id)
                    except Exception:
                        logger.error("Watchdog: failed to mark match %d", match_id)
                    counters["failed"] += 1
                    results["overview"]["failed"] += 1
                    # Cancel the stuck task
                    task = info.get("task")
                    if task and not task.done():
                        task.cancel()

    # Process matches in bounded-concurrency batches instead of spawning
    # all N tasks at once.  With 25k matches, asyncio.gather(all) would
    # create 25k live coroutines — each holding a stack frame and awaiting
    # the client_queue.  Batching to 8× worker count keeps memory flat
    # while ensuring workers always have queued work ready.
    watchdog_task = asyncio.create_task(_watchdog())
    batch_size = len(clients) * 8
    try:
        for batch_start in range(0, len(pending), batch_size):
            if shutdown.is_set:
                break
            batch = pending[batch_start:batch_start + batch_size]
            await asyncio.gather(*[process_one(e) for e in batch], return_exceptions=True)
            # Circuit breaker: warn on high batch failure rate
            total_processed = counters["done"] + counters["failed"]
            if total_processed > 0 and counters["failed"] / total_processed > 0.5:
                logger.warning(
                    "High failure rate: %d/%d (%.0f%%) — possible systemic issue",
                    counters["failed"], total_processed,
                    100 * counters["failed"] / total_processed,
                )
    finally:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

    logger.info("Worker pool done: %d ok, %d failed, %.0fs elapsed",
                counters["done"], counters["failed"], time.monotonic() - t0)
    return results
