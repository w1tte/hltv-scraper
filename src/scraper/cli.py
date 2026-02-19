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
import time

from scraper.config import ScraperConfig
from scraper.db import Database
from scraper.discovery_repository import DiscoveryRepository
from scraper.http_client import HLTVClient
from scraper.logging_config import setup_logging
from scraper.pipeline import ShutdownHandler, run_pipeline
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
        default=25000,
        help="End offset for results pagination (default: 25000)",
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
        help="Tabs per browser instance (default: 1)",
    )
    parser.add_argument(
        "--page-load-wait",
        type=float,
        default=None,
        help="Seconds to wait after navigation (default: 1.5)",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=None,
        help="Minimum delay between requests in seconds (default: 0.5)",
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
    # 1. Logging
    log_file = setup_logging(data_dir=args.data_dir)

    # 2. Config
    config_overrides = {
        "data_dir": args.data_dir,
        "db_path": f"{args.data_dir}/hltv.db",
        "start_offset": args.start_offset,
        "max_offset": args.end_offset,
    }
    if args.concurrent_tabs is not None:
        config_overrides["concurrent_tabs"] = args.concurrent_tabs
    if args.page_load_wait is not None:
        config_overrides["page_load_wait"] = args.page_load_wait
    if args.min_delay is not None:
        config_overrides["min_delay"] = args.min_delay
    config = ScraperConfig(**config_overrides)

    mode = "full" if args.full else "incremental"
    total_workers = args.overview_workers + args.map_workers + args.perf_workers
    logger.info(
        "Starting hltv-scraper: offsets %d-%d, mode=%s, data_dir=%s, "
        "workers=%d+%d+%d, tabs=%d, page_wait=%.1fs, min_delay=%.1fs, log=%s",
        args.start_offset, args.end_offset, mode, args.data_dir,
        args.overview_workers, args.map_workers, args.perf_workers,
        config.concurrent_tabs, config.page_load_wait, config.min_delay, log_file,
    )

    # 3. Shutdown handler
    shutdown = ShutdownHandler()
    shutdown.install()

    # 4. Database
    db = Database(config.db_path)
    db.initialize()

    # 5. Repositories and storage
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
                    await asyncio.sleep(2.0)
            return pool

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
