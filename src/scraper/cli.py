"""CLI entry point for the HLTV scraper.

Provides ``main()`` as the sync entry point for the ``hltv-scraper``
console script, and ``async_main(args)`` which sets up logging,
initializes all components, runs the pipeline, and prints an
end-of-run summary.

Usage::

    hltv-scraper                     # incremental scrape, offsets 0-9900
    hltv-scraper --end-offset 300    # small test run
    hltv-scraper --full              # full re-discovery (no early stop)
    hltv-scraper --force-rescrape    # re-process completed matches
"""

import argparse
import asyncio
import logging
import shutil
import time
from pathlib import Path

from scraper.config import ScraperConfig
from scraper.db import Database
from scraper.discovery_repository import DiscoveryRepository
from scraper.http_client import HLTVClient
from scraper.logging_config import setup_logging
from scraper.pipeline import ShutdownHandler, run_pipeline
from scraper.pipeline_v2 import run_pipeline_v2
from scraper.repository import MatchRepository
from scraper.storage import HtmlStorage

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the hltv-scraper CLI."""
    parser = argparse.ArgumentParser(
        prog="hltv-scraper",
        description="Scrape CS2 match data from HLTV.org",
    )
    parser.add_argument(
        "--start-offset",
        type=int,
        default=0,
        help="Start offset for results pagination (default: 0)",
    )
    parser.add_argument(
        "--end-offset",
        type=int,
        default=100000,
        help="End offset for results pagination, exclusive (default: 100000 — effectively unlimited, discovery stops on its own)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full scrape -- re-discover all matches in range (disables incremental early termination)",
    )
    parser.add_argument(
        "--force-rescrape",
        action="store_true",
        help="Re-process already-complete matches (resets scraped -> pending)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe data directory before starting (fresh run)",
    )
    parser.add_argument(
        "--pipeline",
        choices=["v1", "v2"],
        default="v2",
        help=(
            "Pipeline architecture to use. "
            "v2 (default): discover all first, then worker pool per match (each browser owns one match end-to-end). "
            "v1: classic 3-stage streaming pipeline."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel browser workers for pipeline v2 (default: 8)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Data directory for DB, HTML archive, and logs (default: data)",
    )
    parser.add_argument(
        "--proxy-file",
        type=str,
        default=None,
        help="Path to file with one proxy per line (socks5://host:port, http://host:port)",
    )
    parser.add_argument(
        "--overview-workers",
        type=int,
        default=2,
        help="Browser instances for overview stage (default: 2)",
    )
    parser.add_argument(
        "--map-workers",
        type=int,
        default=3,
        help="Browser instances for map stats stage (default: 3)",
    )
    parser.add_argument(
        "--perf-workers",
        type=int,
        default=5,
        help="Browser instances for perf/economy stage (default: 5)",
    )
    parser.add_argument(
        "--concurrent-tabs",
        type=int,
        default=None,
        help="Tabs per browser instance (default: 2)",
    )
    parser.add_argument(
        "--page-load-wait",
        type=float,
        default=None,
        help="Seconds to wait after navigation (default: 0.4)",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=None,
        help="Minimum delay between requests in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--no-save-html",
        action="store_true",
        default=False,
        help="Skip saving raw HTML to disk (faster, less disk usage; DB data is still written)",
    )
    parser.add_argument(
        "--nav-timeout",
        type=float,
        default=None,
        help="CDP navigation timeout in seconds (default: 25)",
    )
    parser.add_argument(
        "--per-match-timeout",
        type=float,
        default=None,
        help="Hard timeout per match in seconds (default: 180)",
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        default=False,
        help="Skip discovery phase — use existing scrape_queue (for resuming)",
    )
    parser.add_argument(
        "--fast-recovery",
        action="store_true",
        default=False,
        help="Enable accelerated rate limiter recovery after consecutive successes",
    )
    parser.add_argument(
        "--watchdog-timeout",
        type=float,
        default=None,
        help="Seconds before watchdog restarts a stuck worker (default: 600)",
    )
    parser.add_argument(
        "--memory-limit",
        type=int,
        default=None,
        help="Restart browser when RSS exceeds this many MB (default: 300, 0 to disable)",
    )
    return parser


def _format_results(results: dict, wall_time: float, log_file: str) -> str:
    """Format end-of-run results into a human-readable summary string."""
    discovery = results.get("discovery", {})
    overview = results.get("overview", {})
    map_stats = results.get("map_stats", {})
    perf_economy = results.get("perf_economy", {})

    lines = [
        "=" * 60,
        "Pipeline complete",
        "-" * 60,
        "Discovery:   {} matches found ({} new)".format(
            discovery.get("matches_found", 0),
            discovery.get("new_matches", 0),
        ),
        "Overview:    {} parsed, {} failed".format(
            overview.get("parsed", 0),
            overview.get("failed", 0),
        ),
        "Map Stats:   {} parsed, {} failed".format(
            map_stats.get("parsed", 0),
            map_stats.get("failed", 0),
        ),
        "Perf/Econ:   {} parsed, {} failed".format(
            perf_economy.get("parsed", 0),
            perf_economy.get("failed", 0),
        ),
        "-" * 60,
        f"Wall time:   {wall_time:.0f}s",
        f"Log file:    {log_file}",
    ]

    if results.get("halted"):
        lines.append(f"Halted:      {results.get('halt_reason', 'unknown')}")

    lines.append("=" * 60)
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> None:
    """Async entry point: set up components, run pipeline, print summary."""
    # 1. Clean data dir FIRST (before logging setup so log dir exists)
    if args.clean:
        data_path = Path(args.data_dir)
        if data_path.exists():
            shutil.rmtree(data_path)
        data_path.mkdir(parents=True, exist_ok=True)

    # 2. Logging (must come after clean so log dir is fresh)
    log_file = setup_logging(data_dir=args.data_dir)

    # 3. Config
    config_overrides = {
        "data_dir": args.data_dir,
        "start_offset": args.start_offset,
        "max_offset": args.end_offset,
    }
    if args.concurrent_tabs is not None:
        config_overrides["concurrent_tabs"] = args.concurrent_tabs
    if args.page_load_wait is not None:
        config_overrides["page_load_wait"] = args.page_load_wait
    if args.min_delay is not None:
        config_overrides["min_delay"] = args.min_delay
    if args.no_save_html:
        config_overrides["save_html"] = False
    if args.nav_timeout is not None:
        config_overrides["navigation_timeout"] = args.nav_timeout
    if args.per_match_timeout is not None:
        config_overrides["per_match_timeout"] = args.per_match_timeout
    if args.fast_recovery:
        config_overrides["fast_recovery"] = True
    if args.watchdog_timeout is not None:
        config_overrides["watchdog_timeout"] = args.watchdog_timeout
    if args.memory_limit is not None:
        config_overrides["memory_limit_mb"] = args.memory_limit
    config = ScraperConfig(**config_overrides)

    mode = "full" if args.full else "incremental"
    use_v2 = args.pipeline == "v2"
    total_workers = args.workers if use_v2 else (args.overview_workers + args.map_workers + args.perf_workers)
    if use_v2:
        logger.info(
            "Starting hltv-scraper v2: offsets %d-%d, mode=%s, data_dir=%s, "
            "workers=%d, tabs=%d, page_wait=%.1fs, min_delay=%.1fs, log=%s",
            args.start_offset, args.end_offset, mode, args.data_dir,
            args.workers, config.concurrent_tabs, config.page_load_wait, config.min_delay, log_file,
        )
    else:
        logger.info(
            "Starting hltv-scraper: offsets %d-%d, mode=%s, data_dir=%s, "
            "workers=%d+%d+%d, tabs=%d, page_wait=%.1fs, min_delay=%.1fs, log=%s",
            args.start_offset, args.end_offset, mode, args.data_dir,
            args.overview_workers, args.map_workers, args.perf_workers,
            config.concurrent_tabs, config.page_load_wait, config.min_delay, log_file,
        )

    if args.clean:
        logger.info("Cleaned data directory: %s", args.data_dir)

    # 4. Shutdown handler
    shutdown = ShutdownHandler()
    shutdown.install()

    # 5. Database (PostgreSQL)
    db = Database()
    db.initialize()

    # 5b. Attach DB log handler (separate connection for autocommit writes)
    try:
        import psycopg2
        from scraper.logging_config import DbLogHandler
        log_conn = psycopg2.connect(**db.dsn)
        log_conn.autocommit = True
        db_handler = DbLogHandler(log_conn)
        db_handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(db_handler)
    except Exception:
        logger.warning("Could not attach DB log handler")

    # 6. Repositories and storage
    match_repo = MatchRepository(db.conn)
    discovery_repo = DiscoveryRepository(db.conn)
    storage = HtmlStorage(config.data_dir)

    results = {}
    start_time = time.monotonic()
    clients_to_close: list = []

    try:
        # Load proxy list if provided
        proxies: list[str] = []
        if args.proxy_file:
            with open(args.proxy_file) as f:
                proxies = [line.strip() for line in f
                           if line.strip() and not line.strip().startswith("#")]
            logger.info("Loaded %d proxies from %s", len(proxies), args.proxy_file)

        async def create_pool(count, label, proxy_offset):
            """Create a pool of HLTVClient instances with staggered startup."""
            pool = []
            for i in range(count):
                proxy = proxies[(proxy_offset + i) % len(proxies)] if proxies else None
                c = HLTVClient(config, proxy_url=proxy)
                await c.start()
                pool.append(c)
                clients_to_close.append(c)
                logger.info(
                    "Browser %d/%d ready (%s%s)",
                    len(clients_to_close), total_workers, label,
                    f" via {proxy}" if proxy else "",
                )
                if i < count - 1:
                    await asyncio.sleep(0.3)
            return pool

        if use_v2:
            # v2: flat pool — each browser owns one match end-to-end.
            # Overlap discovery with browser warmup: start browser 1 first,
            # then run discovery + warm up remaining browsers in parallel.
            # Try first proxy, then direct if it fails.
            # Build interleaved proxy sublists so each worker gets a
            # non-overlapping set.  Worker 0 → [0,2,4,...], Worker 1 → [1,3,5,...].
            # On each restart the worker rotates to its next proxy.
            def _proxy_sublist(worker_idx: int) -> list[str]:
                if not proxies:
                    return []
                return [proxies[j] for j in range(worker_idx, len(proxies), args.workers)]

            first_proxy_list = _proxy_sublist(0)
            first_proxy = first_proxy_list[0] if first_proxy_list else None
            first_client = None
            for proxy in ([first_proxy] if first_proxy else []) + [None]:
                try:
                    c = HLTVClient(config, proxy_urls=first_proxy_list or None, forwarder_port=18080)
                    await c.start()
                    first_client = c
                    clients_to_close.append(c)
                    logger.info(
                        "Browser 1/%d ready (worker via %s, %d proxies in rotation)",
                        args.workers,
                        proxy or "direct",
                        len(first_proxy_list),
                    )
                    break
                except Exception as e:
                    logger.warning(
                        "Browser 1 failed with %s: %s — trying next",
                        proxy or "direct", e,
                    )
                    try:
                        await c.close()
                    except Exception:
                        pass
            if first_client is None:
                raise RuntimeError("Could not start browser 1 (tried proxy + direct)")

            async def _warm_remaining():
                """Start browsers 2..N with staggered delays and retries."""
                pool = []
                for i in range(1, args.workers):
                    worker_proxies = _proxy_sublist(i)
                    started = False
                    for attempt in range(3):
                        try:
                            c = HLTVClient(config, proxy_urls=worker_proxies or None, forwarder_port=18080 + i)
                            await c.start()
                            pool.append(c)
                            clients_to_close.append(c)
                            logger.info(
                                "Browser %d/%d ready (worker via %s, %d proxies in rotation)",
                                i + 1, args.workers,
                                worker_proxies[0] if worker_proxies else "direct",
                                len(worker_proxies),
                            )
                            started = True
                            break
                        except Exception as e:
                            logger.warning(
                                "Browser %d/%d attempt %d/3 failed (%s): %s",
                                i + 1, args.workers, attempt + 1,
                                worker_proxies[0] if worker_proxies else "direct", e,
                            )
                            try:
                                await c.close()
                            except Exception:
                                pass
                            await asyncio.sleep(3.0)
                    if not started:
                        logger.error("Browser %d/%d failed after 3 attempts — skipping", i + 1, args.workers)
                    if i < args.workers - 1:
                        await asyncio.sleep(3.0)
                return pool

            # Run discovery on first browser while warming up the rest
            warmup_task = asyncio.create_task(_warm_remaining())

            if args.skip_discovery:
                logger.info("Skipping discovery (--skip-discovery)")
            else:
                from scraper.discovery import run_discovery
                from scraper.pipeline import ShutdownHandler as _SH
                disc_result = await run_discovery(
                    [first_client], discovery_repo, storage, config,
                    incremental=not args.full, shutdown=shutdown,
                )
                logger.info(
                    "Discovery complete — %d matches found",
                    disc_result.get("matches_found", 0),
                )

            # Wait for remaining browsers to finish warming up
            remaining = await warmup_task
            worker_pool = [first_client] + remaining

            # Reset health timers so browsers idle during warmup
            # don't trigger false "unresponsive" restarts.
            for c in worker_pool:
                c._last_eval_ok = time.monotonic()

            results = await run_pipeline_v2(
                clients=worker_pool,
                match_repo=match_repo,
                discovery_repo=discovery_repo,
                storage=storage,
                config=config,
                shutdown=shutdown,
                incremental=not args.full,
                force_rescrape=args.force_rescrape,
                skip_discovery=True,
            )
        else:
            # v1: three separate pools per stage
            overview_pool = await create_pool(
                args.overview_workers, "overview", 0,
            )
            await asyncio.sleep(2.0)
            map_pool = await create_pool(
                args.map_workers, "map stats", args.overview_workers,
            )
            await asyncio.sleep(2.0)
            perf_pool = await create_pool(
                args.perf_workers, "perf/economy",
                args.overview_workers + args.map_workers,
            )

            # Scale batch sizes so each browser gets a full batch
            config.overview_batch_size *= args.overview_workers
            config.map_stats_batch_size *= args.map_workers
            config.perf_economy_batch_size *= args.perf_workers

            clients = {
                "overview": overview_pool,
                "map_stats": map_pool,
                "perf_economy": perf_pool,
            }

            results = await run_pipeline(
                clients=clients,
                match_repo=match_repo,
                discovery_repo=discovery_repo,
                storage=storage,
                config=config,
                shutdown=shutdown,
                incremental=not args.full,
                force_rescrape=args.force_rescrape,
            )
    finally:
        for c in clients_to_close:
            await c.close()

        wall_time = time.monotonic() - start_time
        summary_text = _format_results(results, wall_time, str(log_file))

        # Print to console and log file
        logger.info("\n%s", summary_text)

        db.close()
        shutdown.restore()
        logging.shutdown()


def main() -> None:
    """Sync entry point for the hltv-scraper console script."""
    import sys

    # Suppress nodriver's unclosed transport errors on Windows shutdown.
    # These are harmless "Exception ignored in __del__" from asyncio pipe
    # transports that fire after the event loop closes Chrome subprocesses.
    _original_hook = sys.unraisablehook

    def _quiet_transport_cleanup(unraisable):
        if unraisable.object and "Transport" in type(unraisable.object).__name__:
            return  # Silently ignore transport cleanup errors
        _original_hook(unraisable)

    sys.unraisablehook = _quiet_transport_cleanup

    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass  # Already handled by ShutdownHandler
    finally:
        sys.unraisablehook = _original_hook


if __name__ == "__main__":
    main()
